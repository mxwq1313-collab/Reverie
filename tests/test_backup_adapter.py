"""全为自建 RMFH 外壳；不使用用户备份、密钥或聊天正文。"""

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from wechat_archive import ChatService, Database
from wechat_archive.importer.validator import DocumentError
from wechat_archive.ui.import_controller import FORMAT_LABELS, ImportController
from wechat_archive.ui.import_window import ImportWindow
from wechat_archive.wechat_adapter import BackupAdapter, WeChatImporter, detect_source
from wechat_archive.wechat_adapter.backup import RMFHBackupParser
from wechat_archive.wechat_adapter.backup.decryptor import BackupDecryptor, UnavailableBackupDecryptor
from wechat_archive.wechat_adapter.backup.reader import read_envelope, read_edges

ROOT = Path(__file__).resolve().parents[1]


def envelope(payload=b"synthetic non-message bytes", *, count=1, flags=0x101, reserved=0):
    return struct.pack("<4sIHHI", b"RMFH", 123, count, flags, reserved)+bytes(112)+payload+b"RMFT"+bytes(124)


def fixture(root, device_name="device_synthetic", *, batch="1"):
    device = root / "wxid_synthetic" / device_name
    device.mkdir(parents=True, exist_ok=True)
    (device.parent / "roam_device_info.dat").write_bytes(b"synthetic metadata; no keys")
    (device / "backup.attr").write_bytes(envelope(bytes(2)))
    for name in ("ChatPackage", "Index", "Media"):
        folder = device / "files" / batch / "session_synthetic" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ("1767225600000-1767225600000" if name == "ChatPackage" else "synthetic.dat")).write_bytes(envelope())
    return device


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "backup"
        self.device = fixture(self.source)
        self.package = self.device / "files/1/session_synthetic/ChatPackage/1767225600000-1767225600000"
        self.db, self.logs = self.folder / "archive.db", self.folder / "logs"

    def inspect(self, source=None):
        return RMFHBackupParser(source or self.source).inspect()

    def importing(self, **options):
        return WeChatImporter(self.db, report_dir=self.logs, **options).import_file(self.source)

    def test_root_is_structurally_recognized_but_not_import_supported(self):
        found = detect_source(self.source)
        self.assertEqual(found.kind, "pc-backup")
        self.assertFalse(found.supported)
        self.assertEqual(self.inspect().inspection_status, "recognized")

    def test_account_directory_detection(self):
        self.assertTrue(RMFHBackupParser.detect(self.device.parent))

    def test_device_directory_detection(self):
        self.assertTrue(RMFHBackupParser.detect(self.device))

    def test_backup_attr_selection(self):
        self.assertEqual(self.inspect(self.device / "backup.attr").format, "wechat-rmfh-backup")

    def test_batch_selection_keeps_selected_scope(self):
        fixture(self.source, batch="2")
        report = self.inspect(self.device / "files/1")
        self.assertEqual((report.batch_directories, report.chat_package_files), (1, 1))

    def test_multiple_devices_are_counted_without_identity_guessing(self):
        fixture(self.source, "second_device")
        report = self.inspect()
        self.assertEqual((report.device_directories, report.chat_package_files), (2, 2))
        self.assertIsNone(report.message_count)

    def test_empty_account_does_not_mask_valid_backup(self):
        (self.source / "wxid_empty").mkdir()
        self.assertEqual(self.inspect().device_directories, 1)

    def test_counts_are_files_and_not_messages(self):
        report = self.inspect()
        self.assertEqual((report.files, report.chat_package_files, report.index_files, report.media_files), (5, 1, 1, 1))
        self.assertEqual(report.bytes, sum(p.stat().st_size for p in self.source.rglob('*') if p.is_file()))
        self.assertIsNone(report.message_count)
        self.assertFalse(report.content_decoded)
        self.assertEqual(report.encryption_status, "not_verified")

    def test_correct_head_tail_and_payload_boundaries(self):
        decoded = read_envelope(self.package)
        self.assertEqual((decoded['payload_offset'], decoded['payload_bytes']), (128, len(b"synthetic non-message bytes")))

    def test_non_rmfh_message_package_rejected(self):
        self.package.write_bytes(b"unknown format")
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_truncated_container_rejected(self):
        self.package.write_bytes(envelope()[:240])
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_invalid_footer_rejected(self):
        self.package.write_bytes(envelope()[:-128]+bytes(128))
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_unknown_header_count_rejected(self):
        self.package.write_bytes(envelope(count=2))
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_unknown_header_flags_rejected(self):
        self.package.write_bytes(envelope(flags=0x102))
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_unknown_reserved_header_rejected(self):
        self.package.write_bytes(envelope(reserved=1))
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_invalid_backup_attr_rejected(self):
        (self.device / "backup.attr").write_bytes(b"unknown")
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_missing_message_packages_rejected(self):
        self.package.unlink()
        self.assertEqual(self.inspect().inspection_status, "invalid")

    def test_active_backup_lock_is_rejected(self):
        (self.device / 'files/1/pkg.lock').write_bytes(b'')
        report = self.inspect()
        self.assertEqual(report.inspection_status, 'invalid')
        self.assertIn('pkg.lock', report.reason)

    def test_empty_directory_is_unknown(self):
        empty = self.folder / "empty"
        empty.mkdir()
        self.assertEqual(self.inspect(empty).inspection_status, "unsupported")

    def test_missing_directory_rejected(self):
        with self.assertRaisesRegex(DocumentError, "不存在"):
            RMFHBackupParser(self.folder / "missing")

    def test_source_path_traversal_and_uri_rejected(self):
        for value in ("file:///D:/backup", "../backup", "\\\\server\\backup", "bad\npath"):
            with self.subTest(value=value), self.assertRaises(DocumentError):
                RMFHBackupParser(value)

    def test_symlink_to_backup_rejected(self):
        link = self.folder / "linked"
        try:
            link.symlink_to(self.source, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        with self.assertRaises(DocumentError):
            RMFHBackupParser(link)

    def test_source_change_during_edge_read_rejected(self):
        stamp = (self.package.stat().st_size, self.package.stat().st_mtime_ns, self.package.stat().st_ino)
        with patch('wechat_archive.wechat_adapter.backup.reader.file_stamp', side_effect=[stamp, (stamp[0], stamp[1]+1, stamp[2])]):
            with self.assertRaisesRegex(DocumentError, "变化"):
                read_edges(self.package)

    def test_content_extraction_never_returns_empty_success(self):
        parser = RMFHBackupParser(self.source)
        for method in (parser.extract_users, parser.extract_messages, parser.export_exchange):
            with self.assertRaisesRegex(DocumentError, "正文尚未解码"):
                method()

    def test_inspection_and_failed_import_preserve_source_bytes(self):
        before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.inspect()
        self.importing()
        after = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_failed_import_has_structured_inspection_report(self):
        report = self.importing()
        self.assertEqual((report.status, report.success_count, report.messages), ("failed", 0, 0))
        self.assertEqual(report.issues[0].code, "backup_content_unavailable")
        self.assertEqual(report.source_metadata['backup_inspection']['chat_package_files'], 1)
        self.assertIsNone(report.source_metadata['backup_inspection']['message_count'])
        self.assertFalse(self.db.exists())

    def test_forced_backup_adapter_cannot_bypass_missing_decoder(self):
        self.assertEqual(self.importing(adapter="backup").status, "failed")
        self.assertFalse(self.db.exists())

    def test_existing_archive_is_byte_identical_after_failure(self):
        service = ChatService(self.db)
        service.create_user("wxid_keep", "保留")
        before = self.db.read_bytes()
        self.importing()
        self.assertEqual(self.db.read_bytes(), before)

    def test_report_directory_inside_source_rejected_before_creation(self):
        logs = self.source / "new_logs"
        with self.assertRaisesRegex(DocumentError, "报告"):
            WeChatImporter(self.db, report_dir=logs).import_file(self.source)
        self.assertFalse(logs.exists())

    def test_archive_inside_source_rejected_before_creation(self):
        target = self.source / "new_archive.db"
        with self.assertRaisesRegex(DocumentError, "目标归档库"):
            WeChatImporter(target, report_dir=self.logs).import_file(self.source)
        self.assertFalse(target.exists())

    def test_nested_selection_still_protects_account_directory(self):
        logs = self.device.parent / "new_logs"
        with self.assertRaises(DocumentError):
            WeChatImporter(self.db, report_dir=logs).import_file(self.device / "files/1")
        self.assertFalse(logs.exists())

    def test_saved_inspection_is_utf8_and_distinct(self):
        report = self.inspect()
        first = report.save(self.logs)
        second = report.save(self.logs)
        self.assertNotEqual(first, second)
        self.assertFalse(json.loads(first.read_text(encoding="utf-8"))['import_supported'])

    def test_inspection_report_cannot_write_inside_source(self):
        with self.assertRaises(DocumentError):
            self.inspect(self.device / "backup.attr").save(self.device.parent / "logs")
        self.assertFalse((self.device.parent / "logs").exists())

    def test_decryption_interface_stays_separate_and_unavailable(self):
        with self.assertRaises(TypeError):
            BackupDecryptor()
        with self.assertRaises(NotImplementedError):
            UnavailableBackupDecryptor().decrypt(b"cipher", key=b"synthetic", envelope={})

    def test_cli_inspection_exit_zero_means_structure_only(self):
        result = subprocess.run([sys.executable, '-m', 'cli', 'wechat', 'inspect-backup', str(self.source)], cwd=ROOT, capture_output=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['import_supported'])
        self.assertFalse(self.db.exists())

    def test_cli_import_is_nonzero_with_missing_decoder(self):
        result = subprocess.run([sys.executable, '-m', 'cli', '--db', str(self.db), 'wechat', 'import', str(self.source), '--report-dir', str(self.logs)], cwd=ROOT, capture_output=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['issues'][0]['code'], 'backup_content_unavailable')
        self.assertFalse(self.db.exists())

    def test_controller_auto_preview_returns_backup_result_not_import_success(self):
        result = ImportController(report_dir=self.logs).preview(self.source, self.db)
        self.assertEqual(result['kind'], 'backup')
        self.assertFalse(result['backup_inspection']['import_supported'])
        self.assertTrue(Path(result['backup_inspection']['report_path']).is_file())
        self.assertFalse(self.db.exists())

    def test_controller_explicit_backup_handles_unknown_structure(self):
        unknown = self.folder / 'unknown'
        unknown.mkdir()
        result = ImportController(report_dir=self.logs).preview(unknown, self.db, 'backup')
        self.assertFalse(result['backup_inspection']['import_supported'])
        self.assertFalse(self.db.exists())

    def test_reparse_point_attribute_is_rejected_without_following(self):
        from types import SimpleNamespace
        from wechat_archive.wechat_adapter.backup.reader import checked_path
        original = Path.lstat
        def lstat(path, *args, **kwargs):
            if path == self.source:
                return SimpleNamespace(st_mode=0o40755, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', lstat):
            with self.assertRaisesRegex(DocumentError, '目录联接'):
                checked_path(self.source)

    def test_nested_report_destination_is_rejected_for_metadata_selection(self):
        logs = self.device / 'new_logs'
        with self.assertRaises(DocumentError):
            WeChatImporter(self.db, report_dir=logs).import_file(self.device/'backup.attr')
        self.assertFalse(logs.exists())

    def test_gui_shows_missing_conditions_disables_import_and_recovers(self):
        root = tk.Tk()
        root.withdraw()
        window = ImportWindow(root, controller=ImportController(report_dir=self.logs))
        try:
            window.source.set(str(self.source))
            window.target.set(str(self.db))
            window.preview_button.invoke()
            deadline = time.monotonic()+15
            while window.busy and time.monotonic()<deadline:
                root.update()
                time.sleep(0.01)
            self.assertFalse(window.busy)
            self.assertIn('尚不可导入', window.status.get())
            self.assertIn('实际消息数量：尚未解析', window.result.get('1.0','end'))
            self.assertEqual(str(window.import_button['state']), 'disabled')
            self.assertEqual(str(window.browse_button['state']), 'disabled')
            self.assertEqual(str(window.report_button['state']), 'normal')
            window.source.set(str(ROOT/'examples/chat_sample.json'))
            self.assertEqual(str(window.import_button['state']), 'normal')
            self.assertFalse(self.db.exists())
        finally:
            window.close()

    def test_gui_direct_import_explains_unknown_message_count(self):
        root = tk.Tk()
        root.withdraw()
        window = ImportWindow(root, controller=ImportController(report_dir=self.logs))
        try:
            window.source.set(str(self.source))
            window.target.set(str(self.db))
            window.import_button.invoke()
            deadline = time.monotonic()+15
            while window.busy and time.monotonic()<deadline:
                root.update()
                time.sleep(0.01)
            self.assertFalse(window.busy)
            self.assertIn('实际消息数量：尚未解析', window.result.get('1.0','end'))
            self.assertEqual(str(window.import_button['state']), 'disabled')
            self.assertTrue(window.last_report.is_file())
            self.assertFalse(self.db.exists())
        finally:
            window.close()


if __name__ == '__main__':
    unittest.main()
