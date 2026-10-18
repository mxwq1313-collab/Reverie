"""Tail-only Markdown regression with synthetic notifications."""
import unittest
from unittest.mock import patch
import test_agent as agent_fixture

class TailRenderingTests(unittest.TestCase):
    setUp=agent_fixture.AgentPanelTests.setUp
    def test_40k_history_is_not_redecorated_for_tail_or_final_role(self):
        from wechat_archive.ui import rich_markdown
        panel=self.panel;history=('历史 **原文** [链接](https://example.invalid)\n'*1500)[:40000]
        panel._add('Codex',history);panel._add('Codex','**半段','tail')
        with patch.object(rich_markdown,'decorate_range',wraps=rich_markdown.decorate_range) as decorate:
            panel._notification('item/agentMessage/delta',{'itemId':'tail','delta':'完成** [消息 #1]'});panel._render()
            panel._notification('item/completed',{'item':{'id':'tail','type':'agentMessage','phase':'final_answer','text':panel.messages[-1]['text']}})
        self.assertTrue(decorate.call_args_list)
        self.assertTrue(all(len(call.args[1])<100 for call in decorate.call_args_list))
        self.assertEqual(panel.transcript.get('1.0','end-1c'),history+'\n\n'+panel.messages[-1]['text'])
    def test_delta_burst_schedules_one_refresh_and_clear_cancels_it(self):
        panel=self.panel;panel._add('Codex','','tail')
        with patch.object(panel.root,'after',wraps=panel.root.after) as after:
            for part in ('中文😀',' [消息 #','1] **完成**'):
                panel._notification('item/agentMessage/delta',{'itemId':'tail','delta':part})
        self.assertEqual(sum(call.args[0]==130 for call in after.call_args_list),1)
        self.assertIsNotNone(panel.stream_render_job)
        panel._clear();self.assertIsNone(panel.stream_render_job)
        self.assertEqual(panel.transcript.get('1.0','end-1c'),'')
    def test_range_links_unicode_and_split_citation_keep_click_handlers(self):
        panel=self.panel;panel._add('Codex','😀 [站点](https://example.invalid) **重点**\n[消息 #','tail')
        panel._notification('item/agentMessage/delta',{'itemId':'tail','delta':'1]'});panel._render()
        text=panel.transcript;tags=[name for name in text.tag_names() if name.startswith('md_link_') and text.tag_ranges(name)]
        self.assertEqual(len(tags),1)
        a,b=text.tag_ranges(tags[0]);self.assertEqual(text.get(a,b),'站点')
        refs=[name for name in text.tag_names() if name.startswith('reference_')]
        a,b=text.tag_ranges(refs[0]);self.assertEqual(text.get(a,b),'[消息 #1]')
        self.assertTrue(text.tk.call(text._w,'tag','bind',tags[0],'<Button-1>'));self.assertTrue(text.tk.call(text._w,'tag','bind',refs[0],'<Button-1>'))

    def test_theme_change_preserves_reader_position_and_selection(self):
        import test_client_streaming as streaming
        text=streaming.StreamingReadingTests.show_transcript(self)
        text.yview_moveto(.2);self.root.update()
        text.tag_add('sel','45.0','45.end');selected=text.get('sel.first','sel.last')
        theme=self.app.theme;theme.update(theme.text_size,theme.family,'dark',theme.language,48)
        self.root.update();top=text.index('@0,0');self.panel._render();self.root.update()
        self.assertEqual(text.index('@0,0'),top);self.assertEqual(text.get('sel.first','sel.last'),selected)
    def test_repeated_stream_links_release_old_tcl_callbacks(self):
        panel=self.panel;panel._add('Codex','[站点](https://example.invalid) [消息 #1] 0','tail')
        before=len(panel.transcript._tclCommands)
        for index in range(40):
            panel.by_id['tail']['text']='[站点](https://example.invalid) [消息 #1] '+str(index)
            panel._render()
        self.assertLessEqual(len(panel.transcript._tclCommands),before+2)
        self.assertEqual(len(panel.transcript._markdown_links),1)
