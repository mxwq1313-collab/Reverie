import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from android_fixture import create_android_fixture, refresh_hash
from wechat_archive import ChatService
from wechat_archive.importer.records import LoadedDocument
from wechat_archive.importer.validator import validate_document
from wechat_archive.wechat_adapter import AndroidAdapter, WeChatImporter, detect_source
from wechat_archive.wechat_adapter.android import AndroidWeChatParser, Decryptor, SQLiteDatabaseReader, detect_android_source
from wechat_archive.wechat_adapter.android.detector import local_path
from wechat_archive.wechat_adapter.android.errors import AndroidSourceError

ROOT = Path(__file__).resolve().parents[1]


class AndroidTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_root = self.root / "android_source"
        self.database = create_android_fixture(self.source_root)
        self.metadata = self.database.parent / "android_source.json"
        self.target = self.root / "archive.db"
        self.logs = self.root / "logs"

    def change(self, sql, values=()):
        with sqlite3.connect(self.database) as conn:
            conn.execute(sql, values)
        refresh_hash(self.database)

    def meta(self, **updates):
        value = json.loads(self.metadata.read_text(encoding="utf-8"))
        value.update(updates)
        self.metadata.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def parse(self):
        return AndroidWeChatParser(self.database).parse()

    def assert_failed(self, result, code=None):
        self.assertEqual(result.report.status, "failed")
        self.assertIsNone(result.document)
        self.assertGreater(result.report.failed, 0)
        if code:
            self.assertTrue(any(issue["code"] == code for issue in result.report.issues), result.report.issues)

    def test_detection_root_directory(self):
        result = detect_android_source(self.source_root)
        self.assertEqual((result.status, result.sqlite_header, result.micro_msg_layout), ("candidate", True, True))
        self.assertEqual(result.database, str(self.database.resolve()))

    def test_detection_micro_msg_directory(self):
        self.assertEqual(detect_android_source(self.source_root / "MicroMsg").status, "candidate")

    def test_detection_account_directory(self):
        self.assertEqual(detect_android_source(self.database.parent).status, "candidate")

    def test_detection_file(self):
        self.assertEqual(detect_android_source(self.database).status, "candidate")

    def test_detection_empty_directory(self):
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(detect_android_source(empty).status, "failed")

    def test_detection_wrong_directory(self):
        folder = self.root / "wrong"
        folder.mkdir()
        (folder / "random.txt").write_text("x")
        self.assertEqual(detect_android_source(folder).files, [])

    def test_detection_missing_path(self):
        self.assertEqual(detect_android_source(self.root / "missing").status, "failed")

    def test_detection_multiple_accounts_rejected(self):
        extra = self.source_root / "MicroMsg" / "second-account"
        extra.mkdir()
        shutil.copy2(self.database, extra / "EnMicroMsg.db")
        self.assertIn("多个", detect_android_source(self.source_root).reason)

    def test_detection_missing_metadata_does_not_open_database(self):
        self.metadata.unlink()
        with patch("pathlib.Path.open", side_effect=AssertionError("must not read source")):
            self.assertEqual(detect_android_source(self.database).status, "failed")

    def test_detection_success_does_not_certify_schema(self):
        self.meta(schema_profile="unknown-future-version")
        self.assertEqual(detect_android_source(self.database).status, "candidate")
        self.assert_failed(self.parse(), "unknown_schema")

    def test_reader_lists_tables(self):
        with SQLiteDatabaseReader(self.database) as reader:
            self.assertEqual(reader.list_tables(), ["chatroom", "message", "rcontact"])

    def test_reader_columns_and_structure_report(self):
        with SQLiteDatabaseReader(self.database) as reader:
            self.assertIn("createTime", [row["name"] for row in reader.table_columns("message")])
            self.assertTrue(reader.schema_report()["read_only"])
            self.assertEqual(reader._connection().execute("PRAGMA query_only").fetchone()[0], 1)

    def test_reader_missing_table(self):
        with SQLiteDatabaseReader(self.database) as reader:
            with self.assertRaises(AndroidSourceError):
                reader.table_columns("missing")

    def test_reader_missing_column(self):
        with SQLiteDatabaseReader(self.database) as reader:
            with self.assertRaises(AndroidSourceError):
                list(reader.iter_rows("message", ["missing"]))

    def test_reader_sql_identifier_cannot_inject(self):
        with SQLiteDatabaseReader(self.database) as reader:
            with self.assertRaises(AndroidSourceError):
                reader.table_columns('message; DROP TABLE message; --')
            self.assertIn("message", reader.list_tables())

    def test_reader_is_read_only_and_creates_no_files(self):
        before, files = self.database.read_bytes(), set(self.database.parent.iterdir())
        with SQLiteDatabaseReader(self.database) as reader:
            for sql in ("DELETE FROM message", "CREATE TABLE evil(x)", "PRAGMA writable_schema=ON", "ATTACH DATABASE ':memory:' AS other"):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                    reader._connection().execute(sql)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(set(self.database.parent.iterdir()), files)

    def test_reader_closed_context_cannot_be_used(self):
        with SQLiteDatabaseReader(self.database) as reader:
            pass
        with self.assertRaises(AndroidSourceError):
            reader.list_tables()

    def test_reader_rejects_wal_and_journal_sidecars(self):
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = self.database.with_name(self.database.name + suffix)
            sidecar.write_bytes(b"pending")
            with self.subTest(suffix=suffix), self.assertRaises(AndroidSourceError):
                with SQLiteDatabaseReader(self.database):
                    pass
            sidecar.unlink()

    def test_reader_rejects_non_sqlite_without_decryption(self):
        self.database.write_bytes(b"encrypted-or-unknown" * 10)
        with patch.object(Decryptor, "decrypt", side_effect=AssertionError("must not decrypt")):
            self.assert_failed(self.parse())

    def test_reader_change_detection_discards_result(self):
        with self.assertRaises(AndroidSourceError):
            with SQLiteDatabaseReader(self.database):
                self.database.write_bytes(self.database.read_bytes() + b"external-change")

    def test_parse_normal_texts_and_skip_counts(self):
        result = self.parse()
        self.assertEqual((result.report.status, result.report.contacts, result.report.participants, result.report.text_messages, result.report.failed), ("success", 2, 3, 5, 0))
        self.assertEqual(result.report.skipped_unsupported_count, 2)
        self.assertIsInstance(result.document, LoadedDocument)
        self.assertEqual(validate_document(result.document.payload).issues, [])

    def test_parse_correct_time_and_directions(self):
        messages = self.parse().document.payload["messages"]
        self.assertEqual(messages[0]["timestamp"], "2026-01-05T04:00:00.000000Z")
        self.assertEqual((messages[0]["sender_id"], messages[0]["receiver_id"]), ("wxid_android_me", "wxid_android_zhang"))
        self.assertEqual((messages[1]["sender_id"], messages[1]["receiver_id"]), ("wxid_android_zhang", "wxid_android_me"))

    def test_parse_preserves_unicode_and_whitespace(self):
        content = "  中文🙂\n'原文'  "
        self.change("UPDATE message SET content=? WHERE msgId=1", (content,))
        self.assertEqual(self.parse().document.payload["messages"][0]["content"], content)

    def test_parse_wrong_time_is_failure(self):
        self.change("UPDATE message SET createTime='not-time' WHERE msgId=1")
        self.assert_failed(self.parse(), "invalid_time")

    def test_parse_seconds_in_millisecond_field_is_failure(self):
        self.change("UPDATE message SET createTime=1767585600 WHERE msgId=1")
        self.assert_failed(self.parse(), "invalid_time")

    def test_parse_empty_content_is_failure(self):
        self.change("UPDATE message SET content='  ' WHERE msgId=1")
        self.assert_failed(self.parse(), "invalid_field")

    def test_parse_null_content_is_failure(self):
        self.change("UPDATE message SET content=NULL WHERE msgId=1")
        self.assert_failed(self.parse(), "invalid_field")

    def test_parse_unknown_type_is_failure(self):
        self.change("UPDATE message SET type=999999 WHERE msgId=1")
        self.assert_failed(self.parse(), "unknown_message_type")

    def test_parse_invalid_direction_is_failure(self):
        self.change("UPDATE message SET isSend=2 WHERE msgId=1")
        self.assert_failed(self.parse(), "invalid_direction")

    def test_parse_missing_contact_is_failure(self):
        self.change("UPDATE message SET talker='missing-person' WHERE msgId=1")
        self.assert_failed(self.parse(), "missing_contact")

    def test_parse_missing_table_is_failure(self):
        self.change("DROP TABLE message")
        self.assert_failed(self.parse(), "missing_table")

    def test_parse_missing_field_is_failure(self):
        self.change("ALTER TABLE message RENAME COLUMN createTime TO otherTime")
        self.assert_failed(self.parse(), "missing_field")

    def test_parse_field_affinity_mismatch_is_failure(self):
        self.change("DROP TABLE message")
        self.change("CREATE TABLE message(msgId INTEGER,createTime TEXT,talker TEXT,isSend INTEGER,type INTEGER,content TEXT)")
        self.assert_failed(self.parse(), "field_type")

    def test_parse_metadata_time_unit_mismatch_is_failure(self):
        self.meta(time_unit="seconds")
        self.assert_failed(self.parse(), "time_unit_mismatch")

    def test_parse_metadata_snapshot_claim_required(self):
        self.meta(sqlite_snapshot=False)
        self.assert_failed(self.parse())

    def test_parse_metadata_binding_cannot_escape(self):
        self.meta(database_file="../other.db")
        self.assert_failed(self.parse())

    def test_parse_source_hash_mismatch_is_failure(self):
        self.meta(database_sha256="0" * 64)
        self.assert_failed(self.parse(), "source_hash_mismatch")

    def test_malformed_metadata_types_fail_cleanly(self):
        original = self.metadata.read_text(encoding="utf-8")
        for update in ({"database_sha256":int("1"*64)}, {"account":None}, {"schema_profile":[]}, {"time_unit":[]}, {"sqlite_snapshot":"true"}):
            self.metadata.write_text(original, encoding="utf-8")
            self.meta(**update)
            with self.subTest(update=update):
                self.assert_failed(self.parse())

    def test_parse_optional_server_id_absent_and_empty_tables(self):
        self.change("ALTER TABLE message DROP COLUMN msgSvrId")
        self.assertEqual(self.parse().document.payload["messages"][0]["source_id"], "local:1")
        self.change("DELETE FROM message")
        self.assertEqual(self.parse().report.text_messages, 0)

    def test_contacts_remark_and_id_fallback(self):
        self.change("UPDATE rcontact SET conRemark='张三备注' WHERE username='wxid_android_zhang'")
        users = {row["id"]:row for row in self.parse().document.payload["users"]}
        self.assertEqual(users["wxid_android_zhang"]["nickname"], "张三备注")
        self.change("UPDATE rcontact SET nickname=NULL,conRemark=NULL WHERE username='wxid_android_zhang'")
        users = {row["id"]:row for row in self.parse().document.payload["users"]}
        self.assertEqual(users["wxid_android_zhang"]["nickname"], "wxid_android_zhang")

    def test_import_reuses_dedup_and_does_not_touch_source(self):
        first_row = self.parse().document.payload["messages"][0]
        self.change("INSERT INTO message SELECT 8,1008,type,isSend,createTime,talker,content FROM message WHERE msgId=1")
        before, meta = self.database.read_bytes(), self.metadata.read_bytes()
        importer = WeChatImporter(self.target, adapter="android", report_dir=self.logs)
        first, second = importer.import_file(self.database), importer.import_file(self.database)
        self.assertEqual((first.success_count, first.duplicated_count, second.duplicated_count), (5, 1, 6))
        self.assertEqual(ChatService(self.target).stats(), {"users":3,"messages":5})
        self.assertEqual((self.database.read_bytes(), self.metadata.read_bytes()), (before, meta))

    def test_auto_adapter_imports_directory(self):
        self.assertTrue(detect_source(self.source_root).supported)
        report = WeChatImporter(self.target, report_dir=self.logs).import_file(self.source_root)
        self.assertEqual(report.success_count, 5)

    def test_destination_cannot_overwrite_source_or_metadata(self):
        for target in (self.database, self.metadata):
            before = target.read_bytes()
            report = WeChatImporter(target, adapter="android", report_dir=self.logs).import_file(self.database)
            self.assertEqual(report.status, "failed")
            self.assertEqual(target.read_bytes(), before)

    def test_illegal_paths_are_rejected(self):
        for path in (None, 42, b"bytes.db", "http://example.com/data.db", "file:///tmp/data.db", "abc\x00.db", self.source_root / ".." / "android_source"):
            with self.subTest(path=path), self.assertRaises(AndroidSourceError):
                local_path(path)

    def test_decryptor_is_explicit_not_implemented(self):
        self.assertIs(Decryptor().decrypt(self.database, "unused-placeholder"), NotImplemented)

    def test_existing_adapter_and_extractor_interfaces(self):
        parser = AndroidWeChatParser(self.database)
        self.assertEqual(len(parser.extract_users()), 3)
        self.assertEqual(len(parser.extract_messages()), 5)
        self.assertEqual(len(AndroidAdapter().load(self.database).payload["messages"]), 5)


class AndroidCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = create_android_fixture(self.root / "source")
        self.target = self.root / "archive.db"

    def cli(self, *args, code=0, error=False):
        result = subprocess.run([sys.executable,"-m","cli","--db",str(self.target),"android",*args],cwd=ROOT,capture_output=True,encoding="utf-8",timeout=15)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(result.stderr if error else result.stdout)

    def test_cli_detect_report(self):
        self.assertEqual(self.cli("detect", str(self.database))["status"], "candidate")
        self.assertFalse(self.target.exists())

    def test_cli_schema_report(self):
        report = self.cli("schema", str(self.database))
        self.assertIn("message", report["tables"])
        self.assertTrue(report["read_only"])

    def test_cli_parse_exports_standard_and_report(self):
        output = self.root / "exchange.json"
        report = self.cli("parse", str(self.database), "--output", str(output))
        self.assertEqual((report["status"],report["text_messages"]), ("success",5))
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["format"], "chat-exchange")
        self.assertFalse(self.target.exists())

    def test_cli_output_cannot_overwrite_source(self):
        before = self.database.read_bytes()
        self.cli("parse",str(self.database),"--output",str(self.database),code=1,error=True)
        self.assertEqual(self.database.read_bytes(), before)

    def test_cli_failure_is_report_and_does_not_export(self):
        metadata = self.database.parent / "android_source.json"
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        payload["schema_profile"] = "unknown"
        metadata.write_text(json.dumps(payload), encoding="utf-8")
        output = self.root / "bad.json"
        self.assertEqual(self.cli("parse",str(self.database),"--output",str(output),code=1)["status"],"failed")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
