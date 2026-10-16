"""Streaming display checks use UI notifications only, never inference."""
import unittest
import test_agent as agent_fixture


class StreamingReadingTests(unittest.TestCase):
    setUp=agent_fixture.AgentPanelTests.setUp

    def show_transcript(self):
        # Fixture replaces the built-in panel; place its transcript in a dedicated mapped window.
        import tkinter as tk
        from tkinter.scrolledtext import ScrolledText
        old=self.panel.transcript
        self.window=tk.Toplevel(self.root);self.window.geometry('640x320+0+0')
        self.addCleanup(self.window.destroy)
        self.panel.transcript=ScrolledText(self.window,wrap='word',font=self.app.theme.body)
        self.panel.transcript.pack(fill='both',expand=True)
        self.panel.transcript.configure(yscrollcommand=self.panel.transcript_scrolled)
        self.panel._add('Codex','\n'.join(f'原文行 {i}' for i in range(200)),'stream')
        self.root.update();return self.panel.transcript

    def test_streaming_keeps_reader_position_and_selection(self):
        text=self.show_transcript();text.yview_moveto(.2);self.root.update()
        top=text.index('@0,0');text.tag_add('sel','45.0','45.end');selected=text.get('sel.first','sel.last')
        for i in range(10):self.panel._notification('item/agentMessage/delta',{'itemId':'stream','delta':f'\n增量 {i}'})
        self.root.update()
        self.assertEqual(text.index('@0,0'),top);self.assertEqual(text.get('sel.first','sel.last'),selected)
        self.assertNotIn('disabled',self.panel.latest_button.state())

    def test_bottom_reader_follows_and_latest_button_resumes_follow(self):
        text=self.show_transcript();text.yview_moveto(.1);self.root.update()
        self.panel.latest_button.invoke();self.root.update();self.assertGreater(text.yview()[1],.995)
        self.panel._notification('item/agentMessage/delta',{'itemId':'stream','delta':'\n最后新增'});self.root.update()
        self.assertGreater(text.yview()[1],.995);self.assertIn('disabled',self.panel.latest_button.state())

    def test_final_role_update_keeps_original_unicode_and_reference(self):
        self.panel._add('Codex','中文 😀\n[消息 #1]','unicode')
        self.panel._notification('item/agentMessage/delta',{'itemId':'unicode','delta':'\n尾部 🧪'})
        self.panel._notification('item/completed',{'item':{'id':'unicode','type':'agentMessage','phase':'final_answer','text':'中文 😀\n[消息 #1]\n尾部 🧪'}})
        self.assertEqual(self.panel.transcript.get('1.0','end-1c'),'中文 😀\n[消息 #1]\n尾部 🧪')
        self.assertEqual(self.panel.messages[-1]['role'],'Codex · 回答')
        self.assertIn('Codex · 回答\n中文 😀',self.panel.conversation_text())
        self.assertTrue(any(tag.startswith('reference_') for tag in self.panel.transcript.tag_names()))

    def test_new_conversation_clears_display_and_follow_control(self):
        self.panel._add('Codex','prior text');self.panel.new_conversation()
        self.assertEqual(self.panel.transcript.get('1.0','end-1c'),'')
        self.assertIn('disabled',self.panel.latest_button.state())
