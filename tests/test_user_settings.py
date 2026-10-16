"""Persistent, live user preferences and the lean AI sidebar on synthetic data."""
import hashlib
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import font,ttk
import unittest
from unittest.mock import patch
from wechat_archive import ChatService
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ui.slim_scrollbar import SlimScrollbar
from wechat_archive.ui.user_preferences import validate


class UserSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        self.controller=ApplicationController(self.folder/'profile');self.path=self.folder/'archive.db';self.controller.new_archive(self.path)
        service=ChatService(self.path)
        for wxid,nickname in (('settings_self','我'),('settings_peer','搜索')):service.create_user(wxid=wxid,nickname=nickname)
        self.raw='  设置\nSearch 原文 😀  '
        service.create_message(sender_id=2,receiver_id=1,content=self.raw,create_time='2026-10-14T00:00:00Z')
        self.root=tk.Tk();self.root.withdraw();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=ApplicationWindow(self.root,controller=self.controller);self.addCleanup(self.app.close)
        self.app.owner_id=1;self.app.owner_box.current(0);self.app.peer_id=2;self.app.load_contacts()
        self.digest=hashlib.sha256(self.path.read_bytes()).hexdigest()

    def show(self):
        self.root.geometry('1240x820+0+0');self.root.deiconify();self.root.update()

    def assert_preserved(self):
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.digest)
        self.assertEqual(self.app.chat_text.bubbles[1]['text'].get('1.0','end-1c'),self.raw)
        self.assertEqual(self.errors,[])

    def test_idle_progress_and_native_heavy_scrollbars_are_removed(self):
        self.show();self.assertFalse(self.app.progress.winfo_ismapped());self.assertFalse(self.app.cancel_button.winfo_ismapped())
        bars=[w for w in self.app.descendants(self.root) if isinstance(w,SlimScrollbar)]
        self.assertGreater(len(bars),5);self.assertTrue(all(int(float(w.cget('width')))<=self.app.theme.u(8) for w in bars))
        self.assertFalse(any(w.winfo_class() in ('Scrollbar','TScrollbar') for w in self.app.descendants(self.root)))

    def test_ai_controls_live_in_settings_not_sidebar(self):
        self.show();panel=self.app.agent_panel
        self.assertTrue(panel.input.winfo_ismapped())
        ancestors=[];widget=panel.connect_button
        while widget is not None:ancestors.append(widget);widget=getattr(widget,'master',None)
        self.assertIn(self.app.settings_ai_codex,ancestors);self.assertNotIn(self.app.copilot_body,ancestors)
        panel.settings_button.invoke();self.root.update()
        self.assertEqual(self.app.current_page,'设置');self.assertTrue(panel.connect_button.winfo_ismapped());self.assertTrue(panel.parameters_button.winfo_ismapped())
        panel.parameters_button.invoke();self.root.update();self.assertTrue(panel.power_model_button.winfo_ismapped());self.assertTrue(panel.power_slider.winfo_ismapped())
        panel.parameters_popup.withdraw()

    def test_tool_tabs_have_no_placeholder_or_unavailable_backup_diagnostics(self):
        labels=[self.app.tools_notebook.tab(tab,'text') for tab in self.app.tools_notebook.tabs()]
        self.assertEqual(labels,['归档管理','语义检索','文字小工坊'])
        self.assertIn('导入与分析报告',[self.app.settings_notebook.tab(tab,'text') for tab in self.app.settings_notebook.tabs()])
        self.assertFalse(self.app.knowledge_panel.ask_button.winfo_manager())

    def test_theme_and_font_apply_live_preserve_archive_and_restore(self):
        self.show();self.app.theme_choice.set('深色');self.app.text_size.set(19)
        family='Segoe UI' if 'Segoe UI' in self.app.theme.available_fonts else self.app.theme.available_fonts[0]
        self.app.font_family.set(family);self.app.apply_user_settings();self.root.update()
        self.assertEqual(self.app.theme.active_mode,'dark');self.assertEqual(self.app.theme.family,family)
        self.assertEqual(self.app.chat_text.bubbles[1]['text'].cget('background'),self.app.theme.palette['CANVAS'])
        restored=ApplicationController(self.controller.profile_dir).user_preferences()
        self.assertEqual((restored['theme'],restored['text_size'],restored['font_family']),('dark',19,family));self.assert_preserved()

    def test_english_changes_ui_not_raw_nickname_or_selector_semantics(self):
        self.show();self.app.language_choice.set('English');self.app.apply_user_settings();self.root.update()
        self.assertEqual(self.root.title(),'Sixu')
        self.assertEqual(self.app.nav_buttons['设置'].cget('text'),'Settings')
        self.assertEqual(self.app.contact_tree.cards['2'][1].cget('text'),'搜索')
        self.assertEqual(self.app.search_scope.get(),'当前会话');self.assertEqual(self.app.search_box.get(),'This chat')
        dates=[widget.cget('text') for widget in self.app.chat_text.body.winfo_children() if hasattr(widget,'_date_value')]
        self.assertEqual(dates,['2026-10-14'])
        self.app.search_box.current(1);self.root.update();self.assertEqual(self.app.search_scope.get(),'全部会话')
        self.assert_preserved()

    def test_language_can_switch_back_and_body_never_translates(self):
        self.show()
        for language in ('English','简体中文','English','简体中文'):
            self.app.language_choice.set(language);self.app.apply_user_settings();self.root.update();self.assert_preserved()
        self.assertEqual(self.app.nav_buttons['设置'].cget('text'),'设置')

    def test_storage_redirects_future_files_preserves_profile_and_archive(self):
        target=self.folder/'new files';self.app.storage_root.set(str(target));self.app.default_export_folder.set(str(self.folder/'exports'))
        self.app.apply_user_settings()
        self.assertEqual(self.controller.data_dir,target.resolve());self.assertEqual(self.controller.profile_dir,self.folder/'profile')
        self.assertEqual(self.controller.database,self.path.resolve())
        self.assertEqual(self.controller.imports.report_dir,target/'import_logs')
        restored=ApplicationController(self.controller.profile_dir)
        self.assertEqual(restored.data_dir,target);self.assertTrue(restored.restore_archive());self.assertEqual(restored.database,self.path.resolve())
        self.assertFalse((target/'archive.db').exists());self.assert_preserved()

    def test_invalid_path_does_not_save_or_relocate(self):
        before=self.controller.settings();self.app.storage_root.set(str(self.path))
        with patch('wechat_archive.ui.settings_panel.messagebox.showerror') as error:self.app.apply_user_settings()
        self.assertEqual(self.controller.settings(),before);error.assert_called_once();self.assert_preserved()

    def test_show_sidebar_and_wheel_speed_persist_and_apply(self):
        self.show();self.app.show_ai_setting.set(False);self.app.wheel_speed.set(96);self.app.apply_user_settings();self.root.update()
        self.assertFalse(self.app.copilot_expanded);self.assertEqual(self.app.theme.wheel_router.pixels,self.app.theme.u(96))
        self.assertFalse(self.controller.user_preferences()['show_ai'])

    def test_system_theme_reacts_without_writing_preferences(self):
        self.show();self.app.theme_choice.set('跟随系统')
        with patch('wechat_archive.ui.theme.Theme.resolved_mode',return_value='dark'):self.app.apply_user_settings()
        before=self.controller.settings()
        self.root.after_cancel(self.app.theme_poll_job)  # Manual poll replaces the scheduled poll.
        with patch('wechat_archive.ui.theme.Theme.resolved_mode',return_value='light'):self.app.poll_system_theme()
        self.assertEqual(self.app.theme.active_mode,'light');self.assertEqual(self.controller.settings(),before);self.assert_preserved()

    def test_font_and_range_validation(self):
        for values in ({'text_size':True},{'text_size':30},{'wheel_speed':0},{'theme':'unknown'},{'language':'bad'}):
            with self.assertRaises(Exception):validate(values)

    def test_new_archive_default_can_be_changed_without_moving_old_file(self):
        self.app.storage_root.set(str(self.folder/'later'));self.app.apply_user_settings()
        other=self.controller.data_dir/'new.db';self.controller.new_archive(other)
        self.assertTrue(other.exists());self.assertTrue(self.path.exists());self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.digest)


if __name__=='__main__':unittest.main()
