"""Resident sidebar and context injection with real Tk events and an offline server."""
import json
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_workbench as workbench_fixture
import test_agent as agent_fixture
from wechat_archive.agent import CodexClient
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow

ROOT=Path(__file__).resolve().parent


class CopilotUITests(unittest.TestCase):
    setUp=workbench_fixture.WorkbenchTests.setUp
    show=workbench_fixture.WorkbenchTests.show
    wait=agent_fixture.AgentPanelTests.wait

    def login(self,hold=False):
        self.panel=self.app.agent_panel
        def factory(*args,**kwargs):
            return CodexClient(*args,**kwargs,timeout=3,command=[sys.executable,'-B','-X','utf8','-u',str(ROOT/'fake_codex_server.py'),str(self.folder/'trace.jsonl'),*(['--hold'] if hold else [])])
        self.panel.client_factory=factory;self.panel.open_browser=lambda _:True
        self.panel.connect();self.wait(lambda:not self.panel.busy)
        self.panel.login();self.wait(lambda:self.panel.authenticated and not self.panel.busy)

    def test_default_resident_sidebar_survives_all_pages_without_starting_client(self):
        self.show(1240,820);panel=self.app.agent_panel
        self.assertTrue(panel.compact);self.assertTrue(self.app.copilot_expanded);self.assertEqual(self.app.copilot_mode,'docked')
        self.assertIsNone(panel.client)
        for page in self.app.PAGE_NAMES:
            self.app.show_page(page);self.root.update();self.assertIs(self.app.agent_panel,panel)
            self.assertTrue(self.app.copilot_host.winfo_ismapped())
        self.assertIsNone(panel.client)

    def test_collapse_width_drag_and_restore_keep_reading_and_settings(self):
        before=self.path.read_bytes();self.show(1240,820)
        panes=self.app.workspace_panes;panes.sash_place(0,panes.winfo_width()-self.app.theme.u(425)-int(panes.cget('sashwidth')),0)
        self.app.save_copilot_sash();self.assertAlmostEqual(self.controller.copilot_layout()['width'],425,delta=3)
        self.app.hide_copilot();self.assertFalse(self.controller.copilot_layout()['expanded'])
        root=tk.Tk();root.withdraw();other=ApplicationWindow(root,controller=ApplicationController(self.controller.data_dir))
        try:self.assertFalse(other.copilot_expanded);self.assertAlmostEqual(other.copilot_width,425,delta=3)
        finally:other.close()
        self.assertEqual(before,self.path.read_bytes())

    def test_small_window_drawer_keeps_input_and_send_inside_sidebar(self):
        for width,height in ((820,600),(900,650),(1100,720),(1240,820)):
            self.show(width,height);self.root.update()
            host=self.app.copilot_body;panel=self.app.agent_panel
            self.assertGreater(self.app.chat_text.winfo_width(),280)
            self.assertLessEqual(panel.send_button.winfo_rooty()+panel.send_button.winfo_height(),host.winfo_rooty()+host.winfo_height())
            self.assertGreater(panel.input.winfo_height(),30)
            self.assertTrue(self.app.search_entry.winfo_ismapped());self.assertGreater(self.app.search_entry.winfo_width(),35)
        self.assertEqual(self.errors,[])

    def test_ctrl_l_any_page_and_escape_do_not_clear_chat_search(self):
        self.show();self.app.search_word.set('论文修改');self.app.load_messages()
        for page in self.app.PAGE_NAMES:
            self.app.show_page(page);self.app.hide_copilot();self.root.update()
            self.root.focus_force();self.root.event_generate('<Control-l>');self.root.update()
            self.assertTrue(self.app.copilot_expanded);self.assertIs(self.root.focus_get(),self.app.agent_panel.input)
            self.app.agent_panel.input.event_generate('<Escape>');self.root.update()
            self.assertIsNot(self.root.focus_get(),self.app.agent_panel.input)
            self.assertEqual(self.app.search_word.get(),'论文修改')

    def test_ask_button_binds_conversation_and_context_reaches_real_transport_shape(self):
        self.login();self.app.ask_ai_button.invoke();self.panel.fill_prompt('这个人说过什么？')
        self.panel.send_shortcut();self.wait(lambda:not self.panel.busy and not self.panel.active)
        rows=[json.loads(line) for line in (self.folder/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        turn=next(row for row in rows if row.get('method')=='turn/start')
        text=turn['params']['input'][0]['text'];payload=json.loads(text[text.index('{'):])
        self.assertEqual(payload['user_question'],'这个人说过什么？')
        context=payload['current_context'];self.assertEqual((context['user_id'],context['peer_id']),(1,2))
        self.assertEqual(context['conversation_id'],'private:1:2');self.assertNotIn(self.raw,text)
        self.assertNotIn(str(self.folder),json.dumps(context,ensure_ascii=False))
        self.assertEqual(len(next(row for row in rows if row.get('method')=='thread/start')['params']['dynamicTools']),5)

    def test_search_metadata_is_applied_and_question_display_stays_original(self):
        self.login();self.app.search_word.set('论文修改');self.app.start_date.set('2026-10-10');self.app.load_messages()
        self.app.search_word.set('not yet applied');self.panel.fill_prompt('整理当前范围');self.panel.send()
        self.wait(lambda:not self.panel.busy and not self.panel.active)
        context=self.panel.last_context;self.assertEqual(context.search_query,'论文修改')
        self.assertEqual(context.date_filter[0],'2026-10-10');self.assertEqual(self.panel.messages[0]['text'],'整理当前范围')

    def test_reading_can_change_during_answer_and_old_tools_are_revoked(self):
        self.login(hold=True);self.panel.fill_prompt('暂时保持回合');self.panel.send()
        self.wait(lambda:not self.panel.busy and self.panel.active);self.assertFalse(self.app.busy)
        self.app.contact_tree.selection_set('3');self.app.select_contact();self.root.update()
        self.assertEqual(self.app.peer_id,3);self.assertEqual(self.app.message_rows[0]['id'],self.second)
        self.wait(lambda:not self.panel.busy and self.panel.client.tools is None)
        self.assertTrue(self.panel.client.connected)

    def test_revocation_during_thread_start_cannot_restore_tool_authority(self):
        self.login();client=self.panel.client;request=client.request
        def guarded(method,*args,**kwargs):
            result=request(method,*args,**kwargs)
            if method=='thread/start':client.revoke_tools()
            return result
        self.panel.fill_prompt('race question')
        with patch.object(client,'request',side_effect=guarded):
            self.panel.send();self.wait(lambda:not self.panel.busy)
        self.assertIsNone(client.tools);self.assertIn('已撤销',self.panel.state.get())
        rows=[json.loads(line) for line in (self.folder/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertFalse(any(row.get('method')=='turn/start' for row in rows))

    def test_invalid_layout_preferences_fall_back_without_touching_archive(self):
        settings=self.controller.settings();settings['copilot_layout']={'expanded':'yes','width':True};self.controller.save_settings(settings)
        self.assertEqual(self.controller.copilot_layout(),{'expanded':True,'width':360})

    def test_drawer_grip_adjustment_saves_logical_width(self):
        self.show(900,650);self.assertEqual(self.app.copilot_mode,'drawer')
        self.app.start_copilot_drag(SimpleNamespace(x_root=600));self.app.drag_copilot(SimpleNamespace(x_root=565));self.app.persist_copilot_layout()
        self.assertAlmostEqual(self.controller.copilot_layout()['width'],395,delta=3)

    def test_source_change_while_answering_revokes_context_and_keeps_connection(self):
        self.login(hold=True);self.panel.fill_prompt('保持待验收回合');self.panel.send()
        self.wait(lambda:not self.panel.busy and self.panel.active)
        self.controller.manage_message('update',message_id=1,content='改动后的自建原文')
        self.wait(lambda:not self.panel.busy and not self.panel.messages)
        self.assertIsNone(self.panel.client.tools);self.assertTrue(self.panel.client.connected)
        self.assertIn('原文已变化',self.panel.state.get())

    def test_reading_preferences_preserve_saved_copilot_layout(self):
        self.controller.save_copilot_layout(False,410)
        self.controller.save_preferences(17,True)
        self.assertEqual(self.controller.copilot_layout(),{'expanded':False,'width':410})

    def test_late_turn_response_cannot_restore_active_state_after_revocation(self):
        self.login(hold=True);client=self.panel.client;request=client.request
        def guarded(method,*args,**kwargs):
            result=request(method,*args,**kwargs)
            if method=='turn/start':client.revoke_tools()
            return result
        self.panel.fill_prompt('late response question')
        with patch.object(client,'request',side_effect=guarded):
            self.panel.send();self.wait(lambda:not self.panel.busy)
        self.assertFalse(client.active);self.assertIsNone(client.tools)
        self.assertIn('已撤销',self.panel.state.get())

    def test_empty_identity_during_answer_revokes_previous_authority(self):
        self.login(hold=True);self.panel.fill_prompt('保持旧范围回合');self.panel.send()
        self.wait(lambda:not self.panel.busy and self.panel.active)
        self.app.owner_box.current(3);self.app.change_owner()
        self.wait(lambda:not self.panel.busy and self.panel.client.tools is None and not self.panel.messages)
        self.assertTrue(self.panel.client.connected);self.assertIsNone(self.panel.client.scope_key)
        self.assertIn('无有效会话',self.panel.state.get())

    def test_narrow_search_shortcut_uncovers_reader_and_focuses_search(self):
        self.show(900,650);self.app.open_copilot();self.root.update()
        canvas=self.app.contact_tree.canvas;canvas.focus_force();self.root.update()
        canvas.event_generate('<Control-f>');self.root.update()
        self.assertFalse(self.app.copilot_expanded);self.assertIs(self.root.focus_get(),self.app.search_entry)

    def test_switch_away_and_back_cannot_revive_a_prepared_request(self):
        self.login();client=self.panel.client;scope=self.panel.current_scope()
        request=self.panel.ai_service.prepare('之前准备的问题',scope,expected_epoch=client.scope_epoch)
        self.app.peer_id=3;self.app.notify_copilot_binding();self.app.peer_id=2;self.app.notify_copilot_binding()
        with self.assertRaises(Exception) as failure:self.panel.ai_service.send(client,request)
        self.assertIn('已撤销',str(failure.exception));self.assertIsNone(client.tools)
