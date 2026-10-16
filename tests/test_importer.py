import csv
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from wechat_archive import ChatService, Database
from wechat_archive.database.hashing import message_hash
from wechat_archive.importer import BaseImporter, CSVImporter, JSONImporter, ReportWriteError
from wechat_archive.importer.records import LoadedDocument
from wechat_archive.web.server import make_server

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return json.loads((ROOT / "examples" / "chat_sample.json").read_text(encoding="utf-8"))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db = self.folder / "chat.db"
        self.logs = self.folder / "import_logs"
        self.file = self.folder / "chat.json"
        self.importer = JSONImporter(self.db, report_dir=self.logs)

    def write(self, payload):
        self.file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self.file

    def run_import(self, payload):
        return self.importer.import_file(self.write(payload))

    def counts(self):
        return ChatService(self.db).stats()

    def assert_balance(self, report):
        self.assertEqual(report.messages, report.success_count + report.duplicated_count + report.failed_count)

    def test_json_normal_and_source_preservation(self):
        data = sample()
        data["messages"][0]["source_hash"] = "A" * 64
        report = self.run_import(data)
        self.assertEqual((report.status, report.success_count, report.users_created_count, report.chats_created_count), ("success", 3, 2, 1))
        self.assertEqual(self.counts(), {"users": 2, "messages": 3})
        message = ChatService(self.db).get_message(1)
        self.assertEqual((message.source, message.source_id, message.external_id, message.source_hash), ("sample:my-account", "export-1001", "m1", "a" * 64))
        self.assertEqual(len(message.message_hash), 64)
        self.assertIsNotNone(message.chat_id)
        self.assert_balance(report)

    def test_repeat_import_and_log_uniqueness(self):
        first = self.run_import(sample())
        second = self.importer.import_file(self.file)
        self.assertEqual((second.success_count, second.duplicated_count, second.users_reused_count), (0, 3, 2))
        self.assertNotEqual(first.report_path, second.report_path)
        self.assertEqual(len(list(self.logs.glob("*.json"))), 2)
        saved = json.loads(Path(second.report_path).read_text(encoding="utf-8"))
        self.assertEqual(saved, second.to_dict())
        self.assert_balance(second)

    def test_duplicate_within_file_and_timezone_equivalence(self):
        data = sample()
        duplicate = {**data["messages"][0], "id": "m4", "timestamp": "2026-01-02T04:00:00Z"}
        data["messages"].append(duplicate)
        report = self.run_import(data)
        self.assertEqual((report.success_count, report.duplicated_count), (3, 1))
        self.assert_balance(report)

    def test_existing_crud_message_is_deduplicated(self):
        service = ChatService(self.db)
        me = service.create_user("import_demo_me", "现有昵称")
        friend = service.create_user("import_demo_zhang", "张三")
        row = sample()["messages"][0]
        service.create_message(me.id, friend.id, row["content"], create_time=row["timestamp"])
        report = self.run_import(sample())
        self.assertEqual((report.success_count, report.duplicated_count), (2, 1))
        self.assertEqual(service.get_user(me.id).nickname, "现有昵称")
        self.assertTrue(report.warnings)

    def test_content_whitespace_newline_and_unicode_preserved(self):
        data = sample()
        data["messages"][0]["content"] = "  中文🙂\n'引号', 第二行  "
        self.run_import(data)
        self.assertEqual(ChatService(self.db).get_message(1).content, data["messages"][0]["content"])
        data["messages"][0]["content"] = data["messages"][0]["content"].strip()
        report = self.run_import(data)
        self.assertEqual((report.success_count, report.duplicated_count), (1, 2))

    def test_partial_error_reports_original_message_23(self):
        data = sample()
        template = data["messages"][0]
        data["messages"] = [{**template, "id": f"m{index}", "content": f"消息 {index}"} for index in range(1, 24)]
        del data["messages"][22]["sender_id"]
        report = self.run_import(data)
        self.assertEqual((report.status, report.success_count, report.failed_count), ("partial", 22, 1))
        issue = report.issues[0]
        self.assertEqual((issue.entity, issue.index, issue.field), ("message", 23, "sender_id"))
        self.assertIn("第23条消息失败：缺少发送者", issue.message)
        self.assert_balance(report)

    def test_invalid_fields_times_types_and_missing_refs(self):
        changes = [
            {"surprise": "bad"}, {"timestamp": "2026-01-02 12:00"}, {"timestamp": "2026-02-30T12:00:00Z"},
            {"timestamp": "2026-01-02T12:00:00.1234567Z"}, {"sender_id": "missing"},
            {"receiver_id": "missing"}, {"chat_id": "missing"}, {"type": "image"},
            {"content": "  "}, {"source_hash": "not-a-hash"}, {"content": "x\x00y"},
        ]
        for change in changes:
            with self.subTest(change=change):
                data = sample()
                data["messages"] = [{**data["messages"][0], **change}]
                report = self.run_import(data)
                self.assertEqual(report.failed_count, 1)
                self.assertTrue(report.issues)
                self.assert_balance(report)

    def test_user_chat_errors_and_private_membership(self):
        data = sample()
        data["users"][1]["unknown"] = "bad"
        report = self.run_import(data)
        self.assertEqual((report.users_failed_count, report.chats_failed_count, report.failed_count), (1, 1, 3))
        self.assertEqual(self.counts()["messages"], 0)
        data = sample()
        data["users"].append({"id": "other", "external_id": "other", "nickname": "别人"})
        data["messages"][0]["receiver_id"] = "other"
        report = self.run_import(data)
        self.assertEqual(report.failed_count, 1)
        self.assertEqual(report.issues[0].code, "chat_membership")

    def test_duplicate_ids_are_validation_errors(self):
        data = sample()
        data["users"].append(dict(data["users"][0]))
        data["chats"].append(dict(data["chats"][0]))
        data["messages"].append(dict(data["messages"][0]))
        report = self.run_import(data)
        self.assertEqual((report.users_failed_count, report.chats_failed_count, report.failed_count), (1, 1, 1))
        self.assertEqual(report.success_count, 3)

    def test_strict_validation_does_not_touch_existing_database(self):
        service = ChatService(self.db)
        service.create_user("keep", "保留")
        before = self.db.read_bytes()
        data = sample()
        del data["messages"][0]["sender_id"]
        report = JSONImporter(self.db, report_dir=self.logs, strict=True).import_file(self.write(data))
        self.assertEqual((report.status, report.success_count, report.failed_count), ("failed", 0, 3))
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(service.stats(), {"users": 1, "messages": 0})

    def test_empty_data_and_fatal_empty_file(self):
        data = sample()
        for key in ("users", "chats", "messages"):
            data[key] = []
        report = self.run_import(data)
        self.assertEqual((report.status, report.messages, report.success_count), ("success", 0, 0))
        self.file.write_text("", encoding="utf-8")
        report = self.importer.import_file(self.file)
        self.assertEqual(report.status, "failed")
        self.assertTrue(Path(report.report_path).exists())

    def test_malformed_root_and_duplicate_object_fields(self):
        for text in ("{}", "[]", "{", '{"format":"x","format":"y"}', '{"x":NaN}'):
            with self.subTest(text=text):
                self.file.write_text(text, encoding="utf-8")
                report = self.importer.import_file(self.file)
                self.assertEqual(report.status, "failed")
                self.assertTrue(Path(report.report_path).exists())
                self.assertFalse(self.db.exists())

    def test_json_bom_and_missing_file(self):
        self.file.write_text(json.dumps(sample(), ensure_ascii=False), encoding="utf-8-sig")
        self.assertEqual(self.importer.import_file(self.file).success_count, 3)
        report = self.importer.import_file(self.folder / "missing.json")
        self.assertEqual(report.status, "failed")

    def test_media_and_group_capability_are_explicit(self):
        data = sample()
        data["media"] = [{"id": "x", "type": "image", "uri": "photo.png"}]
        report = self.run_import(data)
        self.assertEqual(report.status, "failed")
        self.assertFalse(self.db.exists())
        self.assertIn("media", report.issues[0].message)
        data = sample()
        data["chats"][0]["type"] = "group"
        report = self.run_import(data)
        self.assertEqual((report.chats_failed_count, report.failed_count), (1, 3))

    def test_reserved_media_reference_is_explicit_and_empty_is_compatible(self):
        data = sample()
        data["messages"][0]["media_ids"] = []
        self.assertEqual(self.run_import(data).success_count, 3)
        data["messages"][0]["media_ids"] = ["photo1"]
        report = self.run_import(data)
        self.assertEqual((report.failed_count, report.duplicated_count), (1, 2))
        self.assertEqual(report.issues[0].code, "unsupported_media_refs")

    def test_chat_source_conflict_and_strict_rollback(self):
        self.run_import(sample())
        data = sample()
        data["users"][1]["external_id"] = "different_friend"
        before = self.counts()
        report = JSONImporter(self.db, report_dir=self.logs, strict=True).import_file(self.write(data))
        self.assertEqual(report.status, "failed")
        self.assertTrue(report.rolled_back)
        self.assertEqual(self.counts(), before)
        self.assertTrue(any(issue.code == "chat_source_conflict" for issue in report.issues))

    def test_storage_failure_rolls_back_whole_batch(self):
        service = ChatService(self.db)
        with service.database.connection() as conn:
            conn.execute("CREATE TRIGGER stop_import BEFORE INSERT ON messages BEGIN SELECT RAISE(ROLLBACK, 'stop'); END")
        report = self.run_import(sample())
        self.assertEqual((report.status, report.success_count, report.failed_count), ("failed", 0, 3))
        self.assertTrue(report.rolled_back)
        self.assertEqual(service.stats(), {"users": 0, "messages": 0})

    def test_report_directory_is_checked_before_database_writes(self):
        bad = self.folder / "not_a_directory"
        bad.write_text("keep", encoding="utf-8")
        with self.assertRaises(ReportWriteError):
            JSONImporter(self.db, report_dir=bad).import_file(self.write(sample()))
        self.assertFalse(self.db.exists())

    def test_adapter_only_needs_to_produce_exchange_document(self):
        class Adapter(BaseImporter):
            format_name = "future-adapter"
            def load(self, path):
                return LoadedDocument(sample())
        report = Adapter(self.db, report_dir=self.logs).import_file(self.folder / "future-source")
        self.assertEqual(report.success_count, 3)

    def test_hash_is_unambiguous_and_updated_on_crud_edits(self):
        self.assertNotEqual(message_hash(1, 23, "stamp", "x"), message_hash(12, 3, "stamp", "x"))
        self.run_import(sample())
        service = ChatService(self.db)
        old = service.get_message(1)
        changed = service.update_message(1, content="修改后的内容")
        self.assertNotEqual(old.message_hash, changed.message_hash)
        self.assertEqual(self.importer.import_file(self.file).success_count, 1)

    def test_imported_messages_visible_in_existing_browser_http_api(self):
        self.run_import(sample())
        server = make_server(self.db)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.01}, daemon=True)
        thread.start()
        try:
            with urlopen(server.url + "api/messages?user_id=1&peer_id=2") as response:
                data = json.load(response)
            self.assertEqual(data["total"], 3)
            self.assertEqual(data["items"][0]["content"], sample()["messages"][0]["content"])
            with urlopen(server.url + "api/contacts?user_id=1") as response:
                self.assertEqual(json.load(response)["items"][0]["message_count"], 3)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_bulk_50000_messages_and_repeat(self):
        data = sample()
        data["messages"] = [{**data["messages"][0], "id": f"bulk{index}", "content": f"批量消息 {index}"} for index in range(50000)]
        report = self.run_import(data)
        self.assertEqual((report.success_count, report.failed_count), (50000, 0))
        second = self.importer.import_file(self.file)
        self.assertEqual((second.success_count, second.duplicated_count), (0, 50000))
        self.assertEqual(self.counts()["messages"], 50000)
        print(f"\nBulk 50000: first={report.duration_seconds}s repeat={second.duration_seconds}s")


class CSVImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db, self.logs, self.file = self.folder / "chat.db", self.folder / "logs", self.folder / "chat.csv"

    def import_csv(self, rows, **options):
        with self.file.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time", "sender", "receiver", "content", "type"])
            writer.writerows(rows)
        return CSVImporter(self.db, report_dir=self.logs, **options).import_file(self.file)

    def test_csv_normal_quotes_multiline_and_repeat(self):
        content = '  你好,"朋友"\n第二行🙂  '
        rows = [["2026-01-01 12:00", "我", "张三", content, "text"], ["2026-01-01 12:01", "张三", "我", "回复", "text"]]
        first = self.import_csv(rows)
        second = CSVImporter(self.db, report_dir=self.logs).import_file(self.file)
        self.assertEqual((first.success_count, second.duplicated_count), (2, 2))
        message = ChatService(self.db).get_message(1)
        self.assertEqual(message.content, content)
        self.assertEqual(message.create_time.hour, 4)

    def test_header_only_and_invalid_headers(self):
        self.assertEqual(self.import_csv([]).status, "success")
        for text in ("", "time,sender,receiver,content\n", "time,time,receiver,content,type\n", "time,sender,receiver,content,type,extra\n"):
            self.file.write_text(text, encoding="utf-8")
            self.assertEqual(CSVImporter(self.db, report_dir=self.logs).import_file(self.file).status, "failed")

    def test_csv_invalid_rows_have_record_and_physical_line(self):
        report = self.import_csv([["bad-time", "我", "张三", "bad", "text"], ["2026-01-01 12:00", "", "张三", "bad", "text"], ["2026-01-01 12:01", "我", "张三", "好消息", "text"]])
        self.assertEqual((report.success_count, report.failed_count), (1, 2))
        self.assertEqual([(issue.index, issue.line) for issue in report.issues if issue.entity == "message"], [(1, 2), (2, 3)])

    def test_timezone_and_identity_namespaces(self):
        rows = [["2026-01-01 12:00", "我", "张三", "你好", "text"]]
        self.import_csv(rows, timezone="Z", namespace="account-a")
        report = self.import_csv(rows, timezone="Z", namespace="account-b")
        self.assertEqual(report.users_created_count, 2)
        self.assertEqual(ChatService(self.db).get_message(1).create_time.hour, 12)
        self.assertEqual(CSVImporter(self.db, report_dir=self.logs, timezone="Asia/Shanghai").import_file(self.file).status, "failed")

    def test_extra_columns_and_invalid_message_types(self):
        report = self.import_csv([["2026-01-01 12:00", "我", "张三", "内容", "image"], ["2026-01-01 12:01", "我", "张三", "内容", "text", "extra"]])
        self.assertEqual(report.failed_count, 2)

    def test_json_and_csv_share_the_same_dedup_logic(self):
        self.import_csv([["2026-01-02 12:00", "我", "张三", "相同消息", "text"]])
        data = sample()
        data["source"]["id"] = "json-account"
        data["users"][0]["external_id"] = "csv:default:%E6%88%91"
        data["users"][1]["external_id"] = "csv:default:%E5%BC%A0%E4%B8%89"
        data["messages"] = [{**data["messages"][0], "content": "相同消息"}]
        file = self.folder / "same.json"
        file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        report = JSONImporter(self.db, report_dir=self.logs).import_file(file)
        self.assertEqual((report.success_count, report.duplicated_count), (0, 1))


class ImportCLITests(unittest.TestCase):
    def test_module_import_alias_and_failure_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            db, logs = Path(folder) / "chat.db", Path(folder) / "logs"
            command = [sys.executable, "-m", "cli", "--db", str(db), "import", "examples/chat_sample.json", "--report-dir", str(logs)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["success"], 3)
            result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15)
            self.assertEqual(json.loads(result.stdout)["duplicated_count"], 3)
            command[command.index("examples/chat_sample.json")] = str(Path(folder) / "missing.json")
            result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
