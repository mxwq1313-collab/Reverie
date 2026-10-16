import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from wechat_archive.errors import ValidationError
from wechat_archive.ui.import_controller import FORMAT_LABELS, ImportController, resolve_format
from wechat_archive.ui.import_window import ImportWindow

ROOT = Path(__file__).resolve().parents[1]


class ImportControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.database = self.folder / "archive.db"
        self.controller = ImportController(report_dir=self.folder / "logs")

    def test_preview_json_does_not_create_target(self):
        report = self.controller.preview(ROOT / "examples/chat_sample.json", self.database)
        self.assertEqual((report["users"], report["messages"], report["issues"]), (2, 3, []))
        self.assertFalse(self.database.exists())

    def test_json_import_uses_existing_engine_and_dedup(self):
        args = (ROOT / "examples/chat_sample.json", self.database)
        first, _ = self.controller.import_data(*args)
        second, _ = self.controller.import_data(*args)
        self.assertEqual((first.success_count, second.duplicated_count), (3, 3))

    def test_auto_csv_and_mock(self):
        report, _ = self.controller.import_data(ROOT / "examples/chat_sample.csv", self.database)
        self.assertEqual(report.success_count, 3)
        self.assertEqual(resolve_format(ROOT / "wechat_mock/export.json", "auto"), "mock")
        report, _ = self.controller.import_data(ROOT / "wechat_mock/export.json", self.database)
        self.assertEqual(report.success_count, 5)

    def test_android_preview_and_import(self):
        preview = self.controller.preview(ROOT / "android_mock", self.database, "android")
        self.assertEqual((preview["messages"], preview["skipped"]), (5, 2))
        self.assertFalse(self.database.exists())
        report, _ = self.controller.import_data(ROOT / "android_mock", self.database, "android")
        self.assertEqual(report.success_count, 5)

    def test_source_target_conflict_and_metadata_hint(self):
        source = ROOT / "android_mock/MicroMsg/mock-account-001/EnMicroMsg.db"
        before = source.read_bytes()
        with self.assertRaises(ValidationError):
            self.controller.import_data(source, source, "android")
        self.assertEqual(source.read_bytes(), before)
        with self.assertRaisesRegex(ValidationError, "元信息"):
            self.controller.preview(source.parent / "android_source.json", self.database)

    def test_relative_sample_resolves_from_project(self):
        result = self.controller.preview("examples/chat_sample.json", self.database)
        self.assertEqual(result["messages"], 3)


class ImportWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = ImportWindow(self.root, controller=ImportController(report_dir=self.folder / "logs"))
        self.addCleanup(self.app.close)

    def finish(self):
        until = time.monotonic() + 15
        while self.app.busy and time.monotonic() < until:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.busy, "GUI task did not finish")
        self.root.update()

    def fill(self):
        self.app.use_sample()
        self.app.target.set(str(self.folder / "archive.db"))

    def test_empty_selection_is_visible_error_without_writes(self):
        self.app.import_button.invoke()
        self.assertIn("请先选择", self.app.status.get())
        self.assertFalse(self.app.busy)

    def test_file_picker_populates_source(self):
        with patch("wechat_archive.ui.import_window.filedialog.askopenfilename", return_value=str(ROOT / "examples/chat_sample.json")):
            self.app.choose_file()
        self.assertTrue(self.app.source.get().endswith("chat_sample.json"))

    def test_preview_and_import_are_clickable_and_threaded(self):
        self.fill()
        self.app.preview_button.invoke()
        self.finish()
        self.assertIn("预览通过", self.app.status.get())
        self.assertFalse((self.folder / "archive.db").exists())
        self.app.import_button.invoke()
        self.assertTrue(self.app.busy)
        self.finish()
        self.assertIn("新增消息：3", self.app.result.get("1.0", "end"))
        self.assertEqual(str(self.app.browse_button["state"]), "normal")
        self.assertTrue(self.app.last_report.is_file())
        self.app.import_button.invoke()
        self.finish()
        self.assertIn("重复跳过：3", self.app.result.get("1.0", "end"))

    def test_invalid_input_leaves_controls_ready(self):
        self.app.source.set(str(self.folder / "missing.json"))
        self.app.target.set(str(self.folder / "archive.db"))
        self.app.import_button.invoke()
        self.finish()
        self.assertIn("不存在", self.app.result.get("1.0", "end"))
        self.assertEqual(str(self.app.import_button["state"]), "normal")

    def test_open_browser_uses_the_imported_database(self):
        self.fill()
        self.app.import_button.invoke()
        self.finish()
        with patch("wechat_archive.ui.import_window.webbrowser.open") as open_browser:
            self.app.browse_button.invoke()
            self.app.browse_button.invoke()
            self.assertEqual(open_browser.call_count, 2)
        self.assertEqual(len(self.app.servers), 1)
        server = next(iter(self.app.servers.values()))
        with urlopen(server.url + "api/status") as response:
            self.assertEqual(json.load(response)["messages"], 3)

    def test_android_sample_choice_and_csv_controls(self):
        self.app.format_label.set(FORMAT_LABELS["android"])
        self.app.use_sample()
        self.assertTrue(self.app.source.get().endswith("android_mock"))
        self.assertEqual(str(self.app.namespace_entry["state"]), "disabled")
        self.app.format_label.set(FORMAT_LABELS["csv"])
        self.app.use_sample()
        self.assertEqual(str(self.app.namespace_entry["state"]), "normal")


if __name__ == "__main__":
    unittest.main()
