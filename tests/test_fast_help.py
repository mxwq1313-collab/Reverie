"""Behavioral checks for stable reading, new palettes and the offline help reader."""
import hashlib
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from wechat_archive import ChatService
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ui.theme import PALETTES
from wechat_archive.ui.user_preferences import validate,normalized


class FastHelpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.controller=ApplicationController(self.folder/'profile')
        self.db=self.folder/'synthetic.db';self.controller.new_archive(self.db);self.service=ChatService(self.db)
        for i,name in enumerate(('自己','对方')):self.service.create_user(wxid=f'fast_{i}',nickname=name)
        for i in range(3):self.service.create_message(sender_id=2,receiver_id=1,content=f' 原文 {i}\n消息第二行 ',create_time='2026-10-14T00:00:00Z')
        self.root=tk.Tk();self.root.withdraw();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=ApplicationWindow(self.root,controller=self.controller);self.addCleanup(self.app.close)
        self.root.geometry('1240x820');self.root.deiconify();self.root.update()
        self.digest=hashlib.sha256(self.db.read_bytes()).hexdigest()

    def preserved(self):
        self.assertEqual(self.errors,[]);self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.digest)

    def test_refresh_reuses_widgets_but_content_change_replaces_them(self):
        first=self.app.chat_text.bubbles[1]['text'];first.tag_add('sel','1.0','1.3')
        self.app.load_messages();self.root.update()
        self.assertIs(self.app.chat_text.bubbles[1]['text'],first);self.assertTrue(first.tag_ranges('sel'))
        self.service.update_message(1,content='更新后的原文')
        self.app.load_messages();self.root.update()
        self.assertIsNot(self.app.chat_text.bubbles[1]['text'],first)
        self.assertEqual(self.app.chat_text.bubbles[1]['text'].get('1.0','end-1c'),'更新后的原文');self.assertEqual(self.errors,[])

    def test_unchanged_reflow_does_not_measure_or_reset_text_geometry(self):
        text=self.app.chat_text.bubbles[1]['text'];height=text.winfo_height()
        with patch.object(self.app.theme.font,'measure',side_effect=AssertionError('No redundant measurement')):
            self.app.chat_text.reflow();self.root.update()
        self.assertEqual(text.winfo_height(),height);self.preserved()

    def test_pending_layout_can_be_replaced_without_stale_callbacks(self):
        self.app.search_word.set('0');self.app.load_messages()
        self.app.search_word.set('1');self.app.load_messages()
        self.root.update();self.assertEqual(list(self.app.chat_text.bubbles),[2]);self.preserved()

    def test_help_is_lazy_searchable_and_keyboard_reachable(self):
        self.assertFalse(hasattr(self.app,'help_reader'))
        self.app.nav_buttons['帮助'].invoke();self.root.update();reader=self.app.help_reader
        self.assertEqual(self.app.current_page,'帮助');self.assertIn('开始使用',reader.text.get('1.0','end'))
        reader.query.set('Ctrl+L');self.assertEqual(len(reader.visible),1)
        self.assertIn('Ctrl+L',reader.text.get('1.0','end'));self.assertTrue(reader.text.tag_ranges('match'))
        # Keyboard routing is exercised in an active window. Windows may leave
        # a later Tk test window inactive after earlier test windows are closed.
        self.root.focus_force();self.root.update()
        self.app.focus_message_search();self.root.update();self.assertIs(self.root.focus_get(),reader.entry)
        reader.query.set('不存在的帮助词');self.assertEqual(reader.visible,[]);self.preserved()

    def test_offscreen_text_maps_when_scrolled_into_view(self):
        for i in range(45):self.service.create_message(sender_id=2,receiver_id=1,content=f'用于滚动的记录 {i}',create_time='2026-10-14T01:00:00Z')
        self.app.load_messages();self.root.update();timeline=self.app.chat_text
        mapped=[v for v in timeline.bubbles.values() if v['text'].winfo_manager()]
        self.assertLess(len(mapped),len(timeline.bubbles)//2)
        last=timeline.bubbles[max(timeline.bubbles)];self.assertFalse(last['text'].winfo_manager())
        timeline.canvas.yview_moveto(1);self.root.update()
        self.assertEqual(last['text'].winfo_manager(),'place');self.assertEqual(self.errors,[])

    def test_default_startup_returns_before_restoring_archive_and_can_close_pending(self):
        other_root=tk.Tk();other_root.withdraw();other=ApplicationWindow(other_root,data_dir=self.controller.profile_dir)
        try:
            self.assertEqual(other.browser_state,'loading');self.assertIsNone(other.controller.database)
            self.assertIsNotNone(other.startup_job)
            other.load_initial_archive();deadline=time.monotonic()+4
            while time.monotonic()<deadline and (other.browser_reads.future is not None or len(other.message_rows)!=3):other_root.update();time.sleep(.005)
            self.assertEqual(len(other.message_rows),3)
        finally:other.close()
        pending_root=tk.Tk();pending_root.withdraw();pending=ApplicationWindow(pending_root,data_dir=self.folder/'empty_profile')
        pending.close();self.assertFalse((self.folder/'empty_profile/chat.db').exists());self.preserved()

    def test_help_english_switch_changes_document_without_chat_translation(self):
        self.app.show_page('帮助');self.app.language_choice.set('English');self.app.apply_user_settings();self.root.update()
        self.assertEqual(self.app.nav_buttons['帮助'].cget('text'),'Help')
        self.assertIn('Getting started',self.app.help_reader.text.get('1.0','end'))
        self.assertIn(' 原文 0\n',self.app.chat_text.bubbles[1]['text'].get('1.0','end'));self.preserved()

    def test_color_themes_apply_restore_and_keep_text_readable(self):
        for label,mode in (('暖砂','sand'),('雾蓝','blue'),('松绿','green'),('紫雾','violet')):
            self.app.theme_choice.set(label);self.app.apply_user_settings();self.root.update()
            self.assertEqual(self.app.theme.active_mode,mode)
            self.assertEqual(self.app.chat_text.bubbles[1]['text'].cget('background'),PALETTES[mode]['CANVAS'])
            self.assertEqual(ApplicationController(self.controller.profile_dir).user_preferences()['theme'],mode)
        self.preserved()

    def test_palettes_meet_normal_text_contrast_and_invalid_mode_is_rejected(self):
        def luminance(color):
            channels=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            return sum(weight*(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4) for weight,c in zip((.2126,.7152,.0722),channels))
        for palette in PALETTES.values():
            for ink,paper in (('INK','PAPER'),('SECONDARY','CANVAS'),('INK','SELECTED'),('PAPER','ACCENT')):
                values=sorted((luminance(palette[ink]),luminance(palette[paper])))
                self.assertGreaterEqual((values[1]+.05)/(values[0]+.05),4.5)
        with self.assertRaises(ValueError):validate({'theme':'unsupported'})
        self.assertEqual(normalized({'ui':{'theme':'unsupported'}})['theme'],'light');self.preserved()
