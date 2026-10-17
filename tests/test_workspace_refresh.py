"""Synthetic end-to-end checks for the redesigned native workspace."""
import hashlib,time,tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_workbench as fixture


class WorkspaceRefreshTests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def settle(self,condition=lambda:True,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.root.update()
            if condition():return
            time.sleep(.005)
        self.fail('UI did not settle')
    def dialogs(self):return [w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.winfo_ismapped()]
    def widgets(self,parent):
        result=[]
        for child in parent.winfo_children():result.append(child);result.extend(self.widgets(child))
        return result
    def test_reports_move_to_settings_with_legacy_route_preserved(self):
        self.app.show_page('报告与设置');self.root.update()
        self.assertEqual(self.app.current_page,'设置')
        self.assertEqual(self.app.settings_notebook.select(),str(self.app.tab_routes['报告与设置'][1]))
        labels=[self.app.tools_notebook.tab(x,'text') for x in self.app.tools_notebook.tabs()]
        self.assertEqual(labels,['归档管理','语义检索','随机回忆'])
    def test_markdown_and_compact_references_preserve_raw_unicode_and_copy(self):
        panel=self.app.agent_panel
        raw='## 标题\n\n- **重点**：中文😀[消息 #1][消息 #2]\n\n`code`\n\n```python\n**原样代码**\n```'
        panel._add('Codex · 回答',raw);self.root.update();text=panel.transcript
        self.assertEqual(text.get('1.0','end-1c'),raw)
        self.assertTrue(text.tag_ranges('md_bold'));self.assertTrue(text.tag_ranges('md_h2'));self.assertTrue(text.tag_ranges('md_reference_marker'))
        bold=text.tag_ranges('md_bold');self.assertEqual(text.get(bold[0],bold[1]),'重点')
        for tag in text.tag_names():
            if tag.startswith('reference_'):
                a,b=text.tag_ranges(tag);self.assertRegex(text.get(a,b),r'^\[消息 #\d+\]$')
        panel.copy_answer();self.assertIn('**重点**',self.root.clipboard_get())
        self.assertEqual(self.errors,[])
    def test_markdown_blank_lines_keep_paragraphs_compact(self):
        self.show();self.app.open_copilot(False);panel=self.app.agent_panel
        raw='## 小标题\n\n一段正文。\n\n下一段。';panel._add('Codex',raw);self.root.update()
        if panel.follow_job:self.root.after_cancel(panel.follow_job);panel.follow_job=None
        panel.transcript.yview_moveto(0);self.root.update();a=panel.transcript.bbox('1.3');b=panel.transcript.bbox('3.0')
        self.assertIsNotNone(a);self.assertIsNotNone(b);self.assertLess(b[1]-a[1],60)
        self.assertEqual(panel.transcript.get('1.0','end-1c'),raw)

    def test_stream_delta_restyles_without_changing_selection_or_source(self):
        panel=self.app.agent_panel;panel._add('Codex','**前半','case')
        panel._notification('item/agentMessage/delta',{'itemId':'case','delta':'段** 与[消息 #1]'})
        panel._render();self.assertEqual(panel.transcript.get('1.0','end-1c'),'**前半段** 与[消息 #1]')
        self.assertTrue(panel.transcript.tag_ranges('md_bold'))
    def test_middle_stream_edit_after_emoji_keeps_exact_raw_text(self):
        panel=self.app.agent_panel;panel._add('Codex','😀 before **draft** tail','mid')
        expected='😀 before **final** tail';panel.by_id['mid']['text']=expected;panel._render()
        self.assertEqual(panel.transcript.get('1.0','end-1c'),expected)
        a,b=panel.transcript.tag_ranges('md_bold');self.assertEqual(panel.transcript.get(a,b),'final')

    def test_media_details_are_readonly_with_values_and_visible_close(self):
        self.show();app=self.app;app.show_page('数据管理');self.root.update()
        row=app.message_rows[0];row.update(msg_type='image',content='<msg><img md5="synthetic"/></msg>',attachments=[])
        app.message_tree.selection_set(str(row['id']));app.message_editor(True);self.root.update();dialog=self.dialogs()[0]
        fields=dialog.variables;self.assertTrue(fields[0].get());self.assertTrue(fields[1].get());self.assertTrue(fields[2].get())
        texts=[w for w in self.widgets(dialog) if isinstance(w,tk.Text)]
        visible=[w for w in texts if w.winfo_ismapped()]
        self.assertTrue(visible);self.assertFalse(any('<msg>' in w.get('1.0','end') for w in visible))
        self.assertTrue(all(str(w.cget('state'))=='disabled' for w in texts))
        close=next(w for w in self.widgets(dialog) if isinstance(w,ttk.Button) and str(w.cget('text'))=='关闭')
        self.assertTrue(close.winfo_ismapped());self.assertLessEqual(close.winfo_rooty()+close.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
        self.assertFalse(any(str(w.cget('text'))=='保存文本' for w in self.widgets(dialog) if isinstance(w,ttk.Button)))
        dialog.destroy();self.assertEqual(self.errors,[])
    def test_group_message_is_not_routed_through_private_pair_editor(self):
        self.show();app=self.app;app.show_page('数据管理');row=app.message_rows[0]
        row.update(chat_kind='group',chat_title='自建群聊',receiver_id=None,msg_type='text')
        app.message_tree.selection_set(str(row['id']));before=self.path.read_bytes();app.message_editor(True);self.root.update()
        dialog=self.dialogs()[0];self.assertEqual(dialog.variables[1].get(),'自建群聊')
        self.assertFalse(any(str(w.cget('text'))=='保存文本' for w in self.widgets(dialog) if isinstance(w,ttk.Button)))
        dialog.destroy();self.assertEqual(before,self.path.read_bytes())

    def test_text_editor_keeps_timestamp_and_works_at_small_size(self):
        self.show();app=self.app;row=app.message_rows[0];before=row['create_time'];app.show_page('数据管理');app.message_tree.selection_set(str(row['id']));app.message_editor(True);self.root.update();dialog=self.dialogs()[0]
        dialog.geometry('650x550');self.root.update()
        save=next(w for w in self.widgets(dialog) if isinstance(w,ttk.Button) and str(w.cget('text'))=='保存文本')
        self.assertTrue(save.winfo_ismapped());save.invoke();self.root.update()
        self.assertEqual(next(x for x in app.message_rows if x['id']==row['id'])['create_time'],before)
        self.assertEqual(self.errors,[])
    def test_capsule_and_random_memory_read_only_current_scope(self):
        app=self.app;before=hashlib.sha256(self.path.read_bytes()).hexdigest();box=app.toolbox_panel
        box.date.set('2026-10-10');box.read('date');self.settle(lambda:not app.busy)
        self.assertIsNotNone(box.row);self.assertIn(box.row['sender_id'],(1,2));self.assertNotEqual(box.row['id'],self.second)
        with patch('wechat_archive.ui.toolbox_panel.random.randrange',return_value=0):box.read('random');self.settle(lambda:not app.busy)
        box.copy_memory();self.assertIn('[消息 #',self.root.clipboard_get())
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        app.peer_id=3;box.copy_memory();self.assertIn('当前范围',app.status.get())
    def test_memory_tool_requires_explicit_conversation(self):
        self.app.peer_id=None
        with patch.object(self.app.controller,'messages') as read:
            self.app.toolbox_panel.read('random');read.assert_not_called()
        self.assertIn('选择会话',self.app.status.get())

    def test_group_search_explains_private_scope_and_disables_invalid_read(self):
        self.app.peer_id=-1;panel=self.app.knowledge_panel
        self.root.after_cancel(panel.poll_job);panel.poll()
        self.assertIn('私聊',panel.scope_text.get());self.assertNotIn('#-1',panel.scope_text.get())
        self.assertIn('disabled',panel.sync_button.state())

    def test_pointer_and_keyboard_receipts_use_actual_action_result(self):
        self.show();app=self.app;app.show_page('随机回忆');self.root.update()
        button=app.button(app.toolbox_panel.views['随机回忆'],'测试复制',lambda:app.status.set('内容已复制。'));button.pack();app.theme.apply_tree(button);self.root.update()
        button.event_generate('<ButtonPress-1>',x=4,y=4);button.event_generate('<ButtonRelease-1>',x=4,y=4);self.root.update()
        self.assertEqual(app.status.get(),'内容已复制。');self.assertFalse(hasattr(app.feedback,'frame'))
        app.ui_settings['reduce_motion']=True;app.feedback.show('请选择会话。');self.assertEqual(app.feedback.tone,'attention');self.assertFalse(hasattr(app.feedback,'frame'))
    def test_status_remains_in_footer_with_narrow_codex_drawer(self):
        self.show(900,700);self.root.attributes('-topmost',True);self.root.focus_force();app=self.app
        app.open_copilot(False);self.root.update();app.adapt_layout();self.root.update()
        self.assertEqual(app.copilot_mode,'drawer');app.feedback.show('操作结果仅在状态栏中显示。');self.root.update()
        self.assertFalse(hasattr(app.feedback,'frame'));label=app.status_label;x=label.winfo_rootx()+label.winfo_width()//2;y=label.winfo_rooty()+label.winfo_height()//2
        self.assertTrue(label.winfo_viewable())
        self.assertGreaterEqual(label.winfo_rooty(),self.root.winfo_rooty())
        self.assertLessEqual(label.winfo_rooty()+label.winfo_height(),self.root.winfo_rooty()+self.root.winfo_height())

    def test_resize_burst_defers_body_width_and_reuses_scrollbar_items(self):
        self.show();view=self.app.chat_text;self.settle(lambda:not view.reflow_busy and not view.layout_job)
        bar=view.scrollbar;bar.set(.1,.4);self.root.update();items=bar.find_withtag('thumb')
        self.assertEqual(len(items),3)
        for i in range(30):bar.draw(i%2==0)
        self.assertEqual(items,bar.find_withtag('thumb'))
        with patch.object(view,'reflow',wraps=view.reflow) as flow:
            for width in range(1000,1200,10):self.root.geometry(f'{width}x720');self.root.update_idletasks()
            self.settle(lambda:not view.reflow_busy and not view.layout_job)
            self.assertLess(flow.call_count,7)
        self.assertEqual(self.errors,[])
    def test_row_can_expand_while_hidden_measurement_yields(self):
        self.show();app=self.app;app.background_browsing=True;view=app.chat_text;base=app.message_rows[0]
        rows=[{**base,'id':3000+n,'content':'可见性变化时仍需稳定测量的原文 '*30+str(n)} for n in range(40)]
        app.message_rows=rows;app.message_total=40;view.set_rows_incremental(rows,app.owner_id)
        self.settle(lambda:not view.rendering and not view.reflow_busy and not view.layout_job)
        value=next(v for v in view.bubbles.values() if v.get('collapsed_children'))
        view.measure_collapsed(value,250,app.theme.font.metrics('linespace')+4)
        original=view.measure_widget.update_idletasks
        def expand():view.expand_row(value);original()
        with patch.object(view.measure_widget,'update_idletasks',side_effect=expand):
            view.measure_collapsed(value,230,app.theme.font.metrics('linespace')+4)
        self.settle(lambda:not view.reflow_busy and not view.layout_job)
        self.assertTrue(value['text'].winfo_exists());self.assertEqual(self.errors,[])

    def test_placeholder_size_does_not_accumulate_rounding_on_resizes(self):
        self.show();app=self.app;view=app.chat_text;base=app.message_rows[0]
        value=next(iter(view.bubbles.values()))
        view.remember_measure(value,300,25,5)
        value.update(display_text='长文本'*100,natural=3000,collapsed_children=[])
        view.measure_cache.clear();view.estimate_collapsed(value,260,25);first=value['text_height']
        for _ in range(8):view.estimate_collapsed(value,230,25);view.estimate_collapsed(value,260,25)
        self.assertEqual(value['text_height'],first)

    def test_repeated_collapsed_text_uses_bounded_measurements(self):
        self.show();app=self.app;app.background_browsing=True;view=app.chat_text;base=app.message_rows[0]
        rows=[{**base,'id':2000+n,'content':'用于换行的重复归档内容 '*35} for n in range(60)]
        app.message_rows=rows;app.message_total=60;view.set_rows_incremental(rows,app.owner_id)
        self.settle(lambda:not view.rendering and not view.reflow_busy and not view.layout_job)
        self.app.theme.update(18,self.app.theme.family,self.app.theme.mode,'zh_CN',48);view.completed_layout=None;view.queue_reflow()
        self.settle(lambda:not view.reflow_busy and not view.layout_job)
        self.assertLessEqual(len(view.measure_cache),80)
        self.assertGreater(sum(bool(v.get('collapsed_children')) for v in view.bubbles.values()),30)
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main(verbosity=2)
