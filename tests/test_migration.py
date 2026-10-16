import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wechat_archive import ChatService, ConflictError, Database
from wechat_archive.database.db import APPLICATION_ID
from wechat_archive.migration.manager import MIGRATIONS

ROOT = Path(__file__).resolve().parents[1]


def legacy_database(path, *, invalid_time=False):
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript((ROOT / "wechat_archive" / "database" / "init.sql").read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
        conn.execute("PRAGMA user_version=1")
        conn.executemany("INSERT INTO users(id,wxid,nickname) VALUES (?,?,?)", [(1, "old_me", "我"), (2, "old_peer", "朋友")])
        stamp = "bad-time" if invalid_time else "2026-01-01T04:00:00.000000Z"
        conn.executemany("INSERT INTO messages(id,sender_id,receiver_id,create_time,content) VALUES (?,?,?,?,?)", [(7, 1, 2, stamp, "旧记录🙂"), (8, 1, 2, stamp, "旧记录🙂")])


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy.db"

    def test_v1_backup_upgrade_preserves_ids_and_old_duplicates(self):
        legacy_database(self.path)
        database = Database(self.path)
        database.initialize()
        self.assertTrue(database.last_backup_path.is_file())
        with sqlite3.connect(database.last_backup_path) as backup:
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
        service = ChatService(database)
        self.assertEqual([row.id for row in service.list_messages()], [7, 8])
        self.assertEqual(service.get_message(7).content, "旧记录🙂")
        self.assertEqual(service.get_message(7).message_hash, service.get_message(8).message_hash)
        self.assertEqual(service.get_message(7).chat_id, service.get_message(8).chat_id)
        with database.connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM migration_history").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        before = self.path.read_bytes()
        Database(self.path).initialize()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(list(database.last_backup_path.parent.glob("*.db"))), 1)

    def test_migration_failure_rolls_back_entire_schema_and_keeps_backup(self):
        legacy_database(self.path)
        before = self.path.read_bytes()
        original_upgrade = MIGRATIONS[2][1]
        def fail(conn):
            original_upgrade(conn)
            raise sqlite3.OperationalError("injected failure")
        database = Database(self.path)
        with patch.dict(MIGRATIONS, {2: ("failure", fail)}):
            with self.assertRaises(sqlite3.OperationalError):
                database.initialize()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(database.last_backup_path.is_file())
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='chats'").fetchone()[0], 0)

    def test_invalid_legacy_time_does_not_lose_old_data(self):
        legacy_database(self.path, invalid_time=True)
        before = self.path.read_bytes()
        with self.assertRaises(ConflictError):
            Database(self.path).initialize()
        self.assertEqual(self.path.read_bytes(), before)

    def test_new_database_has_current_schema_without_unneeded_backup(self):
        database = Database(self.path)
        database.initialize()
        self.assertIsNone(database.last_backup_path)
        self.assertFalse((self.path.parent / "migration_backups").exists())
        with database.connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertIsNone(conn.execute("SELECT backup_path FROM migration_history").fetchone()[0])

    def test_future_version_rejected_without_writes(self):
        legacy_database(self.path)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA user_version=99")
        before = self.path.read_bytes()
        with self.assertRaises(ConflictError):
            Database(self.path).initialize()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "migration_backups").exists())


if __name__ == "__main__":
    unittest.main()
