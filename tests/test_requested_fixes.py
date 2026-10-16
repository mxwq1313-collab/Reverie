"""Screenshot regressions, using only generated archives and source shards."""
import json
import sqlite3
from contextlib import closing
import sys
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from test_sixu_v1 import RichFixture
import test_rich_source as source_fixture
import unittest
from wechat_archive.agent import ArchiveScope,ArchiveTools,CodexClient
from wechat_archive.errors import NotFoundError,ValidationError
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.media_widgets import present_content
from wechat_archive.importer.rich_importer import sha_file,media_root


class RequestedDataTests(RichFixture):
    def test_unmapped_private_and_group_messages_preserve_assets_and_ratios(self):
        self.payload['messages'].append({'id':'unmapped-private','chat_id':'private','sender_id':None,'receiver_id':'unit_self','kind':'system','content':'[发送者未映射]\n可读正文','create_time':'2026-10-15T00:04:00Z'})
        self.payload['messages'].append({'id':'unmapped-group','chat_id':'group','sender_id':None,'kind':'system','content':'[发送者未映射]\n文件','create_time':'2026-10-15T00:05:00Z','attachments':[{'kind':'file','path':'任意文件.bin'}]})
        self.write();report=self.importer().import_file(self.source);self.assertEqual(report.success_count,6)
        c=self.controller();self.assertEqual(c.messages(1,2)['total'],2)
        self.assertEqual(c.messages(2,1)['total'],2)
        group=self.group(c);self.assertEqual((group['message_count'],group['own_count']),(4,1))
        tools=ArchiveTools(ArchiveScope(self.db,1,2));page=tools.archive_messages()
        self.assertEqual(page['total'],2);self.assertEqual(page['items'][1]['sender_name'],'来源身份未映射')
        self.assertEqual(tools.archive_message(page['items'][1]['id'])['item']['content'],page['items'][1]['content'])
        self.assertEqual(ArchiveTools(ArchiveScope(self.db,1)).archive_messages()['total'],2)

    def test_codex_group_reads_all_types_and_blocks_other_conversations(self):
        self.importer().import_file(self.source);c=self.controller();peer=self.group(c)['id']
        tools=ArchiveTools(ArchiveScope(self.db,1,peer))
        self.assertEqual(tools.execute('archive_overview',{})['messages'],3)
        page=tools.execute('archive_messages',{})
        self.assertEqual({x['msg_type'] for x in page['items']},{'text','image','file'})
        self.assertEqual(tools.execute('archive_contacts',{})['items'][0]['id'],peer)
        self.assertEqual({x['id'] for x in tools.execute('archive_users',{})['items']},{1,2,3})
        self.assertNotIn('relative_uri',json.dumps(page));self.assertNotIn(str(self.folder),json.dumps(page))
        reference=page['items'][1]['reference'];self.assertEqual(tools.resolve_reference(reference)['id'],page['items'][1]['id'])
        self.assertEqual(tools.archive_message(page['items'][1]['id'])['item']['attachments'][0]['kind'],'image')
        with self.assertRaises(NotFoundError):tools.archive_message(1)
        with self.assertRaises(ValidationError):tools.archive_messages(peer_id=2)
        private=ArchiveTools(ArchiveScope(self.db,1))
        self.assertEqual(private.archive_overview()['messages'],1)
        with self.assertRaises(ValidationError):private.archive_messages(peer_id=peer)

    def test_codex_group_membership_is_enforced_on_every_read(self):
        self.importer().import_file(self.source);c=self.controller();peer=self.group(c)['id']
        with self.assertRaises(NotFoundError):ArchiveTools(ArchiveScope(self.db,99,peer))
        tools=ArchiveTools(ArchiveScope(self.db,1,peer))
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('DELETE FROM chat_members WHERE chat_id=? AND user_id=1',(-peer,));conn.commit()
        with self.assertRaises(NotFoundError):tools.archive_messages()
        with self.assertRaises(NotFoundError):tools.archive_message(2)

    def test_import_copy_preserves_original_and_verified_assets(self):
        self.importer().import_file(self.source);before=sha_file(self.db);c=ApplicationController(self.folder/'new-profile')
        result=c.import_archive_copy(self.db)
        self.assertEqual(result['messages'],4);self.assertNotEqual(c.database,self.db)
        self.assertEqual(sha_file(self.db),before)
        self.assertEqual(sorted(x.name for x in media_root(c.database).rglob('*') if x.is_file()),['任意文件.bin','图片.png'])
        self.assertEqual(c.messages(1,self.group(c)['id'])['total'],3)

    def test_older_copy_is_imported_without_a_manual_upgrade(self):
        from wechat_archive.services import ChatService
        old=self.folder/'old.db';ChatService(old);before=sha_file(old)
        c=ApplicationController(self.folder/'new-profile');c.import_archive_copy(old)
        self.assertIsNotNone(c.rich_reader());self.assertEqual(sha_file(old),before)
        prior=c.database;c.ensure_extended_archive();self.assertEqual(c.database,prior)

    def test_group_prefix_display_is_verified_and_original_remains_available(self):
        row={'content':'wxid_synthetic:\n正文 😀','sender_wxid':'wechat:wxid_self:wxid_synthetic','chat_kind':'group','msg_type':'text'}
        self.assertEqual(present_content(row),'正文 😀');self.assertEqual(row['content'],'wxid_synthetic:\n正文 😀')
        row['sender_wxid']='wechat:wxid_self:wxid_other';self.assertEqual(present_content(row),row['content'])
        row['chat_kind']='private';self.assertEqual(present_content(row),row['content'])

    def test_group_rpc_retrieval_is_real_and_bound_to_scope(self):
        self.importer().import_file(self.source);c=self.controller();scope=ArchiveScope(self.db,1,self.group(c)['id'])
        events=[];trace=self.folder/'rpc.jsonl'
        client=CodexClient(self.folder/'rpc-profile',event_sink=events.append,timeout=5,command=[sys.executable,'-B','-X','utf8','-u',str(Path(__file__).parent/'fake_codex_server.py'),str(trace)])
        try:
            client.start();client.login();client.send('合成群聊读取检查',scope)
            deadline=time.monotonic()+8
            while client.active and time.monotonic()<deadline:time.sleep(.01)
            self.assertFalse(client.active)
            received=[json.loads(x) for x in trace.read_text(encoding='utf-8').splitlines()]
            reply=next(x['result'] for x in received if x.get('id')=='server-tool-1')
            self.assertTrue(reply['success']);payload=json.loads(reply['contentItems'][0]['text'])
            self.assertEqual(payload['total'],3);self.assertEqual(payload['scope']['peer_id'],scope.peer_id)
            self.assertTrue(any(x['kind']=='tool' and x['name']=='archive_messages' and x['success'] for x in events))
        finally:client.close()


class RequestedSourceTests(unittest.TestCase):
    setUp=source_fixture.RichSourceTests.setUp
    source=source_fixture.RichSourceTests.source
    capture=source_fixture.RichSourceTests.capture
    def test_zero_message_contacts_are_excluded_and_unmapped_records_retained(self):
        from wechat_archive.wechat_source.rich_source import contacts_with_groups
        db=self.source(count=4,shards=1);conn,table=db.tables[0]
        conn.execute(f'UPDATE "{table}" SET real_sender_id=99,message_content=? WHERE local_id=2',('synthetic_peer:\n恢复正文',))
        conn.execute(f'UPDATE "{table}" SET real_sender_id=99 WHERE local_id=3');conn.commit()
        conn.execute(f'UPDATE "{table}" SET real_sender_id=99,local_type=10000,message_content=? WHERE local_id=4',('合成系统通知',));conn.commit()
        rows=contacts_with_groups(db,[{'username':'empty_contact'},{'username':db.peer}])
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['unresolved_count'],1)
        capture=self.capture(db,all_history=True)
        from wechat_archive.importer.rich_importer import create_rich_archive
        from wechat_archive.importer.rich_snapshot import RichSnapshotImporter
        target=self.folder/'result.db';create_rich_archive(target)
        result=RichSnapshotImporter(target).import_snapshot(capture['output']);self.assertEqual((result.success_count,result.failed_count),(4,0))
        c=ApplicationController(self.folder/'profile');c.open_archive(target)
        group=next(x for x in c.contacts(1) if x['kind']=='group');messages=c.messages(1,group['id'])['items']
        unknown=next(x for x in messages if x['content'].startswith('[发送者未映射]'))
        self.assertEqual(unknown['sender_name'],'来源身份未映射');self.assertIn('原文 3',unknown['content'])
        self.assertEqual(next(x for x in messages if x['content']=='合成系统通知')['sender_name'],'系统')
        self.assertEqual(group['own_count'],1);self.assertAlmostEqual(group['own_ratio'],1/4)


class RequestedUITests(RichFixture):
    def test_main_entry_layout_and_direct_copy_action(self):
        self.importer().import_file(self.source);c=self.controller();root=tk.Tk();root.geometry('1240x840')
        errors=[];root.report_callback_exception=lambda *x:errors.append(x);app=ApplicationWindow(root,controller=c)
        try:
            app.owner_id=1;app.peer_id=self.group(c)['id'];app.load_contacts();root.update()
            self.assertTrue(app.copilot_button.winfo_ismapped());self.assertEqual(app.copilot_button.icon,'codex')
            self.assertFalse(app.ask_ai_button.winfo_ismapped());self.assertEqual(app.agent_panel.current_scope().peer_id,app.peer_id)
            app.agent_panel.ai_service.provider.capture(app.agent_panel.current_scope())
            self.assertEqual(int(app.contact_tree.canvas.cget('highlightthickness')),0)
            app.show_page('电脑微信');root.update()
            self.assertNotIn('标识',app.source_tree['columns']);self.assertFalse(app.source_cards.winfo_ismapped())
            self.assertEqual(str(app.source_upgrade_button.cget('state')),'normal')
            with patch('wechat_archive.ui.operation_actions.filedialog.askopenfilename',return_value=str(self.db)):
                app.source_upgrade_button.invoke()
            deadline=time.monotonic()+10
            while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
            root.update();self.assertNotEqual(c.database,self.db);self.assertEqual(c.overview()['messages'],4)
            self.assertEqual(errors,[])
        finally:app.close()
