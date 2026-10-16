"""Selected-conversation snapshot, stable cursor and transactional resume tests."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_external_source as fixture
from wechat_archive import ChatService, ConflictError, ValidationError
from wechat_archive.importer.snapshot_importer import SnapshotImporter
from wechat_archive.migration.copy_upgrade import upgrade_archive_copy
from wechat_archive.wechat_source.snapshot import project_snapshot, SnapshotReader, SNAPSHOT_API

ROOT = Path(__file__).resolve().parents[1]


def header():
    value = fixture.data()
    value.pop("records")
    value["provider"]["api"] = SNAPSHOT_API
    return value


def source_shard(path, *, count=5, offset=0, same_text=False, unknown=False, owner_id=4):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    peer = header()["conversation"]["wxid"]
    table = "Msg_" + hashlib.md5(peer.encode("utf-8")).hexdigest()
    connection.execute("CREATE TABLE Name2Id(user_name TEXT)")
    connection.execute("INSERT INTO Name2Id(rowid,user_name) VALUES (?,?)", (owner_id, header()["account"]["wxid"]))
    connection.execute("INSERT INTO Name2Id(rowid,user_name) VALUES (9,?)", (peer,))
    connection.execute(f'CREATE TABLE "{table}"(local_id INTEGER PRIMARY KEY,local_type INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content,source,packed_info_data,compress_content,server_id INTEGER,sort_seq INTEGER)')
    def values():
        for local in range(1, count + 1):
            number = offset + local
            yield (local, 777 if unknown and local == count else 1, owner_id, 1767225600 if same_text else 1767225600 + number,
                   "same synthetic text" if same_text else "synthetic message " + str(number), None, None, None, 1000000 + number, number)
    connection.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?,?,?,?)', values())
    other = "Msg_" + hashlib.md5(b"unselected_peer").hexdigest()
    connection.execute(f'CREATE TABLE "{other}"(content TEXT)')
    connection.execute(f'INSERT INTO "{other}" VALUES (?)', ("DO_NOT_EXPORT_OTHER_CHAT",))
    connection.commit()
    return connection, table


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.output = self.folder / "sealed snapshot"
        self.target = self.folder / "archive-v3.db"
        source = self.folder / "archive-v2.db"
        ChatService(source)
        upgrade_archive_copy(source, self.target)
        self.logs = self.folder / "reports"

    def snapshot(self, *, count=5, same_text=False, unknown=False, shards=1):
        tables = []
        try:
            for index in range(shards):
                connection, table = source_shard(self.folder / f"source-{index}.db", count=count, offset=index * count, same_text=same_text, unknown=unknown, owner_id=4 + index)
                tables.append((connection, table, f"message__message_{index}.db"))
            return project_snapshot(tables, header(), self.output)
        finally:
            for connection, table, label in tables:
                connection.close()

    def importer(self):
        return SnapshotImporter(self.target, report_dir=self.logs)

    def count(self):
        return ChatService(self.target).stats()["messages"]

    def test_projects_selected_table_not_other_conversations(self):
        self.snapshot()
        reader = SnapshotReader(self.output)
        self.assertEqual(reader.total, 5)
        for records, positions in reader.batches():
            self.assertNotIn("DO_NOT_EXPORT_OTHER_CHAT", json.dumps(records))
        with reader.connection(reader.shards[0]["path"]) as conn:
            self.assertEqual({row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}, {"source_rows"})

    def test_sender_maps_use_own_shard_ids(self):
        self.snapshot(shards=2)
        records = [record for rows, cursor in SnapshotReader(self.output).batches() for record in rows]
        self.assertEqual({record["sender_wxid"] for record in records}, {header()["account"]["wxid"]})

    def test_same_time_same_content_different_ids_and_shards_preserved(self):
        self.snapshot(count=5, shards=2, same_text=True)
        report = self.importer().import_snapshot(self.output, batch_size=3)
        self.assertEqual((report.success_count, report.duplicated_count), (10, 0))
        self.assertEqual(self.count(), 10)

    def test_reader_keyset_resume_covers_each_record_once(self):
        self.snapshot(shards=2)
        reader = SnapshotReader(self.output)
        batches = reader.batches(limit=3)
        first, positions = next(batches)
        batches.close()
        rest = [record for rows, cursor in reader.batches(positions=positions, limit=2) for record in rows]
        keys = [(row["source_database"], row["local_id"]) for row in first + rest]
        self.assertEqual(len(keys), 10)
        self.assertEqual(len(set(keys)), 10)

    def test_cancel_after_commit_and_resume_new_importer(self):
        self.snapshot(count=10)
        cancel = threading.Event()
        first = self.importer().import_snapshot(self.output, batch_size=3, cancel_event=cancel, progress=lambda event: cancel.set())
        self.assertEqual((first.status, first.success_count, self.count()), ("cancelled", 3, 3))
        second = self.importer().import_snapshot(self.output, batch_size=3)
        self.assertEqual((second.status, second.success_count, self.count()), ("success", 7, 10))
        self.assertEqual(second.source_metadata["session_counts"]["added"], 10)

    def test_completed_repeat_rechecks_and_deduplicates(self):
        self.snapshot(count=5)
        first = self.importer().import_snapshot(self.output)
        second = self.importer().import_snapshot(self.output)
        self.assertEqual((first.success_count, second.success_count, second.duplicated_count), (5, 0, 5))

    def test_archive_edit_between_batches_blocks_resume_until_restart(self):
        self.snapshot(count=10)
        cancel = threading.Event()
        first = self.importer().import_snapshot(self.output, batch_size=3, cancel_event=cancel, progress=lambda event: cancel.set())
        service = ChatService(self.target)
        service.create_user(wxid="unrelated_unit", nickname="unrelated")
        service.create_message(sender_id=1, receiver_id=2, content="manual addition", create_time="2026-01-01T00:00:00Z")
        with self.assertRaises(ConflictError):
            self.importer().import_snapshot(self.output)
        restarted = self.importer().import_snapshot(self.output, restart=True)
        self.assertEqual((restarted.success_count, restarted.duplicated_count), (7, 3))

    def test_failure_inside_shared_writer_rolls_back_messages_and_cursor(self):
        self.snapshot(count=5)
        importer = self.importer()
        original = importer.writer._persist
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise sqlite3.OperationalError("injected after message inserts")
        with patch.object(importer.writer, "_persist", side_effect=fail):
            report = importer.import_snapshot(self.output, batch_size=3)
        self.assertEqual(report.status, "failed")
        self.assertEqual(self.count(), 0)
        with ChatService(self.target).database.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)
        self.assertEqual(self.importer().import_snapshot(self.output).success_count, 5)

    def test_post_commit_crash_probe_resumes_without_lost_counts(self):
        self.snapshot(count=5)
        def crash(number):
            raise RuntimeError("simulated process boundary")
        with self.assertRaises(RuntimeError):
            self.importer().import_snapshot(self.output, batch_size=2, after_batch=crash)
        self.assertEqual(self.count(), 2)
        report = self.importer().import_snapshot(self.output, batch_size=2)
        self.assertEqual((report.success_count, report.source_metadata["session_counts"]["added"]), (3, 5))

    def test_unknown_rows_retained_and_count_conserved(self):
        self.snapshot(count=5, unknown=True)
        report = self.importer().import_snapshot(self.output, batch_size=2)
        self.assertEqual((report.status, report.success_count, report.source_metadata["quarantined_count"]), ("partial", 4, 1))
        self.assertEqual(sum(report.source_metadata["session_counts"][key] for key in ("added", "duplicated", "quarantined", "source_duplicates")), 5)

    def test_schema_two_not_automatically_upgraded(self):
        self.snapshot()
        path = self.folder / "default-v2.db"
        ChatService(path)
        before = path.read_bytes()
        with self.assertRaises(ValidationError):
            SnapshotImporter(path, report_dir=self.logs).import_snapshot(self.output)
        self.assertEqual(path.read_bytes(), before)

    def test_manifest_count_and_shard_digest_mismatch_refused(self):
        self.snapshot()
        path = self.output / "snapshot.json"
        original = path.read_text(encoding="utf-8")
        for field, value in (("records", 99), ("format", "unknown")):
            manifest = json.loads(original)
            manifest[field] = value
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises((ConflictError, ValidationError)):
                SnapshotReader(self.output)
        path.write_text(original, encoding="utf-8")
        manifest = json.loads(original)
        manifest["shards"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ConflictError):
            SnapshotReader(self.output)

    def test_snapshot_path_traversal_and_sidecar_refused(self):
        self.snapshot()
        path = self.output / "snapshot.json"
        original = path.read_text(encoding="utf-8")
        manifest = json.loads(original)
        manifest["shards"][0]["file"] = "../source-0.db"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValidationError):
            SnapshotReader(self.output)
        path.write_text(original, encoding="utf-8")
        Path(str(self.output / "part-0000.db") + "-wal").write_bytes(b"synthetic")
        with self.assertRaises(ConflictError):
            SnapshotReader(self.output)

    def test_unselected_conversation_table_refused_before_projection(self):
        connection, table = source_shard(self.folder / "source.db")
        try:
            other = "Msg_" + hashlib.md5(b"unselected_peer").hexdigest()
            with self.assertRaises(ValidationError):
                project_snapshot([(connection, other, "message_0")], header(), self.output)
        finally:
            connection.close()
        self.assertFalse(self.output.exists())

    def test_existing_output_preserved(self):
        self.output.mkdir()
        preserved = self.output / "user.txt"
        preserved.write_text("existing", encoding="utf-8")
        connection, table = source_shard(self.folder / "source.db")
        try:
            with self.assertRaises(ConflictError):
                project_snapshot([(connection, table, "message_0")], header(), self.output)
        finally:
            connection.close()
        self.assertEqual(preserved.read_text(encoding="utf-8"), "existing")

    def test_report_directory_cannot_modify_source_snapshot(self):
        self.snapshot()
        with self.assertRaises(ValidationError):
            SnapshotImporter(self.target, report_dir=self.output / "logs").import_snapshot(self.output)
        self.assertFalse((self.output / "logs").exists())

    def test_cli_streams_and_repeats_with_explicit_target(self):
        self.snapshot()
        command = [sys.executable, "-B", "-X", "utf8", "-m", "cli", "--db", str(self.target), "import-snapshot", str(self.output), "--report-dir", str(self.logs), "--batch-size", "2"]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(first.stdout)["success_count"], 5)
        self.assertEqual(json.loads(second.stdout)["duplicated_count"], 5)

    def test_live_worker_snapshot_bridge_uses_selected_peer_only(self):
        from wechat_archive.wechat_source.live_source import perform
        original = self.folder / "original_source"
        original.mkdir()
        path = original / "message_0.db"
        connection, table = source_shard(path)
        class FakeSDK:
            wxid = header()["account"]["wxid"]
            _keys = {"synthetic": "not a key"}
            _db_files = [("message/message_0.db", str(path), 0)]
            def _shard_label(self, conn):
                return "message__message_0.db"
            def _run_msg_query(self, peer, callback):
                self.peer = peer
                return callback([(connection, table)])
        sdk = FakeSDK()
        try:
            with patch("wechat_archive.wechat_source.live_source.open_account", return_value=(sdk, {"nick_name": "synthetic"})), patch("wechat_archive.wechat_source.live_source.read_contacts", return_value=[{"username": header()["conversation"]["wxid"], "nick_name": "synthetic"}]), patch("wechat_archive.wechat_source.live_source._client_version", return_value="unit_test"):
                result = perform({"action": "snapshot", "root": str(original), "account": "synthetic", "peer": header()["conversation"]["wxid"], "workdir": str(self.folder / "work"), "output": str(self.output)})
            self.assertTrue(result["snapshot"])
            self.assertEqual(SnapshotReader(self.output).total, 5)
            self.assertEqual(sdk.peer, header()["conversation"]["wxid"])
        finally:
            connection.close()

    def test_schema_three_controller_selects_snapshot_for_all_history(self):
        from wechat_archive.ui.application_controller import ApplicationController
        self.snapshot()
        calls = []
        def runner(action, data_dir, **options):
            calls.append((action, options["peer"]))
            return {"output": str(self.output), "records": 5, "snapshot": True}
        controller = ApplicationController(self.folder / "ui", source_runner=runner)
        controller.open_archive(self.target)
        result = controller.acquire_import("unit-root", "unit-account", header()["conversation"]["wxid"], all_history=True)
        self.assertEqual(calls, [("snapshot", header()["conversation"]["wxid"])])
        self.assertEqual(result["report"].success_count, 5)

    def test_file_import_preview_does_not_create_target_and_reports_unknown_text_count(self):
        from wechat_archive.ui.import_controller import ImportController
        self.snapshot()
        target = self.folder / "not_created.db"
        preview = ImportController(report_dir=self.logs).preview(self.output, target)
        self.assertEqual((preview["source_records"], preview["messages"]), (5, None))
        self.assertFalse(target.exists())
        report, path = ImportController(report_dir=self.logs).import_data(self.output, self.target)
        self.assertEqual(report.success_count, 5)

    def test_streaming_mode_rejects_whole_file_strict_option(self):
        from wechat_archive.ui.import_controller import ImportController
        self.snapshot()
        with self.assertRaises(ValidationError):
            ImportController(report_dir=self.logs).preview(self.output, self.target, strict=True)


if __name__ == "__main__":
    unittest.main()
