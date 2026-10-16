from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from wechat_archive import ChatService,NotFoundError
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ui.theme import INK,SECONDARY,ACCENT,PAPER,OWN

ROOT=Path(__file__).resolve().parents[1]


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        self.controller=ApplicationController(self.folder/'profile');self.path=self.folder/'archive.db';self.controller.new_archive(self.path)
        self.service=ChatService(self.path)
        for wxid,name in (('unit_me','自己'),('unit_peer','长联系人姓名'*12),('unit_second','第二会话'),('unit_empty','空身份')):self.service.create_user(wxid=wxid,nickname=name)
        self.stamp=datetime(2026,10,10,0,0,tzinfo=timezone.utc)
        self.raw='  原文 空格\n多行 English https://example.invalid\n\n最后一行  '
        for index in range(15):self.service.create_message(sender_id=1 if index%2 else 2,receiver_id=2 if index%2 else 1,
            content=self.raw if index==0 else f'记录 {index}'+(' · 论文修改' if index==7 else ''),create_time=self.stamp+timedelta(hours=index))
        self.second=self.service.create_message(sender_id=3,receiver_id=1,content='第二会话 · 论文修改',create_time=self.stamp-timedelta(days=1)).id
        self.root=tk.Tk();self.root.withdraw();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=ApplicationWindow(self.root,controller=self.controller);self.addCleanup(self.app.close)
        self.app.owner_id=1;self.app.owner_box.current(0);self.app.peer_id=2;self.app.load_contacts()

    def wait(self):
        deadline=time.monotonic()+10
        while self.app.busy and time.monotonic()<deadline:self.root.update();time.sleep(.01)
        self.root.update();self.assertFalse(self.app.busy)

    def show(self,width=1100,height=720):
        self.root.geometry(f'{width}x{height}+0+0');self.root.deiconify();self.root.update();self.app.adapt_layout();self.root.update()

    def add_bulk(self):
        for index in range(15,115):self.service.create_message(sender_id=1 if index%2 else 2,receiver_id=2 if index%2 else 1,content=f'批量记录 {index}',create_time=self.stamp+timedelta(hours=index))

    def test_startup_restores_valid_identity_and_conversation(self):
        self.controller.save_view(3,1)
        other=ApplicationController(self.controller.data_dir);other.restore_archive()
        root=tk.Tk();root.withdraw();app=ApplicationWindow(root,controller=other)
        try:self.assertEqual((app.owner_id,app.peer_id),(3,1));self.assertEqual(app.current_page,'聊天归档')
        finally:app.close()

    def test_invalid_saved_view_falls_back_without_exit(self):
        settings=self.controller.settings();settings['views']={str(self.path):{'owner_id':999,'peer_id':998}};self.controller.save_settings(settings)
        other=ApplicationController(self.controller.data_dir);other.restore_archive();root=tk.Tk();root.withdraw();app=ApplicationWindow(root,controller=other)
        try:self.assertEqual(app.owner_id,1);self.assertIn(app.peer_id,(2,3))
        finally:app.close()

    def test_invalid_recent_archive_can_fall_back_to_valid_default(self):
        profile=self.folder/'fallback';profile.mkdir();database=profile/'chat.db';ChatService(database)
        (profile/'desktop_settings.json').write_text(json.dumps({'last_archive':str(self.folder/'missing.db')}),encoding='utf-8')
        controller=ApplicationController(profile);self.assertIsNotNone(controller.restore_archive());self.assertEqual(controller.database,database.resolve())

    def test_open_archive_uses_readonly_inspection_and_keeps_bytes(self):
        before=self.path.read_bytes()
        with patch('wechat_archive.ui.application_window.filedialog.askopenfilename',return_value=str(self.path)):
            self.app.open_archive()
        self.assertEqual(self.app.current_page,'聊天归档');self.assertEqual(self.path.read_bytes(),before)

    def test_no_archive_no_chat_and_no_match_are_distinct(self):
        root=tk.Tk();root.withdraw();empty=ApplicationWindow(root,controller=ApplicationController(self.folder/'unused'))
        try:self.assertEqual(empty.browser_state,'no_archive');self.assertFalse((self.folder/'unused/chat.db').exists())
        finally:empty.close()
        self.app.owner_box.current(3);self.app.change_owner();self.assertEqual(self.app.browser_state,'no_chats')
        self.app.owner_box.current(0);self.app.change_owner();self.app.search_word.set('从未出现');self.app.load_messages()
        self.assertEqual(self.app.browser_state,'no_matches');self.assertEqual(self.app.message_rows,[])

    def test_primary_and_legacy_routes_keep_features_reachable_without_source_reads(self):
        with patch.object(self.controller,'source_runner',side_effect=AssertionError('Must be explicit')):
            for name in self.app.PAGE_NAMES:self.app.show_page(name);self.assertEqual(self.app.current_page,name)
            for name,primary in (('电脑微信','添加记录'),('导入文件','添加记录'),('数据管理','工具与设置'),('备份检查','工具与设置'),('报告与设置','设置'),('Codex 助手','设置'),('可读导出','导出归档')):
                self.app.show_page(name);self.assertEqual(self.app.current_page,primary)

    def test_identity_and_contact_switch_never_keep_previous_messages(self):
        self.app.contact_tree.selection_set(str(3));self.app.select_contact();self.assertEqual([row['id'] for row in self.app.message_rows],[self.second])
        self.app.owner_box.current(3);self.app.change_owner();self.assertEqual(self.app.message_rows,[]);self.assertEqual(self.app.chat_text.bubbles,{})

    def test_search_enter_and_date_range_filter_real_query(self):
        self.app.search_word.set('论文修改');self.app.search_entry.event_generate('<Return>');self.root.update()
        # 在未映射根窗口下显式调用与 Enter 相同的动作。
        self.app.load_messages();self.assertEqual(len(self.app.message_rows),1)
        self.app.search_word.set('');self.app.start_date.set('2026-10-10');self.app.end_date.set('2026-10-10');self.app.load_messages()
        self.assertEqual(self.app.message_total,15)
        self.app.clear_filters();self.assertEqual(self.app.message_total,15)

    def test_all_chat_results_display_context_and_locate_original(self):
        self.app.search_scope.set('全部会话');self.app.search_word.set('论文修改');self.app.load_messages()
        self.assertEqual(self.app.message_total,2)
        value=self.app.chat_text.bubbles[self.second];self.assertIn('会话：第二会话',value['label'].cget('text'))
        self.app.show_context(self.second);self.assertEqual(self.app.peer_id,3);self.assertEqual(self.app.search_word.get(),'')
        self.assertEqual(self.app.message_rows[0]['id'],self.second);self.assertEqual(self.app.search_scope.get(),'当前会话')

    def test_context_can_locate_message_beyond_first_page(self):
        self.add_bulk()
        target=110;result=self.controller.message_context(1,target)
        self.assertGreater(result['offset'],0);self.assertIn(target,{row['id'] for row in result['items']})
        with self.assertRaises(NotFoundError):self.controller.message_context(4,target)

    def test_original_text_selection_highlight_and_copy_do_not_change_whitespace(self):
        self.app.search_word.set('English');self.app.load_messages();text=self.app.chat_text.bubbles[1]['text']
        self.assertEqual(text.get('1.0','end-1c'),self.raw);self.assertTrue(text.tag_ranges('match'))
        self.app.chat_text.copy_raw(self.raw);self.assertEqual(self.root.clipboard_get(),self.raw)
        text.tag_add('sel','1.0','end-1c');self.app.chat_text.copy_selection(text);self.assertEqual(self.root.clipboard_get(),self.raw)

    def test_directions_date_groups_and_time_are_preserved(self):
        self.service.create_message(sender_id=2,receiver_id=1,content='第二天的分组记录',create_time=self.stamp+timedelta(days=2));self.app.load_messages()
        first=self.app.chat_text.bubbles[1];second=self.app.chat_text.bubbles[2]
        self.assertEqual(first['color'],PAPER);self.assertEqual(second['color'],OWN)
        self.assertIn('08:00:00',first['label'].cget('text'));self.assertNotIn('UTC',first['label'].cget('text'))
        dates=[w.cget('text') for w in self.app.chat_text.body.winfo_children() if w.winfo_class()=='Label']
        self.assertGreater(len(dates),1)

    def test_load_more_keeps_pixel_reading_position_and_counts(self):
        self.add_bulk();self.app.load_messages()
        self.show();canvas=self.app.chat_text.canvas;canvas.yview_moveto(.15);self.root.update();before=canvas.canvasy(0)
        first=self.app.chat_text.bubbles[1]['text'];self.app.load_messages(more=True);self.root.update()
        self.assertIs(self.app.chat_text.bubbles[1]['text'],first);self.assertAlmostEqual(canvas.canvasy(0),before,delta=5)
        self.assertEqual(len(self.app.message_rows),115);self.assertIn('全部匹配 115 条',self.app.chat_info.get());self.assertIn('当前加载 115 条',self.app.chat_info.get())

    def test_failed_more_keeps_loaded_content_and_can_retry(self):
        self.add_bulk();self.app.load_messages()
        previous=list(self.app.message_rows)
        with patch.object(self.controller,'messages',side_effect=OSError('offline')):self.app.load_messages(more=True)
        self.assertEqual(self.app.message_rows,previous);self.assertIn('已加载内容保留',self.app.status.get())
        self.app.load_messages(more=True);self.assertEqual(len(self.app.message_rows),115)

    def test_first_load_failure_has_retry_state(self):
        with patch.object(self.controller,'messages',side_effect=OSError('unavailable')):self.app.load_messages()
        self.assertEqual(self.app.browser_state,'failed');self.app.load_messages();self.assertEqual(self.app.browser_state,'messages')

    def test_long_message_wraps_without_truncation(self):
        value=('中文 English words '*170)+'\n末尾'
        self.service.update_message(1,content=value);self.app.load_messages();self.show()
        text=self.app.chat_text.bubbles[1]['text'];self.assertEqual(text.get('1.0','end-1c'),value)
        self.assertGreater(text.count('1.0','end-1c','displaylines')[0],10)

    def test_short_message_does_not_wrap_prematurely_in_wide_window(self):
        value='短消息在宽窗口中应当保持一行。'
        self.service.update_message(1,content=value);self.app.load_messages();self.show(1240,820)
        text=self.app.chat_text.bubbles[1]['text'];count=text.count('1.0','end-1c','displaylines')
        self.assertEqual(count[0] if count else 0,0)

    def test_preview_and_duplicate_import_show_real_counts(self):
        self.app.import_source.set(str(ROOT/'examples/chat_sample.json'));before=self.path.read_bytes()
        self.app.import_action(True);self.wait();self.assertEqual(self.path.read_bytes(),before);self.assertEqual(self.app.import_cards.values[0].get(),'3')
        self.app.import_action(False);self.wait();self.assertEqual(self.app.import_cards.values[0].get(),'3')
        self.app.import_action(False);self.wait();self.assertEqual(self.app.import_cards.values[0].get(),'0');self.assertEqual(self.app.import_cards.values[1].get(),'3')

    def test_csv_specific_controls_follow_selected_scenario(self):
        self.assertFalse(self.app.csv_options_visible);self.app.import_source.set('unit.csv');self.assertTrue(self.app.csv_options_visible)
        self.app.import_source.set('unit.json');self.assertFalse(self.app.csv_options_visible)

    def test_current_conversation_export_contains_all_unloaded_and_filtered_messages(self):
        self.add_bulk()
        self.app.search_word.set('English');self.app.load_messages();self.assertEqual(len(self.app.message_rows),1)
        self.app.prepare_export('当前会话');self.assertEqual(self.app.current_page,'导出归档')
        self.app.export_parent.set(str(self.folder));self.app.export_action();self.wait()
        self.assertIn('消息：115',self.app.export_result.get('1.0','end'))
        self.app.export_scope.set('全部已归档文本');self.app.export_action();self.wait()
        self.assertIn('消息：116',self.app.export_result.get('1.0','end'));self.assertEqual(len(list(self.folder.glob('聊天导出_*/index.html'))),2)

    def test_busy_cancel_and_transaction_boundary_remain(self):
        release=threading.Event();completed=[]
        self.app.run('正在读取电脑微信…',lambda:release.wait(3),completed.append)
        self.assertEqual(str(self.app.import_button['state']),'disabled');self.app.show_page('导出归档');self.assertEqual(self.app.current_page,'导出归档')
        self.assertEqual(str(self.app.export_button['state']),'disabled');self.assertNotEqual(str(self.app.nav_buttons['导出归档']['state']),'disabled')
        self.controller.writing=True;self.app.cancel_reading();self.assertFalse(self.controller.cancel_event.is_set());self.assertIn('提交归档',self.app.status.get())
        self.controller.writing=False;self.app.cancel_reading();self.assertTrue(self.controller.cancel_event.is_set())
        release.set();self.wait();self.assertEqual(str(self.app.import_button['state']),'normal');self.assertEqual(len(completed),1)

    def test_exception_restores_controls_and_allows_next_operation(self):
        def fail():raise RuntimeError('unit failure')
        with patch('wechat_archive.ui.application_window.messagebox.showerror') as error:
            self.app.run('正在检查…',fail,lambda _:None);self.wait();error.assert_called_once()
        values=[];self.app.run('正在检查…',lambda:5,values.append);self.wait();self.assertEqual(values,[5])

    def test_reading_settings_persist_without_touching_archive(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest();self.app.text_size.set(17);self.app.compact_nav.set(True);self.app.apply_reading_settings()
        self.assertEqual(ApplicationController(self.controller.data_dir).preferences(),{'text_size':17,'compact_nav':True})
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)

    def test_default_and_small_window_controls_do_not_overlap(self):
        for width,height in ((1240,820),(900,650),(820,600)):
            self.show(width,height)
            entry=self.app.search_entry;scope=self.app.search_box;date=self.app.date_button
            self.assertLessEqual(entry.winfo_rooty()+entry.winfo_height(),scope.winfo_rooty()+1)
            self.assertFalse(self.app.search_button.winfo_ismapped())
            self.assertLessEqual(entry.winfo_rootx()+entry.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
            self.assertLessEqual(scope.winfo_rootx()+scope.winfo_width(),date.winfo_rootx()+1)
            self.assertLessEqual(date.winfo_rootx()+date.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
            self.assertGreater(self.app.chat_text.winfo_width(),280)
            self.assertLessEqual(self.app.conversation_column.winfo_width(),self.app.theme.u(280))
        self.assertEqual(self.errors,[])


class LayoutScaleTests(unittest.TestCase):
    def test_three_tk_dpi_scales_fit_real_widgets(self):
        with tempfile.TemporaryDirectory() as directory:
            for factor in (1,1.25,1.5):
                root=tk.Tk();root.withdraw();root.tk.call('tk','scaling',(96/72)*factor)
                app=ApplicationWindow(root,controller=ApplicationController(Path(directory)/str(factor)))
                try:
                    root.geometry(f'{round(960*factor)}x{round(680*factor)}+0+0');root.deiconify();root.update();app.adapt_layout();root.update()
                    self.assertAlmostEqual(app.theme.scale,factor,delta=.02)
                    self.assertGreater(app.chat_text.winfo_width()/factor,350)
                    self.assertLessEqual(app.date_button.winfo_rootx()+app.date_button.winfo_width(),root.winfo_rootx()+root.winfo_width())
                    self.assertLessEqual(app.more_button.winfo_rooty()+app.more_button.winfo_height(),root.winfo_rooty()+root.winfo_height())
                finally:app.close()

    def test_normal_text_colors_meet_45_contrast(self):
        def luminance(value):
            values=[int(value[i:i+2],16)/255 for i in (1,3,5)]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
        for ink,paper in ((INK,PAPER),(SECONDARY,PAPER),(ACCENT,PAPER),(INK,OWN)):
            first,second=sorted((luminance(ink),luminance(paper)));self.assertGreaterEqual((second+.05)/(first+.05),4.5)
