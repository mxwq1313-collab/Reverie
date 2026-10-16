"""Verified WeChat account captions keep exact native account bindings."""
from pathlib import Path
import sqlite3,tempfile,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_workbench as fixture
from wechat_archive.ui.account_labels import account_labels
from wechat_archive.wechat_source.live_source import discover_accounts,open_account,self_alias
from wechat_archive.errors import ArchiveError

class AccountMetadataTests(unittest.TestCase):
    def test_accounts_are_enriched_from_their_own_contact_identity_only(self):
        sdk=SimpleNamespace(list_accounts=lambda root:[{'account':'unit_a_dir','wxid':'unit_a'},{'account':'unit_b_dir','wxid':'unit_b'}])
        owners=[(SimpleNamespace(),{'nick_name':'甲'}),(SimpleNamespace(),{'nick_name':'乙'})]
        with tempfile.TemporaryDirectory() as folder,patch('wechat_archive.wechat_source.live_source._load_sdk',return_value=sdk),patch('wechat_archive.wechat_source.live_source._client_version',return_value='unit'),patch('wechat_archive.wechat_source.live_source.open_account',side_effect=owners) as opened,patch('wechat_archive.wechat_source.live_source.self_alias',side_effect=['account_one','account_two']):
            result=discover_accounts(folder,Path(folder)/'unit-work')
        self.assertEqual([x['nickname'] for x in result['accounts']],['甲','乙']);self.assertEqual([x['weixin_id'] for x in result['accounts']],['account_one','account_two'])
        self.assertEqual([x.args[1] for x in opened.call_args_list],['unit_a_dir','unit_b_dir']);self.assertTrue(all(x.kwargs=={'contact_only':True} for x in opened.call_args_list))
    def test_unavailable_account_is_not_given_another_accounts_name(self):
        sdk=SimpleNamespace(list_accounts=lambda root:[{'account':'unit_a','wxid':'unit_a'}])
        with tempfile.TemporaryDirectory() as folder,patch('wechat_archive.wechat_source.live_source._load_sdk',return_value=sdk),patch('wechat_archive.wechat_source.live_source._client_version',return_value='unit'),patch('wechat_archive.wechat_source.live_source.open_account',side_effect=ArchiveError('unit unavailable')):
            row=discover_accounts(folder,Path(folder)/'unit-work')['accounts'][0]
        self.assertEqual(row['identity_status'],'login_required');self.assertEqual(row['nickname'],'');self.assertIn('待登录核验',account_labels([row])[0])
    def test_contact_only_mode_does_not_collect_message_databases(self):
        class Native:
            def __init__(self,**kwargs):
                self._db_files=self._collect_db_files();self._keys={x[0]:b'unit' for x in self._db_files};self.wxid='unit_owner'
            def _collect_db_files(self):return [('contact/contact.db','contact.db',0),('message/message_0.db','message_0.db',0)]
            def get_self_info(self):return {'username':self.wxid,'nick_name':'自己的昵称'}
        sdk=SimpleNamespace(list_accounts=lambda root:[{'account':'unit_dir'}],WeChatDB=Native)
        with tempfile.TemporaryDirectory() as folder,patch('wechat_archive.wechat_source.live_source._load_sdk',return_value=sdk):
            db,owner=open_account(folder,'unit_dir',Path(folder).parent/'unit-work',contact_only=True)
        self.assertEqual([x[0] for x in db._db_files],['contact/contact.db']);self.assertFalse(db._try_other_accounts());self.assertEqual(owner['nick_name'],'自己的昵称')
    def test_wechat_id_is_looked_up_by_exact_self_username(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'contact.db'
            with sqlite3.connect(path) as c:c.execute('CREATE TABLE contact(username TEXT,alias TEXT)');c.executemany('INSERT INTO contact VALUES (?,?)',[('other','someone_else'),('unit_self','my_wechat_account')])
            c.close()
            def connect(rel):
                c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
            db=SimpleNamespace(_db_files=[('contact/contact.db',str(path),0)],wxid='unit_self',_open=connect)
            self.assertEqual(self_alias(db),'my_wechat_account')
    def test_duplicate_nicknames_remain_distinguishable(self):
        rows=[{'nickname':'同名','weixin_id':'one','account':'a','wxid':'unit_a'},{'nickname':'同名','weixin_id':'two','account':'b','wxid':'unit_b'}]
        self.assertEqual(account_labels(rows),['同名 · 微信号：one','同名 · 微信号：two'])

class AccountCaptionUITests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def wait(self):
        stop=time.monotonic()+5
        while self.app.busy and time.monotonic()<stop:self.root.update();time.sleep(.005)
        self.root.update();self.assertFalse(self.app.busy);self.assertEqual(self.errors,[])
    def test_detected_names_and_wechat_ids_select_the_exact_native_account(self):
        app=self.app
        app.controller.source_runner=lambda *args,**kwargs:{'root':str(self.folder),'client_version':'unit','accounts':[{'account':'native_a_dir','wxid':'unit_a','nickname':'甲','weixin_id':'wechat_one'},{'account':'native_b_dir','wxid':'unit_b','nickname':'乙','weixin_id':'wechat_two'}]}
        app.detect_source();self.wait();self.assertEqual(tuple(app.account_box.cget('values')),('甲 · 微信号：wechat_one','乙 · 微信号：wechat_two'))
        app.account_box.current(1);app.source_account_changed();self.assertEqual(app.account_selection(),(str(self.folder),'native_b_dir'));self.assertEqual(self.errors,[])
    def test_unconnected_account_can_use_only_exact_archived_self_identity(self):
        self.service.update_user(1,wxid='wechat:unit_a:unit_a',nickname='自己的归档昵称')
        self.service.update_user(2,wxid='wechat:unit_a:unit_b',nickname='对方不能当作账号本人')
        self.app.controller.source_runner=lambda *args,**kwargs:{'root':str(self.folder),'client_version':'unit','accounts':[{'account':'native_a','wxid':'unit_a'},{'account':'native_b','wxid':'unit_b'}]}
        result=self.app.controller.discover(str(self.folder));labels=account_labels(result['accounts'])
        self.assertEqual(labels[0],'自己的归档昵称 · 归档昵称');self.assertIn('待登录核验',labels[1]);self.assertNotIn('nickname',result['accounts'][1])
    def test_live_verified_name_takes_priority_over_archive_label(self):
        self.service.update_user(1,wxid='wechat:unit_a:unit_a',nickname='旧归档昵称')
        self.app.controller.source_runner=lambda *args,**kwargs:{'accounts':[{'account':'native_a','wxid':'unit_a','nickname':'当前微信昵称','weixin_id':'current_account','identity_status':'verified'}]}
        row=self.app.controller.discover()['accounts'][0]
        self.assertEqual(row['nickname'],'当前微信昵称');self.assertEqual(row['identity_status'],'verified');self.assertNotIn('归档',account_labels([row])[0])
    def test_connecting_updates_only_the_selected_verified_account_caption(self):
        app=self.app;app.accounts=[{'account':'native_a','wxid':'unit_a'},{'account':'native_b','wxid':'unit_b'}];app.update_account_labels();app.account_box.current(1)
        app.controller.source_runner=lambda *args,**kwargs:{'owner':{'wxid':'unit_b','nickname':'真实对应昵称','weixin_id':'my_wechat'},'contacts':[]}
        app.load_source_contacts();self.wait();self.assertEqual(app.account_box.get(),'真实对应昵称 · 微信号：my_wechat');self.assertEqual(app.account_selection()[1],'native_b');self.assertNotIn('nickname',app.accounts[0])

if __name__=='__main__':unittest.main(verbosity=2)
