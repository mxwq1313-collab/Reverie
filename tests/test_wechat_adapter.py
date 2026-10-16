import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wechat_archive import ChatService
from wechat_archive.importer import JSONImporter
from wechat_archive.importer.records import LoadedDocument
from wechat_archive.importer.validator import DocumentError, validate_document
from wechat_archive.wechat_adapter import AndroidAdapter, BackupAdapter, MockWeChatAdapter, WeChatBackupParser, WeChatImporter, detect_source
from wechat_archive.wechat_adapter.mapper import map_mock_export, map_timestamp

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "wechat_mock" / "export.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db, self.logs, self.file = self.folder / "chat.db", self.folder / "logs", self.folder / "export.json"

    def write(self, data):
        self.file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return self.file

    def importing(self, data, **options):
        return WeChatImporter(self.db, report_dir=self.logs, **options).import_file(self.write(data))

    def test_mock_conversion_returns_loaded_document_and_valid_standard(self):
        loaded = MockWeChatAdapter().load(FIXTURE)
        self.assertIsInstance(loaded, LoadedDocument)
        self.assertEqual((loaded.payload["format"], loaded.payload["format_version"]), ("chat-exchange", "1.0"))
        self.assertEqual((len(loaded.payload["users"]), len(loaded.payload["chats"]), len(loaded.payload["messages"])), (3, 2, 5))
        self.assertEqual(validate_document(loaded.payload).issues, [])

    def test_field_mapping_identity_content_and_source_id(self):
        raw = fixture()
        raw["messages"][0]["msgId"] = 123
        raw["messages"][0]["content"] = "  中文🙂\n原文 '引号'  "
        loaded = map_mock_export(raw).payload
        message = loaded["messages"][0]
        self.assertEqual((message["id"], message["source_id"]), ("123", "123"))
        self.assertEqual(message["content"], raw["messages"][0]["content"])
        self.assertEqual(message["type"], "text")
        user = next(user for user in loaded["users"] if user["id"] == raw["messages"][0]["talker"])
        self.assertEqual(user["external_id"], "wechat-mock:wxid_mock_me:wxid_mock_zhang")
        self.assertEqual(loaded["source"]["metadata"]["adapter"], "wechat-mock")

    def test_seconds_and_milliseconds_are_explicit_and_precise(self):
        self.assertEqual(map_timestamp(1767499200), "2026-01-04T04:00:00.000000Z")
        self.assertEqual(map_timestamp("1767499200123", "milliseconds"), "2026-01-04T04:00:00.123000Z")
        self.assertEqual(map_timestamp(-1, "milliseconds"), "1969-12-31T23:59:59.999000Z")
        raw = fixture()
        raw["timeUnit"] = "milliseconds"
        for row in raw["messages"]:
            row["createTime"] *= 1000
        self.assertEqual(map_mock_export(raw).payload["messages"][0]["timestamp"], "2026-01-04T04:00:00.000000Z")
        for value, unit in ((True, "seconds"), (1.2, "seconds"), ("not-time", "seconds"), (10**30, "seconds"), (1, "auto")):
            with self.subTest(value=value, unit=unit), self.assertRaises(DocumentError):
                map_timestamp(value, unit)

    def test_bidirectional_sender_receiver_and_self_notes(self):
        data = fixture()
        mapped = map_mock_export(data).payload
        self.assertEqual((mapped["messages"][0]["sender_id"], mapped["messages"][0]["receiver_id"]), ("wxid_mock_me", "wxid_mock_zhang"))
        self.assertEqual((mapped["messages"][1]["sender_id"], mapped["messages"][1]["receiver_id"]), ("wxid_mock_zhang", "wxid_mock_me"))
        data["messages"] = [{**data["messages"][0], "talker": "wxid_mock_me"}]
        self.assertEqual(validate_document(map_mock_export(data).payload).issues, [])

    def test_import_reuses_existing_dedup_and_report(self):
        first = self.importing(fixture())
        second = WeChatImporter(self.db, report_dir=self.logs).import_file(self.file)
        self.assertEqual((first.success_count, second.success_count, second.duplicated_count), (5, 0, 5))
        self.assertEqual(ChatService(self.db).stats(), {"users": 3, "messages": 5})
        self.assertEqual(second.format, "wechat")
        self.assertTrue(Path(second.report_path).is_file())
        self.assertEqual(len(list(self.logs.glob("*.json"))), 2)
        self.assertEqual(first.messages, first.success_count + first.failed_count + first.duplicated_count)

    def test_adapter_and_standard_json_share_dedup(self):
        self.importing(fixture())
        file = self.folder / "exchange.json"
        file.write_text(json.dumps(MockWeChatAdapter().load(FIXTURE).payload), encoding="utf-8")
        report = JSONImporter(self.db, report_dir=self.logs).import_file(file)
        self.assertEqual((report.success_count, report.duplicated_count), (0, 5))

    def test_batch_duplicate_with_new_msg_id_is_skipped(self):
        data = fixture()
        data["messages"].append({**data["messages"][0], "msgId": "duplicate-new-id"})
        report = self.importing(data)
        self.assertEqual((report.success_count, report.duplicated_count), (5, 1))

    def test_account_namespace_prevents_cross_account_merges(self):
        self.importing(fixture())
        data = fixture()
        data["account"]["wxid"] = "different-account"
        report = self.importing(data)
        self.assertEqual((report.users_created_count, report.success_count), (3, 5))
        self.assertEqual(ChatService(self.db).stats(), {"users": 6, "messages": 10})

    def test_wrong_format_is_rejected_with_report_and_no_database(self):
        cases = [[], {}, {**fixture(), "format":"chat-exchange"}, {**fixture(), "format_version":"2.0"}, {**fixture(), "contacts":None}, {**fixture(), "unknown":"x"}]
        for data in cases:
            with self.subTest(data=data):
                report = self.importing(data)
                self.assertEqual(report.status, "failed")
                self.assertTrue(Path(report.report_path).is_file())
                self.assertFalse(self.db.exists())

    def test_missing_message_fields_and_ambiguous_direction_rejected(self):
        for change in ({"isSend":True}, {"isSend":2}, {"isSend":"1"}, {"talker":"missing"}, {"createTime":False}, {"unknown":"bad"}):
            data = fixture()
            data["messages"][1].update(change)
            with self.subTest(change=change):
                report = self.importing(data)
                self.assertEqual(report.status, "failed")
                self.assertIn("第2条微信模拟消息映射失败", report.issues[0].message)
                self.assertFalse(self.db.exists())
        data = fixture()
        del data["messages"][0]["msgId"]
        self.assertEqual(self.importing(data).status, "failed")

    def test_unsupported_message_type_goes_to_original_validator(self):
        data = fixture()
        data["messages"][0]["type"] = 3
        report = self.importing(data)
        self.assertEqual((report.status, report.success_count, report.failed_count), ("partial", 4, 1))
        self.assertEqual(report.issues[0].code, "unsupported_message_type")

    def test_strict_mode_remains_existing_import_behavior(self):
        data = fixture()
        data["messages"][0]["type"] = "image"
        report = self.importing(data, strict=True)
        self.assertEqual((report.status, report.success_count, report.failed_count), ("failed", 0, 5))
        self.assertFalse(self.db.exists())

    def test_detector_file_directory_and_missing_path(self):
        self.write(fixture())
        self.assertTrue(detect_source(self.file).supported)
        self.assertTrue(detect_source(self.folder).supported)
        self.assertEqual(detect_source(self.folder / "missing").kind, "missing")
        self.file.write_text("{", encoding="utf-8")
        self.assertEqual(detect_source(self.file).kind, "invalid")

    def test_real_sources_are_metadata_only_and_cannot_be_forced(self):
        database = self.folder / "EnMicroMsg.db"
        database.write_bytes(b"not a database; keep unchanged")
        backup = self.folder / "BackupFiles"
        backup.mkdir()
        before = database.read_bytes()
        with patch("pathlib.Path.open", side_effect=AssertionError("real source must not be opened")):
            self.assertEqual(detect_source(database).kind, "android-db")
            self.assertEqual(detect_source(backup).kind, "pc-backup")
            self.assertTrue(AndroidAdapter().detect(database))
            self.assertTrue(BackupAdapter().detect(backup))
            with self.assertRaises(DocumentError):
                AndroidAdapter().load(database)
            with self.assertRaises(DocumentError):
                BackupAdapter().load(backup)
        self.assertEqual(database.read_bytes(), before)
        for adapter in ("auto", "android", "backup"):
            report = WeChatImporter(self.db, adapter=adapter, report_dir=self.logs).import_file(database)
            self.assertEqual(report.status, "failed")
            self.assertFalse(self.db.exists())

    def test_backup_parser_interface_is_reserved_and_abstract(self):
        with self.assertRaises(TypeError):
            WeChatBackupParser(self.file)
        for name in ("detect", "extract_users", "extract_messages", "export_exchange"):
            self.assertTrue(hasattr(WeChatBackupParser, name))

    def test_empty_contacts_and_messages_are_supported(self):
        data = fixture()
        data["contacts"], data["messages"] = [], []
        report = self.importing(data)
        self.assertEqual((report.status, report.users_created_count, report.success_count), ("success", 1, 0))


class WeChatCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db, self.logs = self.folder / "chat.db", self.folder / "logs"

    def cli(self, args, code=0, stderr=False):
        result = subprocess.run([sys.executable, "-m", "cli", "--db", str(self.db), "wechat", *args], cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, code, result.stderr)
        return json.loads(result.stderr if stderr else result.stdout)

    def test_cli_import_report_and_duplicate_counts(self):
        args = ["import", "wechat_mock/export.json", "--report-dir", str(self.logs)]
        self.assertEqual(self.cli(args)["success_count"], 5)
        self.assertEqual(self.cli(args)["duplicated_count"], 5)

    def test_cli_convert_and_detect_do_not_create_database(self):
        self.assertTrue(self.cli(["detect", "wechat_mock/export.json"])["supported"])
        output = self.folder / "exchange.json"
        self.assertEqual(self.cli(["convert", "wechat_mock/export.json", "--output", str(output)])["messages"], 5)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["format"], "chat-exchange")
        self.assertEqual(self.cli(["convert", "wechat_mock/export.json"])["format_version"], "1.0")
        self.assertFalse(self.db.exists())

    def test_convert_preserves_existing_output_and_source(self):
        target = self.folder / "existing.json"
        target.write_text("keep", encoding="utf-8")
        self.assertEqual(self.cli(["convert", "wechat_mock/export.json", "--output", str(target)], code=1, stderr=True)["error"]["type"], "ConflictError")
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        before = FIXTURE.read_bytes()
        self.cli(["convert", str(FIXTURE), "--output", str(FIXTURE)], code=1, stderr=True)
        self.assertEqual(FIXTURE.read_bytes(), before)

    def test_cli_unsupported_source_is_failure_report(self):
        source = self.folder / "EnMicroMsg.db"
        source.write_bytes(b"untouched")
        report = self.cli(["import", str(source), "--report-dir", str(self.logs)], code=1)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(Path(report["report_path"]).is_file())
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
