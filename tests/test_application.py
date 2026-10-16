import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from wechat_archive import ChatService,ConflictError,ValidationError
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.wechat_source.live_source import extract_records,source_stamp,read_contacts
from wechat_archive.errors import ArchiveError

ROOT=Path(__file__).resolve().parents[1]


class ApplicationControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        self.controller=ApplicationController(self.folder/'profile');self.database=self.folder/'archive.db';self.controller.new_archive(self.database)

    def import_sample(self):return self.controller.import_file(ROOT/'examples/chat_sample.json')

    def test_new_archive_never_overwrites(self):
        before=self.database.read_bytes()
        with self.assertRaises(ConflictError):self.controller.new_archive(self.database)
        self.assertEqual(self.database.read_bytes(),before)

    def test_last_archive_restored_without_writing_database(self):
        self.import_sample();before=hashlib.sha256(self.database.read_bytes()).hexdigest()
        other=ApplicationController(self.folder/'profile');other.restore_archive()
        self.assertEqual(other.database,self.database);self.assertEqual(other.overview()['messages'],3)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(),before)

    def test_import_repeat_report_and_native_search(self):
        first=self.import_sample();second=self.import_sample()
        self.assertEqual((first.success_count,second.duplicated_count),(3,3))
        users=self.controller.users();messages=self.controller.messages(users[0]['id'])
        self.assertEqual(messages['total'],3);word=messages['items'][0]['content']
        self.assertGreater(self.controller.messages(users[0]['id'],keyword=word)['total'],0)
        paths=self.controller.report_files();self.assertEqual(len(paths),2)
        self.assertEqual(self.controller.read_report(paths[0])['duplicated_count'],3)

    def test_invalid_date_is_clear(self):
        self.import_sample()
        with self.assertRaises(ValidationError):self.controller.messages(1,start='bad')

    def test_readonly_browser_leaves_source_bytes_equal(self):
        self.import_sample();before=self.database.read_bytes()
        self.controller.users();self.controller.contacts(1);self.controller.messages(1,2)
        self.assertEqual(self.database.read_bytes(),before)

    def test_contact_and_message_crud_reuses_core(self):
        a=self.controller.manage_user('create',wxid='unit_a',nickname='甲');b=self.controller.manage_user('create',wxid='unit_b',nickname='乙')
        self.controller.manage_user('update',a.id,nickname='新昵称')
        message=self.controller.manage_message('create',sender_id=a.id,receiver_id=b.id,content='unit text',create_time='2026-01-01T00:00:00Z')
        with self.assertRaises(ConflictError):self.controller.manage_user('delete',a.id)
        self.controller.manage_message('update',message.id,content='edited')
        self.assertEqual(self.controller.messages(a.id,b.id)['items'][0]['content'],'edited')
        self.controller.manage_message('delete',message.id);self.controller.manage_user('delete',a.id)
        self.assertEqual(self.controller.overview(),{'database':str(self.database),'users':1,'messages':0})

    def test_selected_export_has_all_messages_and_source_unchanged(self):
        self.import_sample();before=self.database.read_bytes()
        result=self.controller.export(self.folder,1,2)
        self.assertEqual(result['messages'],3);self.assertTrue(Path(result['index']).is_file())
        self.assertEqual(self.database.read_bytes(),before)

    def test_cancelled_source_never_imports(self):
        def runner(*args,**kwargs):
            self.controller.cancel_event.set();return {'output':str(ROOT/'examples/chat_sample.json')}
        self.controller.source_runner=runner
        with self.assertRaises(ValidationError):self.controller.acquire_import('unit','unit','unit')
        self.assertEqual(self.controller.overview()['messages'],0)


class ApplicationWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        self.controller=ApplicationController(self.folder/'profile');self.database=self.folder/'archive.db';self.controller.new_archive(self.database)
        self.root=tk.Tk();self.root.withdraw();self.app=ApplicationWindow(self.root,controller=self.controller);self.addCleanup(self.app.close)

    def wait(self):
        limit=time.monotonic()+20
        while self.app.busy and time.monotonic()<limit:self.root.update();time.sleep(.01)
        self.assertFalse(self.app.busy);self.root.update()

    def test_all_pages_available_from_start(self):
        self.assertEqual(len(self.app.PAGE_NAMES),6);self.assertEqual(self.app.current_page,'聊天归档')
        for name in self.app.PAGE_NAMES:self.app.show_page(name);self.assertEqual(self.app.current_page,name)

    def test_import_buttons_render_records_inside_application(self):
        self.app.import_source.set(str(ROOT/'examples/chat_sample.json'))
        with patch('webbrowser.open') as browser,patch('wechat_archive.ui.application_window.messagebox.showerror') as error:
            self.app.import_button.invoke();self.wait();browser.assert_not_called();error.assert_not_called()
        self.assertEqual(len(self.app.message_rows),3)
        self.assertIn(self.app.message_rows[0]['content'],self.app.chat_text.get('1.0','end'))
        self.assertIn('新增消息：3',self.app.import_result.get('1.0','end'))

    def test_export_button_uses_selected_archive(self):
        self.controller.import_file(ROOT/'examples/chat_sample.json');self.app.refresh_archive();self.app.export_parent.set(str(self.folder))
        with patch('wechat_archive.ui.application_window.messagebox.showerror') as error:
            self.app.export_button.invoke();self.wait();error.assert_not_called()
        self.assertEqual(len(list(self.folder.glob('聊天导出_*/index.html'))),1)
        self.assertIn('消息：3',self.app.export_result.get('1.0','end'))

    def test_switch_to_empty_identity_clears_previous_message_selection(self):
        self.controller.import_file(ROOT/'examples/chat_sample.json');self.controller.manage_user('create',wxid='empty_unit',nickname='空身份');self.app.refresh_archive()
        self.app.owner_box.current(len(self.app.archive_users)-1);self.app.change_owner()
        self.assertEqual(self.app.message_rows,[]);self.assertEqual(self.app.message_tree.get_children(),())

    def test_source_buttons_keep_workflow_in_one_interface(self):
        from test_external_source import data
        payload=data()
        def runner(action,data_dir,**options):
            if action=='accounts':return {'root':str(self.folder),'accounts':[{'account':'unit_account','wxid':'wxid_unit_owner'}],'client_version':'unit_test'}
            if action=='contacts':return {'owner':{'wxid':'wxid_unit_owner','nickname':'测试自己'},'contacts':[{'username':'wxid_unit_peer','name':'测试对方','message_count':2}]}
            destination=Path(options['output']);destination.mkdir(parents=True)
            from wechat_archive.importer.rich_importer import sha_file
            owner,peer='wxid_unit_owner','wxid_unit_peer'
            exchange={'format':'sixu-chat-exchange','format_version':'2.0','namespace':'wechat:'+owner,
                      'users':[{'id':owner,'nickname':'测试自己'},{'id':peer,'nickname':'测试对方'}],
                      'chats':[{'id':peer,'kind':'private','members':[owner,peer]}],
                      'messages':[{'id':'synthetic-'+str(i),'chat_id':peer,'sender_id':owner,'receiver_id':peer,'create_time':'2026-01-01T00:00:00Z','kind':'text','content':'自建正文 '+str(i)} for i in range(2)]}
            batch=destination/'batch.json';batch.write_text(json.dumps(exchange,ensure_ascii=False),encoding='utf-8')
            raw=destination/'raw.jsonl';raw.write_text('{}\n{}\n',encoding='utf-8')
            manifest={'format':'sixu-source-snapshot','format_version':'1.0','records':2,'typed_records':2,'unresolved_senders':0,'attachments':0,'raw_file':raw.name,'raw_sha256':sha_file(raw),'batches':[{'file':batch.name,'records':2,'sha256':sha_file(batch)}]}
            (destination/'rich_snapshot.json').write_text(json.dumps(manifest),encoding='utf-8');return {'output':str(destination),'records':2}
        self.controller.source_runner=runner
        with patch('wechat_archive.ui.application_window.messagebox.showerror') as error:
            self.app.detect_source();self.wait();self.app.load_source_contacts();self.wait();self.app.source_tree.selection_set('0');self.app.acquire_button.invoke();self.wait();error.assert_not_called()
        self.assertEqual(self.controller.overview()['messages'],2);self.assertEqual(len(self.app.message_rows),2)
        self.assertIn('新增消息：2',self.app.source_result.get('1.0','end'))

    def test_account_change_invalidates_previous_contact_list(self):
        self.app.source_peers=[{'username':'unit','name':'unit'}];self.app.source_tree.insert('','end',iid='0',values=('unit','unit'))
        self.app.source_account_changed();self.assertEqual(self.app.source_peers,[]);self.assertEqual(self.app.source_tree.get_children(),())

    def test_preview_does_not_create_default_archive(self):
        profile=self.folder/'unused_profile';controller=ApplicationController(profile)
        self.app.controller=controller;self.app.import_source.set(str(ROOT/'examples/chat_sample.json'))
        with patch('wechat_archive.ui.application_window.messagebox.showerror') as error:
            self.app.import_action(True);self.wait();error.assert_not_called()
        self.assertFalse((profile/'chat.db').exists());self.assertIsNone(controller.database)


class FakeMessageDB:
    wxid='wxid_unit_owner'
    def __init__(self,count=3):
        self._db_files=[];self.items=[{'local_id':index+1,'shard':'message_0','sender_username':'wxid_unit_owner' if index%2==0 else 'wxid_unit_peer','create_time':1767225600+index,'content':f'unit row {index}','type':1} for index in range(count)]
    def get_messages(self,peer,limit=20,offset=0):return self.items[offset:offset+limit]
    def get_message_row(self,peer,local_id,shard=None):
        row=copy.deepcopy(self.items[local_id-1]);row.update(local_type=1,server_id=1000+local_id,sort_seq=local_id);return row


class LiveSourceContractTests(unittest.TestCase):
    def test_full_history_exceeds_small_window_without_offset_paging(self):
        rows=extract_records(FakeMessageDB(620),'wxid_unit_peer',all_history=True)
        self.assertEqual(len(rows),620);self.assertEqual(len({row['source_id_kind']+row['source_message_id'] for row in rows}),620)

    def test_recent_limit_respected(self):
        self.assertEqual(len(extract_records(FakeMessageDB(900),'wxid_unit_peer',limit=550)),550)

    def test_duplicate_page_identity_is_explicit_failure(self):
        db=FakeMessageDB(2);db.items[1]=copy.deepcopy(db.items[0])
        with self.assertRaises(ArchiveError):extract_records(db,'wxid_unit_peer')

    def test_group_and_invalid_limit_rejected(self):
        for peer in ('unit@chatroom','gh_unit','wxid_unit_owner'):
            with self.assertRaises(ArchiveError):extract_records(FakeMessageDB(),peer)
        with self.assertRaises(ValidationError):extract_records(FakeMessageDB(),'wxid_unit_peer',limit=True)

    def test_unrelated_session_file_change_does_not_invalidate_messages(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'session.db';path.write_bytes(b'unit session');db=FakeMessageDB();db._db_files=[('session',str(path),1)]
            original=db.get_messages
            def query(*args,**kwargs):path.write_bytes(b'changed unit session');return original(*args,**kwargs)
            db.get_messages=query;self.assertEqual(len(extract_records(db,'wxid_unit_peer')),3)

    def test_message_shard_change_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'message_0.db';path.write_bytes(b'unit');db=FakeMessageDB();db._db_files=[('message',str(path),1)]
            original=db.get_messages
            def query(*args,**kwargs):path.write_bytes(b'changed unit shard');return original(*args,**kwargs)
            db.get_messages=query
            with self.assertRaises(ArchiveError):extract_records(db,'wxid_unit_peer')

    def test_contact_schema_mapping_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'contact.db'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE contact(username TEXT,nick_name TEXT,remark TEXT)');connection.execute("INSERT INTO contact VALUES ('unit_peer','昵称','备注')")
            connection.close()
            class ContactDB:
                _db_files=[('contact',str(path),1)]
                def _open(self,rel):
                    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);connection.row_factory=sqlite3.Row;return connection
            self.assertEqual(read_contacts(ContactDB(),peer='unit_peer')[0]['remark'],'备注')
            self.assertEqual(read_contacts(ContactDB(),keyword='不存在'),[])

    def test_unknown_contact_schema_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'contact.db'
            with sqlite3.connect(path) as connection:connection.execute('CREATE TABLE contact(unknown TEXT)')
            connection.close()
            class ContactDB:
                _db_files=[('contact',str(path),1)]
                def _open(self,rel):
                    connection=sqlite3.connect(path);connection.row_factory=sqlite3.Row;return connection
            with self.assertRaises(ArchiveError):read_contacts(ContactDB())
