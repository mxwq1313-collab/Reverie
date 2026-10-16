import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from wechat_archive import ChatService, ConflictError, Database, NotFoundError, ValidationError
from wechat_archive.database.db import APPLICATION_ID, SCHEMA_VERSION
from wechat_archive.demo import seed_demo


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "中文目录" / "chat.db"
        self.service = ChatService(self.path)
        self.me = self.service.create_user("wxid_me", "我")
        self.friend = self.service.create_user("wxid_friend", "张三")
        self.other = self.service.create_user("wxid_other", "李四")

    def message(self, sender=None, receiver=None, content="你好", stamp="2026-01-01T12:00:00+08:00"):
        return self.service.create_message(
            self.me.id if sender is None else sender,
            self.friend.id if receiver is None else receiver,
            content, create_time=stamp,
        )

    def test_user_crud_and_avatar_clear(self):
        user = self.service.create_user("  new_wxid  ", "  新联系人  ", "avatar.png")
        self.assertEqual(self.service.get_user(user.id), user)
        self.assertEqual(self.service.get_user_by_wxid("new_wxid"), user)
        changed = self.service.update_user(user.id, wxid="new_wxid_2", nickname="新昵称", avatar=None)
        self.assertEqual((changed.wxid, changed.nickname, changed.avatar), ("new_wxid_2", "新昵称", None))
        self.service.delete_user(user.id)
        with self.assertRaises(NotFoundError):
            self.service.get_user(user.id)

    def test_duplicate_wxid_create_and_update_rollback(self):
        with self.assertRaises(ConflictError):
            self.service.create_user("wxid_me", "重复")
        with self.assertRaises(ConflictError):
            self.service.update_user(self.friend.id, wxid="wxid_me", nickname="不应该保存")
        self.assertEqual(self.service.get_user(self.friend.id), self.friend)
        self.assertEqual(self.service.stats()["users"], 3)

    def test_user_pagination(self):
        self.assertEqual(self.service.list_users(limit=1, offset=1), [self.friend])
        self.assertEqual(self.service.list_users(offset=99), [])

    def test_missing_user_and_message(self):
        for operation in (
            lambda: self.service.get_user(999), lambda: self.service.get_user_by_wxid("missing"),
            lambda: self.service.update_user(999, nickname="不存在"), lambda: self.service.delete_user(999),
            lambda: self.service.get_message(999), lambda: self.service.update_message(999, content="不存在"),
            lambda: self.service.delete_message(999),
        ):
            with self.subTest(operation=operation), self.assertRaises(NotFoundError):
                operation()

    def test_message_crud_and_unicode_roundtrip(self):
        message = self.message(content="  中文、emoji🙂\n第二行 '单引号'  ")
        self.assertEqual(self.service.get_message(message.id), message)
        self.assertEqual(message.create_time, datetime(2026, 1, 1, 4, tzinfo=timezone.utc))
        changed = self.service.update_message(
            message.id, sender_id=self.friend.id, receiver_id=self.other.id,
            content="更新后的内容", create_time="2026-01-02T12:00:00+08:00", msg_type="text",
        )
        self.assertEqual((changed.sender_id, changed.receiver_id, changed.content), (self.friend.id, self.other.id, "更新后的内容"))
        self.assertEqual(changed.create_time.day, 2)
        self.service.delete_message(message.id)
        self.assertEqual(self.service.stats()["messages"], 0)

    def test_default_timestamp_is_aware(self):
        before = datetime.now(timezone.utc)
        message = self.service.create_message(self.me.id, self.friend.id, "现在")
        self.assertLessEqual(before, message.create_time)
        self.assertLessEqual(message.create_time, datetime.now(timezone.utc))

    def test_both_message_endpoints_must_exist(self):
        for sender, receiver in ((999, self.friend.id), (self.me.id, 999)):
            with self.subTest(sender=sender, receiver=receiver), self.assertRaises(NotFoundError):
                self.message(sender=sender, receiver=receiver)
        self.assertEqual(self.service.stats()["messages"], 0)

    def test_invalid_message_update_is_atomic(self):
        message = self.message()
        with self.assertRaises(NotFoundError):
            self.service.update_message(message.id, content="不应写入", receiver_id=999)
        self.assertEqual(self.service.get_message(message.id), message)

    def test_foreign_keys_enabled_on_every_connection(self):
        for sender, receiver in ((999, self.friend.id), (self.me.id, 999)):
            with self.subTest(sender=sender, receiver=receiver), self.assertRaises(sqlite3.IntegrityError):
                with self.service.database.connection() as conn:
                    self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                    conn.execute(
                        "INSERT INTO messages(sender_id, receiver_id, create_time, content) VALUES (?, ?, ?, ?)",
                        (sender, receiver, "2026-01-01T00:00:00.000000Z", "不能插入"),
                    )
        self.assertEqual(self.service.stats()["messages"], 0)

    def test_delete_contact_protects_sent_and_received_messages(self):
        message = self.message()
        for user in (self.me, self.friend):
            with self.subTest(user=user), self.assertRaises(ConflictError):
                self.service.delete_user(user.id)
        self.assertEqual(self.service.get_message(message.id), message)
        self.service.delete_message(message.id)
        self.service.delete_user(self.friend.id)

    def test_conversation_includes_both_directions_and_excludes_third_party(self):
        outgoing = self.message()
        incoming = self.message(sender=self.friend.id, receiver=self.me.id, content="回复")
        third_party = self.message(receiver=self.other.id, content="其他聊天")
        self.assertEqual(self.service.get_conversation(self.me.id, self.friend.id), [outgoing, incoming])
        self.assertEqual(self.service.get_conversation(self.friend.id, self.me.id), [outgoing, incoming])
        self.assertEqual(self.service.list_messages(user_id=self.me.id), [outgoing, incoming, third_party])

    def test_self_conversation(self):
        note = self.message(receiver=self.me.id, content="给自己留条记录")
        self.assertEqual(self.service.get_conversation(self.me.id, self.me.id), [note])

    def test_timezones_chronological_order_ties_and_pagination(self):
        late = self.message(stamp="2026-01-01T05:00:00Z")
        early = self.message(stamp="2026-01-01T12:00:00+08:00")
        tie = self.message(stamp=datetime(2026, 1, 1, 4, tzinfo=timezone.utc))
        fractional = self.message(stamp="2026-01-01T04:00:00.000001Z")
        self.assertEqual(self.service.list_messages(), [early, tie, fractional, late])
        self.assertEqual(self.service.list_messages(limit=2, offset=1), [tie, fractional])

    def test_time_window_start_inclusive_end_exclusive(self):
        first = self.message(stamp="2026-01-01T04:00:00Z")
        self.message(stamp="2026-01-01T05:00:00Z")
        self.assertEqual(self.service.list_messages(start_time="2026-01-01T12:00:00+08:00", end_time="2026-01-01T05:00:00Z"), [first])
        with self.assertRaises(ValidationError):
            self.service.list_messages(start_time="2026-01-02T00:00:00Z", end_time="2026-01-01T00:00:00Z")

    def test_literal_search_and_conversation_filter(self):
        literal = self.message(content="进度 100%_，下午开会")
        self.message(content="进度 100X，下午开会")
        self.message(receiver=self.other.id, content="下午开会")
        self.assertEqual(self.service.search_messages("%_"), [literal])
        self.assertEqual(len(self.service.search_messages("开会", user_id=self.me.id, peer_id=self.friend.id)), 2)
        self.assertEqual(self.service.search_messages("不存在"), [])

    def test_sql_text_cannot_change_query_or_schema(self):
        payload = "x'; DROP TABLE users; --"
        user = self.service.create_user(payload, "引号联系人")
        message = self.message(content=payload)
        self.assertEqual(self.service.get_user_by_wxid(payload), user)
        self.assertEqual(self.service.search_messages(payload), [message])
        self.assertEqual(self.service.search_messages("' OR 1=1 --"), [])
        self.assertEqual(self.service.stats()["users"], 4)

    def test_validation_for_text_ids_and_types(self):
        for bad in ("", " \t\n", "x\x00y", None, 123):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.service.create_user(bad, "昵称")
            with self.subTest(content=bad), self.assertRaises(ValidationError):
                self.message(content=bad)
        for bad in (0, -1, True, "1", 2**63):
            with self.subTest(id=bad), self.assertRaises(ValidationError):
                self.service.get_user(bad)
        with self.assertRaises(ValidationError):
            self.service.create_message(self.me.id, self.friend.id, "图片", msg_type="image")
        with self.assertRaises(ValidationError):
            self.service.update_user(self.me.id)
        with self.assertRaises(ValidationError):
            self.service.update_user(self.me.id, avatar=123)
        message = self.message()
        with self.assertRaises(ValidationError):
            self.service.update_message(message.id)
        with self.assertRaises(ValidationError):
            self.service.update_message(message.id, msg_type="image")

    def test_invalid_or_naive_time_is_rejected(self):
        for stamp in ("not-a-date", "2026-01-01T12:00:00", datetime(2026, 1, 1), 42, "0001-01-01T00:00:00+08:00"):
            with self.subTest(stamp=stamp), self.assertRaises(ValidationError):
                self.message(stamp=stamp)

    def test_invalid_filters_and_pagination(self):
        for options in ({"limit": 0}, {"limit": 1001}, {"limit": True}, {"offset": -1}, {"offset": 2**63}, {"peer_id": self.friend.id}, {"keyword": ""}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.service.list_messages(**options)
        with self.assertRaises(NotFoundError):
            self.service.get_conversation(self.me.id, 999)

    def test_transaction_rolls_back_on_exception(self):
        with self.assertRaises(RuntimeError):
            with self.service.database.connection() as conn:
                conn.execute("INSERT INTO users(wxid, nickname) VALUES (?, ?)", ("rolled_back", "不保存"))
                raise RuntimeError("中断事务")
        self.assertEqual(self.service.stats()["users"], 3)

    def test_reopen_and_reinitialize_preserves_records(self):
        message = self.message()
        reopened = ChatService(self.path)
        reopened.database.initialize()
        self.assertEqual(reopened.get_message(message.id), message)
        self.assertEqual(reopened.stats(), {"users": 3, "messages": 1})
        with reopened.database.connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(conn.execute("PRAGMA application_id").fetchone()[0], APPLICATION_ID)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_unknown_database_or_schema_is_not_rewritten(self):
        for kind in ("table", "view", "future", "damaged", "columns", "foreign_keys"):
            path = Path(self.temp.name) / f"{kind}.db"
            with sqlite3.connect(path) as conn:
                if kind == "table":
                    conn.execute("CREATE TABLE other(secret TEXT)")
                    conn.execute("INSERT INTO other VALUES ('保留')")
                elif kind == "view":
                    conn.execute("CREATE VIEW other AS SELECT '保留' AS secret")
                elif kind == "future":
                    conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                    conn.execute("PRAGMA user_version = 99")
                else:
                    conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                    if kind == "columns":
                        conn.execute("CREATE TABLE users(id INTEGER)")
                        conn.execute("CREATE TABLE messages(id INTEGER)")
                    elif kind == "foreign_keys":
                        conn.execute("CREATE TABLE users(id INTEGER, wxid TEXT, nickname TEXT, avatar TEXT)")
                        conn.execute("CREATE TABLE messages(id INTEGER, sender_id INTEGER, receiver_id INTEGER, create_time TEXT, content TEXT, msg_type TEXT)")
            before = path.read_bytes()
            with self.subTest(kind=kind), self.assertRaises(ConflictError):
                ChatService(path)
            self.assertEqual(path.read_bytes(), before)

    def test_connections_are_closed(self):
        with self.service.database.connection() as conn:
            conn.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_in_memory_path_is_rejected(self):
        with self.assertRaises(ValidationError):
            Database(":memory:")


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ChatService(Path(self.temp.name) / "demo.db")

    def test_demo_is_repeatable(self):
        self.assertTrue(seed_demo(self.service))
        self.assertFalse(seed_demo(self.service))
        self.assertEqual(self.service.stats(), {"users": 3, "messages": 5})
        self.assertEqual(len(self.service.get_conversation(1, 2)), 3)
        self.assertEqual(len(self.service.search_messages("开会")), 2)

    def test_demo_refuses_existing_other_data(self):
        user = self.service.create_user("real_user", "实际联系人")
        with self.assertRaises(ConflictError):
            seed_demo(self.service)
        self.assertEqual(self.service.get_user(user.id), user)
        self.assertEqual(self.service.stats(), {"users": 1, "messages": 0})


if __name__ == "__main__":
    unittest.main()
