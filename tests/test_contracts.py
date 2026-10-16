"""Domain/capability and scoped citation contract tests; synthetic data only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

import test_external_source as fixture
from wechat_archive import ChatService, ConflictError, NotFoundError, ValidationError
from wechat_archive.agent import ArchiveScope, ArchiveTools
from wechat_archive.models import ImportBatch, MediaRef, MessageKind, MessageRecord, MessageRef, ParseStatus, SourceCapabilities, SourceRef
from wechat_archive.wechat_adapter import WeChatImporter
from wechat_archive.wechat_adapter.android_adapter import AndroidAdapter
from wechat_archive.wechat_adapter.backup_adapter import BackupAdapter
from wechat_archive.wechat_adapter.external_adapter import ExternalExportAdapter
from wechat_archive.wechat_adapter.mock_adapter import MockWeChatAdapter


class DomainContractTests(unittest.TestCase):
    def record(self, **changes):
        values = dict(record_id="synthetic-message", chat_id="synthetic-chat", sender_id="owner", receiver_id="peer",
                      timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc), kind=MessageKind.TEXT,
                      original_text="  original\n中文🙂  ", source_ref=SourceRef("synthetic"))
        values.update(changes)
        return MessageRecord(**values)

    def test_original_text_whitespace_unicode_preserved(self):
        self.assertEqual(self.record().original_text, "  original\n中文🙂  ")

    def test_aware_time_normalized_without_changing_instant(self):
        record = self.record(timestamp_utc=datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8))))
        self.assertEqual(record.timestamp_utc.isoformat(), "2026-01-01T00:00:00+00:00")

    def test_naive_time_rejected(self):
        with self.assertRaises(ValidationError):
            self.record(timestamp_utc=datetime(2026, 1, 1))

    def test_text_requires_original_not_placeholder(self):
        for value in (None, "", "   "):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.record(original_text=value)

    def test_group_domain_has_chat_and_sender_without_receiver(self):
        self.assertIsNone(self.record(chat_kind="group", receiver_id=None).receiver_id)

    def test_private_domain_requires_receiver(self):
        with self.assertRaises(ValidationError):
            self.record(receiver_id=None)

    def test_future_domain_types_do_not_enable_current_adapter(self):
        caps = ExternalExportAdapter().describe_capabilities()
        for kind in (MessageKind.IMAGE, MessageKind.VIDEO, MessageKind.AUDIO, MessageKind.FILE, MessageKind.LOCATION, MessageKind.SYSTEM):
            with self.subTest(kind=kind):
                self.assertFalse(caps.supports(self.record(kind=kind, original_text=None)))
        self.assertFalse(caps.supports(self.record(chat_kind="group", receiver_id=None)))

    def test_unsupported_status_not_promoted_to_accepted(self):
        caps = ExternalExportAdapter().describe_capabilities()
        self.assertFalse(caps.supports(self.record(parse_status=ParseStatus.UNSUPPORTED)))

    def test_stable_source_ref_requires_its_id_scope(self):
        with self.assertRaises(ValidationError):
            SourceRef("synthetic", source_id="1", id_kind="local")
        self.assertEqual(SourceRef("synthetic", "1", "owner", "chat", "shard", "local").shard, "shard")

    def test_unknown_source_id_kind_rejected(self):
        with self.assertRaises(ValidationError):
            SourceRef("synthetic", id_kind="guessed")

    def test_unknown_kind_and_parse_status_are_contract_errors(self):
        for changes in ({"kind": "unknown"}, {"parse_status": "guessed"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.record(**changes)

    def test_invalid_capability_declarations_are_rejected(self):
        for changes in ({"profiles": "profile"}, {"chat_kinds": ("unknown",)}, {"streaming": True}, {"synthetic": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                SourceCapabilities("synthetic", **changes)

    def test_media_missing_stays_missing(self):
        self.assertEqual(MediaRef("media", MessageKind.IMAGE).availability, "missing")

    def test_ready_media_requires_resource_evidence(self):
        with self.assertRaises(ValidationError):
            MediaRef("media", MessageKind.IMAGE, availability="ready")
        self.assertEqual(MediaRef("media", MessageKind.IMAGE, "assets/a.png", "a" * 64, 0, "ready").relative_uri, "assets/a.png")

    def test_media_paths_cannot_escape_or_be_remote(self):
        for value in ("../outside", "/absolute", "C:/outside", "https://example.com/a", "assets\\file", ".", "assets/\nfile"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                MediaRef("media", MessageKind.FILE, relative_uri=value)

    def test_legacy_batch_cannot_claim_cursor_or_nonfinal(self):
        caps = ExternalExportAdapter().describe_capabilities()
        for changes in ({"next_cursor": "offset1"}, {"is_final": False}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ImportBatch("snapshot", "batch", (self.record(),), caps, **changes)

    def test_batch_requires_supported_records(self):
        with self.assertRaises(ValidationError):
            ImportBatch("snapshot", "batch", (self.record(chat_kind="group", receiver_id=None),), ExternalExportAdapter().describe_capabilities())

    def test_batch_cannot_accept_untyped_records(self):
        with self.assertRaises(ValidationError):
            ImportBatch("snapshot", "batch", ({"content": "fake"},), ExternalExportAdapter().describe_capabilities())

    def test_mock_android_backup_external_capabilities_are_specific(self):
        self.assertTrue(MockWeChatAdapter().describe_capabilities().synthetic)
        self.assertFalse(AndroidAdapter().describe_capabilities().stable_source_identity)
        self.assertIn("已解密", AndroidAdapter().describe_capabilities().input_requirement)
        self.assertTrue(BackupAdapter().describe_capabilities().inspection)
        self.assertEqual(BackupAdapter().describe_capabilities().message_kinds, ())
        self.assertTrue(ExternalExportAdapter().describe_capabilities().stable_source_identity)
        self.assertFalse(ExternalExportAdapter().describe_capabilities().streaming)
        self.assertEqual(json.loads(json.dumps(ExternalExportAdapter().describe_capabilities().to_dict()))["message_kinds"], ["text"])


class AdapterBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "source.json"
        self.path.write_text(json.dumps(fixture.data(), ensure_ascii=False), encoding="utf-8")

    def test_external_batch_has_original_records_source_and_final_marker(self):
        before = self.path.read_bytes()
        batches = list(ExternalExportAdapter().iter_batches(self.path))
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].records), 2)
        self.assertTrue(batches[0].is_final)
        self.assertIsNone(batches[0].next_cursor)
        self.assertEqual(batches[0].records[0].source_ref.shard, "message_0")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.folder / "archive.db").exists())

    def test_same_payload_has_same_batch_id(self):
        adapter = ExternalExportAdapter()
        self.assertEqual(next(adapter.iter_batches(self.path)).batch_id, next(adapter.iter_batches(self.path)).batch_id)

    def test_legacy_bridge_rejects_unverified_resume_and_overbudget(self):
        for options in ({"cursor": "offset=2"}, {"max_messages": 1}, {"max_messages": True}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                list(ExternalExportAdapter().iter_batches(self.path, **options))

    def test_import_report_exposes_host_capabilities(self):
        report = WeChatImporter(self.folder / "archive.db", report_dir=self.folder / "logs").import_file(self.path)
        self.assertEqual(report.source_capabilities["adapter"], "external")
        self.assertEqual(report.source_capabilities["message_kinds"], ["text"])


class CitationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "archive.db"
        self.service = ChatService(self.path)
        for i in range(3):
            self.service.create_user(wxid="citation_unit_" + str(i), nickname="synthetic")
        self.service.create_message(sender_id=1, receiver_id=2, content="source text", create_time="2026-01-01T00:00:00Z")
        self.tools = ArchiveTools(ArchiveScope(self.path, 1, 2))

    def reference(self):
        return self.tools.archive_message(1)["item"]["reference"]

    def test_reference_resolves_original_in_authorized_scope(self):
        ref = self.reference()
        self.assertEqual(self.tools.resolve_reference(ref)["content"], "source text")
        self.assertEqual(MessageRef.from_dict(ref).to_dict(), ref)

    def test_content_edit_invalidates_existing_reference(self):
        ref = self.reference()
        self.service.update_message(1, content="edited")
        with self.assertRaises(ConflictError):
            self.tools.resolve_reference(ref)

    def test_deleted_message_cannot_be_resolved(self):
        ref = self.reference()
        self.service.delete_message(1)
        with self.assertRaises(NotFoundError):
            self.tools.resolve_reference(ref)

    def test_another_scope_cannot_expand_citation(self):
        with self.assertRaises(NotFoundError):
            ArchiveTools(ArchiveScope(self.path, 1, 3)).resolve_reference(self.reference())

    def test_another_archive_cannot_reuse_message_number(self):
        other = self.root / "other.db"
        service = ChatService(other)
        for i in range(2):
            service.create_user(wxid="other_unit_" + str(i), nickname="synthetic")
        service.create_message(sender_id=1, receiver_id=2, content="source text", create_time="2026-01-01T00:00:00Z")
        with self.assertRaises(ConflictError):
            ArchiveTools(ArchiveScope(other, 1, 2)).resolve_reference(self.reference())

    def test_replaced_archive_invalidates_references(self):
        ref = self.reference()
        replacement = self.root / "replacement.db"
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        with self.assertRaises(ConflictError):
            self.tools.resolve_reference(ref)

    def test_invalid_fields_and_message_types_are_rejected(self):
        for changes in ({"path": "other.db"}, {"message_id": True}, {"revision": "unknown"}):
            ref = {**self.reference(), **changes}
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.tools.resolve_reference(ref)

    def test_reference_does_not_disclose_path_and_uses_untruncated_text(self):
        self.service.update_message(1, content="synthetic" * 2000)
        short = self.tools.archive_message(1, content_limit=10)["item"]
        full = self.tools.archive_message(1)["item"]
        self.assertEqual(short["reference"], full["reference"])
        self.assertNotIn(str(self.path), json.dumps(short["reference"]))


if __name__ == "__main__":
    unittest.main()
