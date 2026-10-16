import hashlib
from pathlib import Path
import sqlite3
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from wechat_archive import ChatService,ConflictError,NotFoundError
from wechat_archive.desktop import inspect_archive,resources_report,smoke_check,main
from wechat_archive.ui.import_window import ImportWindow
from wechat_archive.ui.application_window import ApplicationWindow

ROOT=Path(__file__).resolve().parents[1]


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)

    def test_required_resources_available(self):
        report=resources_report()
        self.assertEqual(len(report),7);self.assertTrue(all(value>0 for value in report.values()))

    def test_existing_archive_inspected_readonly(self):
        database=self.folder/'archive.db';ChatService(database)
        before=hashlib.sha256(database.read_bytes()).hexdigest()
        self.assertEqual(inspect_archive(database),database.resolve())
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(),before)

    def test_missing_or_unknown_database_unchanged(self):
        missing=self.folder/'missing.db'
        with self.assertRaises(NotFoundError):inspect_archive(missing)
        self.assertFalse(missing.exists())
        unknown=self.folder/'unknown.db'
        with sqlite3.connect(unknown) as connection:connection.execute('CREATE TABLE unrelated(id)')
        before=unknown.read_bytes()
        with self.assertRaises(ConflictError):inspect_archive(unknown)
        self.assertEqual(unknown.read_bytes(),before)

    def test_smoke_check_import_repeat_export_ui_without_browser(self):
        with patch('webbrowser.open') as browser:
            report=smoke_check(ROOT/'examples/chat_sample.json',self.folder/'check')
            browser.assert_not_called()
        self.assertEqual((report['messages'],report['duplicates'],report['exported']),(3,3,3))
        self.assertTrue(report['ui']['browse_button_enabled']);self.assertIn('导出可读文件',report['ui']['export_button'])

    def test_existing_diagnostics_directory_not_modified(self):
        check=self.folder/'existing';check.mkdir();marker=check/'desktop_error.json';marker.write_text('preserve',encoding='utf-8')
        for args in (['--smoke-check',str(ROOT/'examples/chat_sample.json'),'--check-dir'],['--workbench-check-dir'],['--codex-check-dir'],['--knowledge-check-dir'],['--sixu-check-dir']):
            self.assertEqual(main([*args,str(check)]),1)
            self.assertEqual(marker.read_text(encoding='utf-8'),'preserve');self.assertEqual(len(list(check.iterdir())),1)

    def test_existing_archive_picker_enables_browse_without_import(self):
        database=self.folder/'existing.db';ChatService(database)
        before=database.read_bytes();root=tk.Tk();root.withdraw();app=ImportWindow(root)
        try:
            with patch('wechat_archive.ui.import_window.filedialog.asksaveasfilename',return_value=str(database)):
                app.choose_target()
            self.assertEqual(app.last_database,database.resolve());self.assertEqual(str(app.browse_button['state']),'normal')
            self.assertEqual(database.read_bytes(),before)
        finally:app.close()

    def test_desktop_restores_existing_default_archive(self):
        database=self.folder/'chat.db';ChatService(database);captured=[]
        before=database.read_bytes();root=tk.Tk();root.withdraw();event_loop=root.mainloop;restored=[]
        def window(value):
            app=ApplicationWindow(value,data_dir=self.folder);captured.append(app);return app
        def close():
            # Startup restores after the shell is ready; exercise the real event loop.
            deadline=time.monotonic()+4
            def ready():
                if captured[0].controller.database is not None or time.monotonic()>=deadline:root.quit()
                else:root.after(10,ready)
            root.after(10,ready);event_loop();restored.append(captured[0].controller.database)
            captured[0].close()
        def create(value,**options):return window(value)
        with patch('wechat_archive.desktop.default_data_dir',return_value=self.folder),patch('wechat_archive.desktop.tk.Tk',return_value=root),patch('wechat_archive.desktop.ApplicationWindow',side_effect=create),patch.object(root,'mainloop',side_effect=close):
            self.assertEqual(main([]),0)
        self.assertEqual(restored,[database.resolve()]);self.assertIn('聊天归档',captured[0].pages)
        self.assertEqual(database.read_bytes(),before)
