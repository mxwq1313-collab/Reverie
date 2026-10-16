import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
import test_agent as app_fixture
from wechat_archive.knowledge.rag import RagService


class KnowledgeUITests(unittest.TestCase):
    setUp=app_fixture.AgentPanelTests.setUp
    wait=app_fixture.AgentPanelTests.wait

    @property
    def knowledge(self): return self.app.knowledge_panel

    def ready(self):
        panel=self.knowledge; self.wait(lambda:panel.context()==panel.last_context)
        panel.sync(); self.wait(lambda:not panel.busy)
        self.assertIn('索引已更新',panel.state.get()); return panel

    def test_new_route_and_offline_default_no_automatic_model_calls(self):
        panel=self.knowledge; self.app.show_page('本地知识问答')
        self.assertEqual(self.app.current_page,'工具与设置')
        self.assertEqual(panel.models,[]); self.assertIn('离线',panel.kind.get()); self.assertFalse(panel.busy)
        self.assertFalse(panel.advanced.expanded); self.assertIn('disabled',panel.ask_button.state())

    def test_offline_sync_search_original_preview(self):
        panel=self.ready(); panel.input.insert('1.0','单元记录'); panel.search(); self.wait(lambda:not panel.busy)
        self.assertEqual(len(panel.hits),1)
        panel.tree.selection_set('0'); self.root.update()
        self.assertIn('原文',panel.output.get('1.0','end')); self.assertIn('单元记录',panel.output.get('1.0','end'))
        self.assertEqual(panel.output['state'],'disabled'); self.assertIn('字面',panel.state.get())

    def test_scope_switch_and_source_edit_clear_results(self):
        panel=self.ready(); panel.input.insert('1.0','单元记录'); panel.search(); self.wait(lambda:not panel.busy)
        panel.scope.set('当前身份的所有私聊'); self.assertEqual(panel.hits,[])
        panel.sync(); self.wait(lambda:not panel.busy); panel.search(); self.wait(lambda:not panel.busy)
        self.controller.manage_message('update',message_id=1,content='已修改')
        self.wait(lambda:panel.hits==[]); self.assertIn('变化',panel.state.get())

    def test_cancelled_worker_cannot_restore_results_and_blocks_overlap(self):
        panel=self.knowledge; self.wait(lambda:panel.context()==panel.last_context)
        released=threading.Event(); self.addCleanup(released.set)
        panel.run(lambda *_:released.wait(2) or [],lambda result:panel.write('stale'))
        panel.cancel(); self.assertTrue(panel.busy)
        panel.run(lambda *_:[],lambda _:panel.write('overlap'))
        self.assertEqual(panel.running,1); released.set(); self.wait(lambda:not panel.busy)
        self.assertEqual(panel.output.get('1.0','end').strip(),'')

    def test_answer_copy_save_no_overwrite_and_scope_revoke(self):
        panel=self.ready(); panel.models=['fixture']; panel.chat_model.set('fixture')
        panel.input.insert('1.0','单元记录')
        class Generator:
            model='fixture'; last_revision='synthetic'
            def generate(self,*_): return {'claims':[{'text':'原文包含测试记录。','citations':['E1']}]}
        with patch('wechat_archive.ui.knowledge_panel.OllamaGenerator',return_value=Generator()):
            panel.ask(); self.wait(lambda:not panel.busy)
        self.assertIsNotNone(panel.answer); panel.copy(); self.assertIn('[证据1]',self.root.clipboard_get())
        target=self.folder/'answer.txt'
        with patch('wechat_archive.ui.knowledge_panel.filedialog.asksaveasfilename',return_value=str(target)):
            panel.save(); original=target.read_bytes(); panel.save()
        self.assertEqual(target.read_bytes(),original); self.assertIn('未完成',panel.state.get())
        panel.scope.set('当前身份的所有私聊'); self.assertIsNone(panel.answer)
        self.assertIn('disabled',panel.copy_button.state())

    def test_controls_scope_and_shortcut(self):
        panel=self.knowledge; self.app.owner_id=None; panel.controls()
        self.assertIn('disabled',panel.sync_button.state())
        self.app.owner_id=1; panel.input.insert('1.0','question')
        with patch.object(panel,'search') as search:
            self.assertEqual(panel.shortcut(),'break'); search.assert_called_once()


if __name__=='__main__': unittest.main()
