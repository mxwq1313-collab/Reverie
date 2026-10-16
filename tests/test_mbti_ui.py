"""Synthetic MBTI transport, scope changes and image presentation contracts."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

from test_sixu_v1 import RichFixture
from wechat_archive.agent import CodexClient
from wechat_archive.ai.personality import mbti_prompt
from wechat_archive.errors import ValidationError
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ui.mbti_panel import open_mbti, participants


class MBTIUITests(RichFixture):
    def app(self, login=False):
        self.importer().import_file(self.source)
        root=tk.Tk();errors=[];root.report_callback_exception=lambda *args:errors.append(str(args))
        app=ApplicationWindow(root,controller=self.controller());self.addCleanup(app.close)
        root.update();app.owner_id=1;app.peer_id=2;app.load_contacts();root.update()
        self.assertEqual(errors,[])
        self.errors=errors
        if login:
            panel=app.agent_panel
            panel.client_factory=lambda *args,**kwargs:CodexClient(*args,**kwargs,timeout=5,command=[sys.executable,'-B','-X','utf8','-u',str(Path(__file__).with_name('fake_codex_server.py')),str(self.folder/'trace.jsonl')])
            panel.open_browser=lambda _:True
            panel.connect();self.wait(app,lambda:not panel.busy)
            panel.login();self.wait(app,lambda:panel.authenticated and not panel.busy)
            self.wait(app,lambda:not panel.busy)
        return app

    def wait(self,app,condition):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            app.root.update()
            if condition():return
            time.sleep(.01)
        self.fail('Timed out: '+app.agent_panel.state.get())

    def test_top_entry_gates_login_and_no_archive_does_not_start_client(self):
        app=self.app();self.assertEqual(app.mbti_button.cget('text'),'MBTI')
        self.assertEqual(str(app.brand_label.cget('text')),'思绪')
        captions=[w.cget('text') for w in app.descendants(app.header) if w.winfo_class()=='TButton']
        self.assertNotIn('新建归档',captions);self.assertNotIn('打开归档',captions)
        app.mbti_button.invoke();app.root.update();window=app.mbti_popup
        self.assertIn('disabled',window.mbti_start.state());self.assertIn('登录',window.mbti_hint.get())
        self.assertIsNone(app.agent_panel.client);window.destroy()
        app.controller.database=None;app.owner_id=None
        window=open_mbti(app);app.root.update();self.assertIn('disabled',window.mbti_start.state())
        self.assertEqual(participants(app,'当前会话'),[])

    def test_group_selects_real_members_all_private_only_owner(self):
        app=self.app();app.peer_id=self.group(app.controller)['id'];app.load_contacts()
        window=open_mbti(app);app.root.update()
        self.assertEqual({x['id'] for x in participants(app,'当前会话')},{1,2,3})
        window.mbti_mode.set('当前身份的所有私聊');window.mbti_refresh()
        self.assertEqual({x['id'] for x in participants(app,'当前身份的所有私聊')},{1})
        self.assertIn('#1',window.mbti_target.get())

    def test_start_uses_existing_scoped_codex_transport_and_history(self):
        app=self.app(login=True);panel=app.agent_panel
        before=app.controller.database.read_bytes()
        window=open_mbti(app);app.root.update();window.mbti_target.set('伙伴 · #2');window.mbti_start.invoke()
        self.wait(app,lambda:not panel.busy and not panel.active)
        self.assertTrue(any('MBTI' in x['text'] for x in panel.messages))
        self.assertNotIn('archive_messages',panel.messages[0]['text'])
        trace=[json.loads(line) for line in (self.folder/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        turn=next(x for x in trace if x.get('method')=='turn/start')
        text=turn['params']['input'][0]['text'];payload=json.loads(text[text.index('{'):])
        self.assertIn('sender_id=2',payload['user_question']);self.assertIn('[消息 #ID]',payload['user_question'])
        self.assertEqual((payload['current_context']['user_id'],payload['current_context']['peer_id']),(1,2))
        panel.flush_history();self.assertEqual(len(panel.history_store.list()),1)
        self.assertEqual(app.controller.database.read_bytes(),before);self.assertEqual(self.errors,[])

    def test_changed_archive_binding_rejects_stale_analysis(self):
        app=self.app(login=True);window=open_mbti(app);app.root.update()
        app.peer_id=self.group(app.controller)['id'];app.load_contacts();window.mbti_start.invoke()
        self.assertIn('变化',window.mbti_hint.get());self.assertFalse(app.agent_panel.messages)

    def test_all_private_mode_uses_owner_and_excludes_groups(self):
        app=self.app(login=True);panel=app.agent_panel
        app.peer_id=self.group(app.controller)['id'];app.load_contacts()
        window=open_mbti(app);window.mbti_mode.set('当前身份的所有私聊');window.mbti_refresh();window.mbti_start.invoke()
        self.wait(app,lambda:not panel.busy and not panel.active)
        trace=[json.loads(line) for line in (self.folder/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        turn=next(x for x in trace if x.get('method')=='turn/start');text=turn['params']['input'][0]['text'];payload=json.loads(text[text.index('{'):])
        self.assertIsNone(payload['current_context']['peer_id']);self.assertIn('sender_id=1',payload['user_question'])
        self.assertNotIn('群内本人',text)

    def test_changed_filters_cannot_send_a_stale_scope_description(self):
        app=self.app(login=True);window=open_mbti(app)
        app.search_word.set('新的筛选');app.load_messages();window.mbti_start.invoke()
        self.assertIn('变化',window.mbti_hint.get());self.assertFalse(app.agent_panel.messages)

    def test_mbti_layout_and_search_survive_large_text_and_small_windows(self):
        app=self.app()
        for width,height,theme,size in ((820,600,'dark',24),(1240,820,'green',15)):
            app.root.geometry(f'{width}x{height}');app.theme.update(size,app.theme.family,theme,'zh_CN',48);app.adapt_layout();app.root.update()
            self.assertGreater(app.search_entry.winfo_width(),35)
            window=open_mbti(app);app.root.update()
            self.assertLessEqual(window.mbti_start.winfo_rooty()+window.mbti_start.winfo_height(),window.winfo_rooty()+window.winfo_height())
            self.assertGreater(window.mbti_start.winfo_height(),15)
            window.destroy()

    def test_retry_retains_task_instructions_with_short_display_question(self):
        app=self.app(login=True);panel=app.agent_panel
        panel.fill_prompt('分析伙伴的 MBTI');task=mbti_prompt(2,'伙伴','当前会话')
        panel.send(task_text=task);self.wait(app,lambda:not panel.busy and not panel.active)
        panel.pending_request={'question':'分析伙伴的 MBTI','task_text':task,'scope':panel.current_scope().key,'token':app.controller.archive_view_token(),'model':panel.model.get(),'effort':panel.effort.get(),'fast_mode':panel.fast_mode.get()}
        panel.remember_failed_question()
        with patch.object(panel,'send') as send:panel.retry_question()
        send.assert_called_once_with(task_text=task)

    def test_invalid_target_rejected_and_evidence_contract_is_explicit(self):
        for value in (-1,0,True,'1'):
            with self.assertRaises(ValidationError):mbti_prompt(value,'对象','当前会话')
        text=mbti_prompt(2,'伙伴','当前会话')
        for required in ('反向证据','实际读取','暂无法判断','sender_id=2','archive_messages','[消息 #ID]'):
            self.assertIn(required,text)

    def test_roles_hidden_colors_distinct_and_only_suffix_animates(self):
        app=self.app();panel=app.agent_panel
        panel._add('你','问题 😀');panel._add('Codex · 回答','回答\n[消息 #1]')
        self.assertEqual(panel.transcript.get('1.0','end-1c'),'问题 😀\n\n回答\n[消息 #1]')
        self.assertNotEqual(panel.transcript.tag_cget('turn_user','background'),panel.transcript.tag_cget('turn_codex','background'))
        self.assertTrue(any(x.startswith('reference_') for x in panel.transcript.tag_names()))
        panel.active=True;panel._controls();values=[]
        for _ in range(3):
            if panel.reply_job:app.root.after_cancel(panel.reply_job)
            panel.animate_reply();values.append(panel.reply_indicator.get())
        self.assertEqual(set(values),{'千丝万绪.','千丝万绪..','千丝万绪...'})
        panel.active=False;panel._controls();self.assertEqual(panel.reply_indicator.get(),'')
        self.assertIn('你\n问题',panel.conversation_text())

    def test_image_is_unframed_and_opens_actions_only_on_click(self):
        app=self.app();app.peer_id=self.group(app.controller)['id'];app.load_contacts();app.root.update()
        row=next(row for row in app.message_rows if any(x['kind']=='image' for x in row['attachments']))
        outer=app.chat_text.bubbles[row['id']]['outer']
        self.assertFalse(app.chat_text.bubbles[row['id']]['bubble'].winfo_manager())
        canvases=[w for w in app.descendants(outer) if w.winfo_class()=='Canvas' and w.cget('cursor')=='hand2']
        self.assertEqual(len(canvases),1);canvas=canvases[0]
        self.wait(app,lambda:hasattr(canvas,'image'))
        self.assertEqual((int(canvas.cget('width')),int(canvas.cget('height'))),(80,60))
        self.assertEqual(int(canvas.cget('highlightthickness')),0)
        self.assertFalse(any(w.winfo_class()=='TButton' for w in app.descendants(outer)))
        with patch('wechat_archive.ui.media_widgets.preview_image') as preview:
            canvas.event_generate('<Button-1>');app.root.update();preview.assert_called_once()
        self.assertEqual(self.errors,[])

    def test_text_buttons_have_no_repeated_hint_icon_uses_soft_theme(self):
        app=self.app();app.show_page('电脑微信');app.root.update()
        self.assertFalse(hasattr(app.detect_button,'_action_hint'))
        app.copilot_button.show_tip();app.root.update()
        hint=app.copilot_button._action_hint.tip
        labels=[w for w in app.descendants(hint) if w.winfo_class()=='Label']
        self.assertEqual(labels[0].cget('background'),app.theme.palette['HOVER'])
        self.assertEqual(labels[0].cget('foreground'),app.theme.palette['INK'])
        app.copilot_button.hide_tip()
