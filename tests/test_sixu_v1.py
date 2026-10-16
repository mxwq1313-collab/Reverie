"""Sixu 1.0 contracts on synthetic groups, opaque files and app-owned history."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image

from wechat_archive.errors import ConflictError,ValidationError,NotFoundError
from wechat_archive.importer.rich_importer import RichImporter,create_rich_archive,resource_path,media_root,sha_file
from wechat_archive.importer.rich_snapshot import RichSnapshotImporter
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.agent.history import ConversationHistory
from wechat_archive.agent.client import CodexClient
from wechat_archive.agent.tools import ArchiveScope
from wechat_archive.exporter import export_readable


class RichFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name);self.db=self.folder/'archive.db';create_rich_archive(self.db)
        Image.new('RGB',(80,60),'#518867').save(self.folder/'图片.png')
        (self.folder/'任意文件.bin').write_bytes(bytes(range(256))*16)
        self.payload={'format':'sixu-chat-exchange','format_version':'2.0','namespace':'unit-rich-namespace','users':[{'id':'unit_self','nickname':'自己'},{'id':'unit_peer','nickname':'伙伴'},{'id':'unit_other','nickname':'另一位'}],
            'chats':[{'id':'private','kind':'private','members':['unit_self','unit_peer'],'title':'私聊'},{'id':'group','kind':'group','members':['unit_self','unit_peer','unit_other'],'title':'自建群聊'}],
            'messages':[
                {'id':'private-1','chat_id':'private','sender_id':'unit_self','receiver_id':'unit_peer','kind':'text','content':'  原文 😀\n第二行  ','create_time':'2026-10-15T00:00:00Z'},
                {'id':'group-1','chat_id':'group','sender_id':'unit_self','kind':'text','content':'群内本人','create_time':'2026-10-15T00:01:00Z'},
                {'id':'group-2','chat_id':'group','sender_id':'unit_peer','kind':'emoji','content':'[表情]','create_time':'2026-10-15T00:02:00Z','attachments':[{'kind':'image','path':'图片.png'}]},
                {'id':'group-3','chat_id':'group','sender_id':'unit_other','kind':'file','content':'文件描述','create_time':'2026-10-15T00:03:00Z','attachments':[{'kind':'file','path':'任意文件.bin'}]}]}
        self.source=self.folder/'exchange.json';self.write()
    def write(self):self.source.write_text(json.dumps(self.payload,ensure_ascii=False),encoding='utf-8')
    def controller(self):
        c=ApplicationController(self.folder/'profile');c.open_archive(self.db);return c
    def importer(self):return RichImporter(self.db)
    def group(self,c):return next(x for x in c.contacts(1) if x['kind']=='group')


class RichArchiveTests(RichFixture):
    def test_upgrade_from_legacy_external_reuses_identity_and_messages(self):
        from test_external_source import data
        from wechat_archive.wechat_adapter import WeChatImporter
        from wechat_archive.migration.copy_upgrade import upgrade_archive_copy
        payload=data();old=self.folder/'legacy.db';source=self.folder/'legacy.json';source.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        report=WeChatImporter(old,adapter='external',report_dir=self.folder/'logs').import_file(source);self.assertEqual(report.success_count,2)
        target=self.folder/'upgraded.db';upgrade_archive_copy(old,target)
        owner=payload['account']['wxid'];peer=payload['conversation']['wxid']
        rich={'format':'sixu-chat-exchange','format_version':'2.0','namespace':'wechat:'+owner,'users':[{'id':owner,'nickname':'自己'},{'id':peer,'nickname':'对方'}],
              'chats':[{'id':peer,'kind':'private','members':[owner,peer]}],'messages':[]}
        from datetime import datetime,timezone
        for record in payload['records']:
            sender=record['sender_wxid'];rich['messages'].append({'id':json.dumps([record['source_database'],record['source_id_kind'],record['source_message_id']],separators=(',',':')),
                'chat_id':peer,'sender_id':sender,'receiver_id':peer if sender==owner else owner,'create_time':datetime.fromtimestamp(record['timestamp'],timezone.utc).isoformat(),'kind':'text','content':record['content']})
        source=self.folder/'upgraded_input.json';source.write_text(json.dumps(rich,ensure_ascii=False),encoding='utf-8');result=RichImporter(target).import_file(source)
        self.assertEqual((result.success_count,result.duplicated_count,result.users_created_count),(0,2,0))
        with sqlite3.connect(target) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],2)

    def test_group_directions_counts_and_membership_isolation(self):
        report=self.importer().import_file(self.source);self.assertEqual(report.success_count,4)
        c=self.controller();group=self.group(c);self.assertEqual((group['own_count'],group['message_count']),(1,3));self.assertAlmostEqual(group['own_ratio'],1/3)
        self.assertEqual(sum(x['message_count'] for x in group['members']),3)
        rows=c.messages(1,group['id'])['items'];self.assertTrue(all(x['receiver_id'] is None for x in rows));self.assertEqual([x['sender_id'] for x in rows],[1,2,3])
        with sqlite3.connect(self.db) as conn:conn.execute("INSERT INTO users(wxid,nickname) VALUES ('unit_outside','旁观者')")
        with self.assertRaises(NotFoundError):c.messages(4,group['id'])

    def test_duplicate_and_source_conflict_never_merge_events(self):
        self.importer().import_file(self.source);self.assertEqual(self.importer().import_file(self.source).duplicated_count,4)
        before=sha_file(self.db);self.payload['messages'][0]['content']='变更正文';self.write()
        with self.assertRaises(ConflictError):self.importer().import_file(self.source)
        self.assertEqual(sha_file(self.db),before)
        self.payload['messages'][0]['id']='new-event';self.write();self.assertEqual(self.importer().import_file(self.source).success_count,1)

    def test_opaque_binary_and_original_text_round_trip_export(self):
        self.importer().import_file(self.source);c=self.controller();group=self.group(c)
        result=export_readable(self.db,self.folder/'export',user_id=1,peer_id=group['id'])
        self.assertEqual(result['messages'],3);manifest=json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
        binaries=[x for x in manifest['files'] if x['name'].endswith('.bin')];self.assertEqual(len(binaries),1)
        self.assertEqual((self.folder/'export'/binaries[0]['name']).read_bytes(),(self.folder/'任意文件.bin').read_bytes())
        for row in manifest['files']:self.assertEqual(sha_file(self.folder/'export'/row['name']),row['sha256'])
        self.assertEqual(c.messages(1,2)['items'][0]['content'],'  原文 😀\n第二行  ')

    def test_attachment_tamper_and_missing_recovery(self):
        file=self.folder/'任意文件.bin';original=file.read_bytes();file.unlink();self.importer().import_file(self.source)
        c=self.controller();row=c.messages(1,self.group(c)['id'])['items'][-1];self.assertEqual(row['attachments'][0]['availability'],'missing')
        file.write_bytes(original);self.importer().import_file(self.source);row=c.messages(1,self.group(c)['id'])['items'][-1];self.assertEqual(row['attachments'][0]['availability'],'ready')
        file.write_bytes(b'changed')
        with self.assertRaises(ConflictError):self.importer().import_file(self.source)

    def test_attachment_paths_and_resource_root_rejected(self):
        for value in ('../private.txt','C:/secret.txt','/absolute','x\\file','x\x00y'):
            with self.assertRaises(ValidationError):resource_path(self.folder,value)
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(ValidationError):resource_path(self.folder,'normal.txt')

    def test_unknown_type_retained_report_and_strict_rolls_back(self):
        self.payload['messages'][0]['kind']='unknown';self.write();report=self.importer().import_file(self.source)
        self.assertEqual((report.status,report.success_count,report.failed_count),('partial',3,1));self.assertTrue(self.source.exists())
        other=self.folder/'strict.db';create_rich_archive(other)
        with self.assertRaises(ValidationError):RichImporter(other,strict=True).import_file(self.source)
        with sqlite3.connect(other) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],0)

    def test_old_archive_preserved_and_rich_requires_copy(self):
        from wechat_archive import ChatService
        old=self.folder/'old.db';ChatService(old);before=sha_file(old)
        with self.assertRaises(ValidationError):RichImporter(old).import_file(self.source)
        self.assertEqual(sha_file(old),before)

    def test_global_group_search_context_returns_original(self):
        self.importer().import_file(self.source);c=self.controller();group=self.group(c)
        found=c.messages(1,None,'本人');self.assertEqual(found['total'],1)
        context=c.message_context(1,found['items'][0]['id']);self.assertEqual(context['peer_id'],group['id']);self.assertEqual(context['total'],3)


class HistoryStoreTests(unittest.TestCase):
    def test_app_owned_persistence_and_invalid_files_are_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=ConversationHistory(temporary);value=store.save({'title':'合成问题','scope':['synthetic.db',1,2],'messages':[{'role':'你','text':'保留原文\n😀'}]})
            self.assertEqual(store.read(value['id'])['messages'][0]['text'],'保留原文\n😀')
            self.assertEqual(len(ConversationHistory(temporary).list('问题')),1)
            (store.directory/'invalid.json').write_text('broken',encoding='utf-8');self.assertEqual(len(store.list()),1)
            with self.assertRaises(ValidationError):store.read('../escape')

    def test_thread_resume_rebinds_tools_and_rejects_wrong_thread(self):
        from test_agent import ArchiveToolTests
        fixture=ArchiveToolTests();fixture.setUp()
        try:
            scope=ArchiveScope(fixture.path,1,2);client=CodexClient(Path(fixture.temp.name)/'profile')
            client.request=lambda method,params:{'thread':{'id':'unit-history'}}
            client.resume_conversation('unit-history',scope);self.assertEqual(client.scope_key,scope.key);self.assertIsNotNone(client.tools)
            client.request=lambda method,params:{'thread':{'id':'wrong'}}
            with self.assertRaises(Exception):client.resume_conversation('unit-history',scope)
            self.assertIsNone(client.tools)
            def revoked(method,params):
                client.revoke_tools();return {'thread':{'id':'unit-history'}}
            client.request=revoked
            with self.assertRaises(ConflictError):client.resume_conversation('unit-history',scope,expected_epoch=client.scope_epoch)
            self.assertIsNone(client.tools)
        finally:fixture.doCleanups()


class RichUITests(RichFixture):
    def test_history_restores_live_rpc_thread_and_continues_same_scope(self):
        import sys,time
        self.importer().import_file(self.source);c=self.controller();root=tk.Tk();root.geometry('1400x860');app=ApplicationWindow(root,controller=c)
        def wait(predicate):
            deadline=time.monotonic()+12
            while not predicate() and time.monotonic()<deadline:root.update();time.sleep(.01)
            root.update();self.assertTrue(predicate())
        try:
            app.owner_id=1;app.peer_id=2;app.load_contacts();root.update();panel=app.agent_panel
            command=[sys.executable,'-B','-X','utf8','-u',str(Path(__file__).parent/'fake_codex_server.py'),str(self.folder/'trace.jsonl')]
            panel.client_factory=lambda *args,**kw:CodexClient(*args,**kw,timeout=4,command=command);panel.open_browser=lambda _:True
            panel.connect();wait(lambda:not panel.busy);panel.login();wait(lambda:panel.authenticated and not panel.busy)
            panel.fill_prompt('合成历史提问');panel.send();wait(lambda:not panel.active and not panel.busy);panel.flush_history()
            saved=panel.history_store.list();self.assertEqual(len(saved),1);self.assertEqual(panel.history_store.read(saved[0]['id'])['thread_id'],'unit-thread')
            panel.new_conversation();panel.show_history();root.update();popup=panel.history_popup
            tree=next(w for w in app.descendants(popup) if w.winfo_class()=='Treeview');tree.selection_set(saved[0]['id'])
            button=next(w for w in app.descendants(popup) if w.winfo_class()=='TButton' and w.cget('text')=='继续对话');button.invoke();wait(lambda:not panel.busy)
            self.assertEqual(panel.client.thread_id,'unit-thread');self.assertIn('合成历史提问',panel.transcript.get('1.0','end'))
            panel.fill_prompt('继续同一线程');panel.send();wait(lambda:not panel.active and not panel.busy)
            trace=[json.loads(x) for x in (self.folder/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(sum(x.get('method')=='thread/start' for x in trace),1);self.assertTrue(any(x.get('method')=='thread/resume' for x in trace))
            self.assertFalse(next(x['params']['ephemeral'] for x in trace if x.get('method')=='thread/start'))
        finally:app.close()

    def test_group_media_history_and_parameter_ui_are_real(self):
        self.importer().import_file(self.source);c=self.controller();root=tk.Tk();root.geometry('1400x860');errors=[];root.report_callback_exception=lambda *x:errors.append(x)
        app=ApplicationWindow(root,controller=c)
        try:
            app.owner_id=1;app.peer_id=self.group(c)['id'];app.load_contacts();root.update();self.assertEqual(len(app.message_rows),3)
            panel=app.agent_panel;self.assertTrue(panel.history_button.winfo_ismapped());panel.parameters_button.invoke();root.update();self.assertTrue(panel.power_model_button.winfo_ismapped());self.assertTrue(panel.power_slider.winfo_ismapped())
            self.assertEqual(panel.model_box.master,panel.effort_box.master);panel.parameters_popup.withdraw()
            self.assertIn('本人',app.contact_tree.cards[str(app.peer_id)][-1].cget('text'))
            self.assertTrue(any(hasattr(w,'attachment_item') for w in app.descendants(app.chat_text)))
            self.assertFalse(any(w.cget('text')=='另存附件' for w in app.descendants(app.chat_text) if w.winfo_class()=='TButton'))
            app.show_page('帮助');root.update();reader=app.help_reader;reader.query.set('历史');root.update();self.assertTrue(reader.visible);self.assertIn('历史',reader.text.get('1.0','end'))
            self.assertEqual(errors,[])
        finally:app.close()
