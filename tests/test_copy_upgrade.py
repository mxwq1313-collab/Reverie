"""Explicit-copy migration and compatibility checks using synthetic archives."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from test_migration import legacy_database
from wechat_archive import ChatService, ConflictError, NotFoundError, ValidationError
from wechat_archive.agent import ArchiveScope, ArchiveTools
from wechat_archive.database import Database
from wechat_archive.exporter import export_readable
from wechat_archive.importer import JSONImporter
from wechat_archive.migration.copy_upgrade import upgrade_archive_copy
from wechat_archive.migration.manager import validate_schema
from wechat_archive.services.browse_service import BrowseService
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.import_controller import inspect_archive

ROOT = Path(__file__).resolve().parents[1]


class CopyUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "source.db"
        self.target = self.folder / "new archive.db"
        self.service = ChatService(self.source)
        self.service.create_user(wxid="copy_unit_owner", nickname="synthetic owner")
        self.service.create_user(wxid="copy_unit_peer", nickname="synthetic peer")
        self.service.create_message(sender_id=1, receiver_id=2, content="  synthetic原文🙂\n  ", create_time="2026-01-01T00:00:00Z")

    def copy(self):
        return upgrade_archive_copy(self.source, self.target)

    @contextmanager
    def connect(self, path=None):
        connection = sqlite3.connect(path or self.target)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def test_copy_preserves_original_bytes_and_all_legacy_fields(self):
        original = self.source.read_bytes()
        receipt = self.copy()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(receipt["source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(receipt["target_sha256"], hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertTrue(receipt["source_unchanged"])
        self.assertEqual(receipt["target_version"], 3)
        self.assertEqual(ChatService(self.target).get_message(1), self.service.get_message(1))
        with self.connect() as conn:
            validate_schema(conn, 3)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_legacy_version_one_duplicates_and_ids_preserved(self):
        self.source.unlink()
        legacy_database(self.source)
        original = self.source.read_bytes()
        self.copy()
        service = ChatService(self.target)
        self.assertEqual([row.id for row in service.list_messages()], [7, 8])
        self.assertEqual(service.get_message(7).content, service.get_message(8).content)
        self.assertEqual(self.source.read_bytes(), original)
        with self.connect() as conn:
            self.assertEqual([row[0] for row in conn.execute("SELECT version FROM migration_history ORDER BY version")], [2, 3])

    def test_default_initialization_keeps_schema_two(self):
        self.copy()
        before = self.source.read_bytes()
        Database(self.source).initialize()
        self.assertEqual(self.source.read_bytes(), before)
        with self.connect(self.source) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_opening_copied_archive_does_not_remigrate_or_rewrite(self):
        self.copy()
        before = self.target.read_bytes()
        Database(self.target).initialize()
        self.assertEqual(self.target.read_bytes(), before)

    def test_existing_target_and_same_file_refused(self):
        original = self.source.read_bytes()
        self.target.write_bytes(b"existing user file")
        for target in (self.target, self.source):
            with self.subTest(target=target), self.assertRaises(ConflictError):
                upgrade_archive_copy(self.source, target)
        self.assertEqual(self.target.read_bytes(), b"existing user file")
        self.assertEqual(self.source.read_bytes(), original)

    def test_missing_and_unknown_sources_not_created_or_changed(self):
        missing = self.folder / "missing.db"
        with self.assertRaises(NotFoundError):
            upgrade_archive_copy(missing, self.target)
        self.assertFalse(missing.exists())
        unknown = self.folder / "unknown.db"
        with sqlite3.connect(unknown) as conn:
            conn.execute("CREATE TABLE secret_data(value TEXT)")
        before = unknown.read_bytes()
        with self.assertRaises(ConflictError):
            upgrade_archive_copy(unknown, self.target)
        self.assertEqual(unknown.read_bytes(), before)
        self.assertFalse(self.target.exists())

    def test_uri_and_traversal_rejected(self):
        for source in ("https://example.com/archive.db", "../source.db", "\\\\server\\share\\source.db"):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                upgrade_archive_copy(source, self.target)

    def test_live_sidecars_rejected_without_reading_them(self):
        for suffix in ("-wal", "-shm", "-journal"):
            path = Path(str(self.source) + suffix)
            path.write_bytes(b"synthetic sidecar")
            try:
                with self.subTest(suffix=suffix), self.assertRaises(ConflictError):
                    self.copy()
                self.assertEqual(path.read_bytes(), b"synthetic sidecar")
            finally:
                path.unlink()
        self.assertFalse(self.target.exists())

    def test_unknown_trigger_is_refused_and_preserved(self):
        with self.connect(self.source) as conn:
            conn.execute("CREATE TRIGGER custom_trigger AFTER INSERT ON users BEGIN SELECT 1; END")
        before = self.source.read_bytes()
        with self.assertRaises(ConflictError):
            self.copy()
        self.assertEqual(self.source.read_bytes(), before)

    def test_autoincrement_high_watermark_preserved_after_deleted_ids(self):
        with self.connect(self.source) as conn:
            conn.execute("INSERT INTO messages(id,sender_id,receiver_id,create_time,content,msg_type,chat_id) SELECT 42,sender_id,receiver_id,create_time,'deleted','text',chat_id FROM messages WHERE id=1")
            conn.execute("DELETE FROM messages WHERE id=42")
        self.copy()
        message = ChatService(self.target).create_message(sender_id=1, receiver_id=2, content="new event", create_time="2026-01-01T00:01:00Z")
        self.assertEqual(message.id, 43)

    def test_custom_index_preserved(self):
        with self.connect(self.source) as conn:
            conn.execute("CREATE INDEX custom_content_index ON messages(content)")
        self.copy()
        with self.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT sql FROM sqlite_master WHERE name='custom_content_index'").fetchone())

    def test_migration_error_cleans_only_owned_staging_and_keeps_source(self):
        original = self.source.read_bytes()
        from wechat_archive.migration.schema3 import upgrade_to_3
        def fail_after_ddl(conn, execute_script):
            upgrade_to_3(conn, execute_script)
            raise sqlite3.OperationalError("synthetic failure after DDL")
        with patch("wechat_archive.migration.copy_upgrade.upgrade_to_3", side_effect=fail_after_ddl):
            with self.assertRaises(sqlite3.OperationalError):
                self.copy()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.folder.glob(".archive-upgrade-*")), [])

    def test_source_change_guard_refuses_delivery(self):
        from wechat_archive.migration.copy_upgrade import _stamp
        original = _stamp(self.source)
        changed = (*original[:3], original[3] + 1)
        with patch("wechat_archive.migration.copy_upgrade._stamp", side_effect=(original, changed)):
            with self.assertRaises(ConflictError):
                self.copy()
        self.assertFalse(self.target.exists())

    def test_already_upgraded_source_not_silently_copied_again(self):
        self.copy()
        another = self.folder / "another.db"
        original = self.target.read_bytes()
        with self.assertRaises(ConflictError):
            upgrade_archive_copy(self.target, another)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertFalse(another.exists())

    def test_target_creation_race_does_not_overwrite(self):
        import os
        original_link = os.link
        def racing_link(source, target):
            Path(target).write_bytes(b"new user file")
            return original_link(source, target)
        with patch("wechat_archive.migration.copy_upgrade.os.link", side_effect=racing_link):
            with self.assertRaises(ConflictError):
                self.copy()
        self.assertEqual(self.target.read_bytes(), b"new user file")

    def test_low_space_refused(self):
        from collections import namedtuple
        Usage = namedtuple("Usage", "total used free")
        with patch("wechat_archive.migration.copy_upgrade.shutil.disk_usage", return_value=Usage(1, 1, 0)):
            with self.assertRaises(ConflictError):
                self.copy()
        self.assertFalse(self.target.exists())

    def test_revision_changes_and_undo_does_not_revive_reference(self):
        self.copy()
        service = ChatService(self.target)
        tools = ArchiveTools(ArchiveScope(self.target, 1, 2))
        reference = tools.archive_message(1)["item"]["reference"]
        original = service.get_message(1).content
        service.update_message(1, content="edited")
        service.update_message(1, content=original)
        with self.assertRaises(ConflictError):
            tools.resolve_reference(reference)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT revision FROM messages WHERE id=1").fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT content_revision FROM archive_metadata").fetchone()[0], 2)

    def test_new_import_provenance_in_same_transaction(self):
        self.copy()
        report = JSONImporter(self.target, report_dir=self.folder / "logs").import_file(ROOT / "examples/chat_sample.json")
        self.assertEqual(report.success_count, 3)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM message_sources").fetchone()[0], 3)

    def test_missing_revision_trigger_refused(self):
        self.copy()
        with self.connect() as conn:
            conn.execute("DROP TRIGGER messages_revision_update")
        with self.assertRaises(ConflictError):
            inspect_archive(self.target)

    def test_modified_revision_trigger_refused(self):
        self.copy()
        with self.connect() as conn:
            conn.execute("DROP TRIGGER messages_revision_update")
            conn.execute("CREATE TRIGGER messages_revision_update AFTER UPDATE OF content ON messages BEGIN SELECT 1; END")
        with self.assertRaises(ConflictError):
            inspect_archive(self.target)

    def test_case_changed_membership_literal_is_not_equivalent_sql(self):
        self.copy()
        with self.connect() as conn:
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='messages_chat_receiver_insert'").fetchone()[0]
            conn.execute("DROP TRIGGER messages_chat_receiver_insert")
            conn.execute(sql.replace("'group'", "'GROUP'"))
        with self.assertRaises(ConflictError):
            inspect_archive(self.target)

    def test_desktop_browser_assistant_and_export_read_migrated_text(self):
        self.copy()
        controller = ApplicationController(self.folder / "ui_data")
        self.assertEqual(controller.open_archive(self.target)["messages"], 1)
        self.assertEqual(controller.messages(1, 2)["items"][0]["content"], self.service.get_message(1).content)
        tools = ArchiveTools(ArchiveScope(self.target, 1, 2))
        self.assertEqual(tools.archive_messages()["total"], 1)
        receipt = export_readable(self.target, self.folder / "export")
        self.assertEqual(receipt["messages"], 1)

    def test_cli_copy_and_actual_version_without_default_archive_creation(self):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "cli", "upgrade-copy", str(self.source), str(self.target)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["target_version"], 3)
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "cli", "--db", str(self.target), "migrate"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(result.stdout)["schema_version"], 3)

    def test_rich_tools_include_private_metadata_and_exclude_unauthorized_groups(self):
        self.copy()
        with self.connect() as conn:
            conn.execute("INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,chat_id) VALUES (1,2,'2026-01-01T00:00:01.000000Z',NULL,'image',1)")
            conn.execute("INSERT INTO chats(chat_key,kind,title) VALUES ('group:synthetic','group','synthetic group')")
            chat = conn.execute("SELECT id FROM chats WHERE kind='group'").fetchone()[0]
            conn.execute("INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,chat_id) VALUES (1,NULL,'2026-01-01T00:00:02.000000Z','group text','text',?)", (chat,))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,chat_id) VALUES (1,2,'2026-01-01T00:00:03Z','wrong group receiver','text',?)", (chat,))
        service = ChatService(self.target)
        self.assertEqual(len(service.list_messages()), 1)
        tools = ArchiveTools(ArchiveScope(self.target, 1))
        self.assertEqual(tools.archive_messages()["total"], 2)
        self.assertEqual({x["msg_type"] for x in tools.archive_messages()["items"]},{"text","image"})
        receipt=export_readable(self.target,self.folder/'rich_export')
        self.assertEqual(receipt['messages'],3)
        self.assertTrue((self.folder/'rich_export/index.html').exists())


if __name__ == "__main__":
    unittest.main()
