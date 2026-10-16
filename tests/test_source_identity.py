"""Stable-source import regression, using synthetic provider fixtures only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_external_source as fixture
from wechat_archive import ChatService
from wechat_archive.importer import JSONImporter
from wechat_archive.wechat_adapter import WeChatImporter


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "archive.db"
        self.logs = self.root / "logs"

    def payload(self, local=1, content="same synthetic message", shard="message_0", owner=None, peer=None):
        payload = fixture.data()
        if owner:
            payload["account"]["wxid"] = owner
        if peer:
            payload["conversation"]["wxid"] = peer
        payload["records"] = [fixture.record(local, payload["account"]["wxid"], 1767225600, content, shard=shard)]
        return payload

    def importing(self, payload, strict=False):
        path = self.root / "source.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return WeChatImporter(self.db, report_dir=self.logs, adapter="external", strict=strict).import_file(path)

    def rows(self):
        with ChatService(self.db).database.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM messages ORDER BY id")]

    def test_distinct_source_same_content_across_batches_preserved(self):
        first = self.importing(self.payload(1))
        second = self.importing(self.payload(2))
        self.assertEqual((first.success_count, second.success_count, second.duplicated_count), (1, 1, 0))
        self.assertEqual(len(self.rows()), 2)

    def test_distinct_source_same_content_in_one_batch_preserved(self):
        payload = self.payload()
        payload["records"].append(self.payload(2)["records"][0])
        report = self.importing(payload)
        self.assertEqual((report.success_count, report.failed_count, report.duplicated_count), (2, 0, 0))

    def test_exact_source_repeat_after_new_importer_is_duplicate(self):
        self.importing(self.payload())
        report = self.importing(self.payload())
        self.assertEqual((report.success_count, report.duplicated_count), (0, 1))

    def test_same_source_content_change_reports_conflict_without_overwrite(self):
        self.importing(self.payload())
        before = self.rows()
        report = self.importing(self.payload(content="changed synthetic message"))
        self.assertEqual((report.success_count, report.failed_count), (0, 1))
        self.assertIn("source_identity_conflict", [issue.code for issue in report.issues])
        self.assertEqual(self.rows(), before)

    def test_same_source_timestamp_change_is_conflict(self):
        self.importing(self.payload())
        payload = self.payload()
        row = payload["records"][0]
        row["timestamp"] += 1
        row["raw_payload"]["database_row"]["create_time"] += 1
        report = self.importing(payload)
        self.assertEqual(report.failed_count, 1)

    def test_same_source_sender_change_is_conflict(self):
        self.importing(self.payload())
        payload = self.payload()
        row = payload["records"][0]
        row["sender_wxid"] = payload["conversation"]["wxid"]
        row["raw_payload"]["database_row"]["sender_username"] = row["sender_wxid"]
        report = self.importing(payload)
        self.assertIn("source_identity_conflict", [issue.code for issue in report.issues])

    def test_same_local_number_different_shard_is_distinct(self):
        self.importing(self.payload())
        report = self.importing(self.payload(shard="message_1"))
        self.assertEqual((report.success_count, report.duplicated_count), (1, 0))

    def test_different_account_namespace_is_distinct(self):
        self.importing(self.payload())
        report = self.importing(self.payload(owner="wxid_unit_other"))
        self.assertEqual(report.success_count, 1)
        self.assertEqual(len(self.rows()), 2)

    def test_different_conversation_is_distinct(self):
        self.importing(self.payload())
        report = self.importing(self.payload(peer="wxid_unit_other"))
        self.assertEqual(report.success_count, 1)

    def test_local_and_server_id_kinds_are_distinct(self):
        self.importing(self.payload())
        payload = self.payload()
        row = payload["records"][0]
        row["source_id_kind"] = "local"
        row["source_message_id"] = str(row["local_id"])
        report = self.importing(payload)
        self.assertEqual(report.success_count, 1)

    def test_duplicate_existing_source_keys_are_ambiguous(self):
        self.importing(self.payload())
        with ChatService(self.db).database.connection() as conn:
            conn.execute("INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,chat_id,message_hash,source,source_id,source_hash,external_id) SELECT sender_id,receiver_id,create_time,content,msg_type,chat_id,message_hash,source,source_id,source_hash,external_id FROM messages")
        report = self.importing(self.payload())
        self.assertEqual(report.failed_count, 1)
        self.assertIn("source_identity_ambiguous", [issue.code for issue in report.issues])
        self.assertEqual(len(self.rows()), 2)

    def test_legacy_collision_reported_without_silent_merge(self):
        self.importing(self.payload())
        with ChatService(self.db).database.connection() as conn:
            conn.execute("UPDATE messages SET source=NULL,source_id=NULL,external_id=NULL")
        report = self.importing(self.payload(2))
        self.assertEqual((report.success_count, report.duplicated_count, report.failed_count), (0, 0, 1))
        self.assertIn("legacy_identity_ambiguous", [issue.code for issue in report.issues])
        self.assertEqual(len(self.rows()), 1)

    def test_strict_conflict_rolls_back_other_new_messages(self):
        self.importing(self.payload())
        payload = self.payload(2, content="new message")
        payload["records"].append(self.payload(content="conflicting message")["records"][0])
        report = self.importing(payload, strict=True)
        self.assertTrue(report.rolled_back)
        self.assertEqual(report.success_count, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_crud_edit_of_source_message_causes_conflict(self):
        self.importing(self.payload())
        service = ChatService(self.db)
        service.update_message(self.rows()[0]["id"], content="user edited text")
        report = self.importing(self.payload())
        self.assertEqual(report.failed_count, 1)
        self.assertEqual(self.rows()[0]["content"], "user edited text")

    def test_raw_capture_metadata_change_without_content_change_is_duplicate(self):
        self.importing(self.payload())
        payload = self.payload()
        payload["records"][0]["raw_payload"]["native"]["capture_note"] = "new capture"
        report = self.importing(payload)
        self.assertEqual((report.duplicated_count, report.failed_count), (1, 0))

    def test_json_metadata_cannot_enable_source_identity_policy(self):
        payload = json.loads((Path(__file__).resolve().parents[1] / "examples/chat_sample.json").read_text(encoding="utf-8"))
        payload["source"]["metadata"] = {"identity_strategy": "source-id-v1"}
        path = self.root / "standard.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        first = JSONImporter(self.db, report_dir=self.logs).import_file(path)
        second = JSONImporter(self.db, report_dir=self.logs).import_file(path)
        self.assertEqual((first.success_count, second.duplicated_count), (3, 3))
        self.assertEqual(second.identity_strategy, "legacy-content")

    def test_report_records_strategy_without_changing_schema(self):
        report = self.importing(self.payload())
        self.assertEqual(report.to_dict()["identity_strategy"], "source-id-v1")
        with ChatService(self.db).database.connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
