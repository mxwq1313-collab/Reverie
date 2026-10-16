"""Full catalog, frozen per-turn options, icon actions and mapped-page behavior."""
import hashlib,json,sys,time
from pathlib import Path
import unittest
from unittest.mock import patch
import test_workbench as workbench_fixture
import test_agent as agent_fixture
from wechat_archive.agent import CodexClient,ArchiveScope
from wechat_archive.ui.icon_button import IconButton

ROOT=Path(__file__).resolve().parent
CATALOG=[{'model':'unit-main','id':'unit-main','displayName':'测试主模型','isDefault':True,'hidden':False,'defaultReasoningEffort':'medium',
 'supportedReasoningEfforts':[{'reasoningEffort':x} for x in ('low','medium','high','max','ultra')]},
 {'model':'unit-hidden','id':'unit-hidden','displayName':'隐藏测试模型','hidden':True,'defaultReasoningEffort':'low','supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]

class CodexControlsTests(unittest.TestCase):
    setUp=workbench_fixture.WorkbenchTests.setUp
    show=workbench_fixture.WorkbenchTests.show
    wait=agent_fixture.AgentPanelTests.wait
    def login(self,hold=False):
        self.panel=self.app.agent_panel
        self.panel.client_factory=lambda *a,**kw:CodexClient(*a,**kw,timeout=4,command=[sys.executable,'-B','-X','utf8','-u',str(ROOT/'fake_codex_server.py'),str(self.folder/'trace.jsonl'),*(['--hold'] if hold else [])])
        self.panel.open_browser=lambda _:True;self.panel.connect();self.wait(lambda:not self.panel.busy)
        self.panel.login();self.wait(lambda:self.panel.authenticated and not self.panel.busy)
        self.panel.set_catalog(CATALOG)
    def trace(self):return [json.loads(x) for x in (self.folder/'trace.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_only_current_page_maps_and_collapse_entry_is_unique(self):
        self.show();self.assertTrue(self.app.copilot_button.winfo_ismapped());self.assertTrue(self.app.copilot_hide_button.winfo_ismapped())
        for name in self.app.PAGE_NAMES:
            self.app.show_page(name);self.root.update()
            self.assertEqual([x for x in self.app.PAGE_NAMES if self.app.pages[x].winfo_ismapped()],[name])
        self.app.hide_copilot();self.root.update();self.assertTrue(self.app.copilot_button.winfo_ismapped());self.assertFalse(self.app.copilot_hide_button.winfo_ismapped())

    def test_icon_actions_have_accessible_labels_and_tooltips(self):
        self.show();panel=self.app.agent_panel
        for button in (panel.copy_button,panel.settings_button,panel.edit_question_button,self.app.copilot_hide_button):
            self.assertIsInstance(button,IconButton);self.assertTrue(button.cget('text'));self.assertTrue(button.cget('image'));self.assertEqual(str(button.cget('compound')),'image')
        panel.settings_button.show_tip();self.assertIsNotNone(panel.settings_button.tip)
        panel.settings_button.hide_tip();self.assertIsNone(panel.settings_button.tip);self.assertEqual(self.errors,[])

    def test_scope_button_changes_real_archive_identity_and_peer(self):
        self.show();panel=self.app.agent_panel;before=self.path.read_bytes();panel.scope_button.invoke();self.root.update()
        self.assertTrue(panel.scope_popup.winfo_exists());self.assertEqual(self.path.read_bytes(),before)
        panel.scope.set('当前身份的所有私聊');self.assertIsNone(panel.current_scope().peer_id)
        panel.scope.set('当前会话');self.assertEqual(panel.current_scope().peer_id,2);self.assertEqual(self.errors,[])

    def test_catalog_includes_hidden_model_and_effort_follows_model(self):
        panel=self.app.agent_panel;panel.set_catalog(CATALOG)
        self.assertIn('unit-hidden',panel.model_ids.values());self.assertIn('渡劫',panel.effort_box.cget('values'))
        panel.effort.set('渡劫');panel.model.set('隐藏测试模型 · unit-hidden')
        self.assertEqual(panel.effort.get(),'自动（模型默认）');self.assertEqual(tuple(panel.effort_box.cget('values')),('自动（模型默认）','练气'))
        self.assertEqual(panel.selected_effort(),'low')

    def test_model_effort_fast_are_sent_to_real_rpc_shape(self):
        self.login();p=self.panel;p.model.set('测试主模型 · unit-main');p.effort.set('渡劫');p.fast_mode.set(True);p.fill_prompt('离线请求参数检查');p.send()
        self.wait(lambda:not p.active and not p.busy)
        turn=next(x['params'] for x in self.trace() if x.get('method')=='turn/start')
        self.assertEqual((turn['model'],turn['effort'],turn['serviceTier']),('unit-main','ultra','fast'))
        self.assertTrue(any(x.get('method')=='model/list' and x['params']['includeHidden'] for x in self.trace()))

    def test_change_options_during_stream_keeps_current_output_and_next_request(self):
        self.login(True);p=self.panel;p.model.set('测试主模型 · unit-main');p.effort.set('金丹');p.fast_mode.set(True);p.fill_prompt('第一问');p.send();self.wait(lambda:not p.busy)
        first=next(x['params'] for x in self.trace() if x.get('method')=='turn/start')
        p.model.set('隐藏测试模型 · unit-hidden');p.fast_mode.set(False)
        p._notification('item/agentMessage/delta',{'threadId':'unit-thread','turnId':'unit-turn','itemId':'stream-options','delta':'原请求仍在回答'})
        self.wait(lambda:'原请求仍在回答' in p.transcript.get('1.0','end'))
        self.assertEqual((first['model'],first['effort'],first['serviceTier']),('unit-main','high','fast'))
        p._notification('turn/completed',{'threadId':'unit-thread','turn':{'id':'unit-turn','status':'completed'}})
        p.client.turn_id=None;p.fill_prompt('第二问');p.send();self.wait(lambda:not p.busy)
        turns=[x['params'] for x in self.trace() if x.get('method')=='turn/start']
        self.assertEqual((turns[-1]['model'],turns[-1]['effort'],turns[-1]['serviceTier']),('unit-hidden','low','default'))
        self.assertEqual(len([x for x in self.trace() if x.get('method')=='thread/start']),1)

    def test_settings_coalesce_and_restore_catalog_options(self):
        p=self.app.agent_panel;p.set_catalog(CATALOG)
        with patch.object(self.controller,'save_settings',wraps=self.controller.save_settings) as save:
            p.model.set('测试主模型 · unit-main');p.effort.set('金丹');p.fast_mode.set(True);p.effort.set('渡劫')
            self.assertEqual(save.call_count,0);p.flush_configuration();self.assertEqual(save.call_count,1)
        settings=self.controller.settings()['ai'];self.assertEqual((settings['effort'],settings['fast_mode']),('ultra',True));self.assertEqual(len(settings['model_catalog']),2)

    def test_add_page_has_no_empty_table_or_unexecuted_counters(self):
        self.show();self.app.show_page('电脑微信');self.root.update()
        self.assertFalse(self.app.source_tree.winfo_ismapped());self.assertFalse(self.app.source_cards.winfo_ismapped());self.assertTrue(self.app.detect_button.winfo_ismapped())
        self.assertLess(self.app.detect_button.winfo_rooty(),self.app.acquire_button.winfo_rooty());self.assertEqual(self.errors,[])

    def test_short_originals_stay_fully_visible_after_theme_and_language_changes(self):
        self.show(1400,860)
        for mode,language in (('dark','English'),('green','简体中文'),('light','English')):
            self.app.theme_choice.set({'dark':'深色','green':'松绿','light':'浅色'}[mode]);self.app.language_choice.set(language)
            self.app.apply_user_settings();self.root.update()
            first=self.app.chat_text.bubbles[1]['text'];self.assertGreaterEqual(first.yview()[1],.995)
            self.assertEqual(first.get('1.0','end-1c'),self.raw)
        self.assertEqual(self.errors,[])
