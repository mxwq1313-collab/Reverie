"""Synthetic 2.1.1 acceptance: offline avatars, independent tools and supplied logo."""
from contextlib import closing
import hashlib,json,sqlite3,time,tkinter as tk
from pathlib import Path
import tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import test_workbench as fixture
from wechat_archive.services.avatar_cache import AvatarCache,targets,user_identity,checked_image
from wechat_archive.wechat_source.avatar_source import read_avatars
from wechat_archive.errors import ValidationError,ArchiveError


class AvatarTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        self.database=self.folder/'head_image.db'
        with closing(sqlite3.connect(self.database)) as conn:
            conn.execute('CREATE TABLE head_image(username TEXT,md5 TEXT,image_buffer BLOB,update_time INTEGER)')
            path=self.folder/'avatar.png';Image.new('RGB',(120,80),'#57a38b').save(path)
            self.data=path.read_bytes();conn.executemany('INSERT INTO head_image VALUES (?,?,?,?)',[('unit_peer','unused',self.data,1),('unit_bad','unused',b'not an image',1)]);conn.commit()
        def connection(rel):
            conn=sqlite3.connect(self.database);conn.row_factory=sqlite3.Row;return conn
        self.db=SimpleNamespace(_db_files=[('head_image/head_image.db',str(self.database),1)],_open=connection,wxid='unit_self')
    def test_registered_cache_projects_only_selected_identities(self):
        result=read_avatars(self.db,['unit_peer','unit_bad','unit_missing'],self.folder/'job')
        self.assertTrue(result['offline']);self.assertEqual(result['missing'],2);self.assertEqual([x['username'] for x in result['images']],['unit_peer'])
        path=Path(result['images'][0]['path']);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),result['images'][0]['sha256'])
        with Image.open(path) as image:self.assertEqual(image.size,(128,128))
    def test_unknown_schema_is_refused(self):
        with closing(sqlite3.connect(self.database)) as conn:conn.execute('ALTER TABLE head_image RENAME COLUMN image_buffer TO unknown');conn.commit()
        with self.assertRaises(ArchiveError):read_avatars(self.db,['unit_peer'],self.folder/'job')
    def test_cache_mapping_and_missing_revocation(self):
        result=read_avatars(self.db,['unit_peer'],self.folder/'job');cache=AvatarCache(self.folder/'profile');mapping={'wechat:unit_self:unit_peer':'unit_peer'}
        saved=cache.store(mapping,result['images'],self.folder/'job');self.assertEqual(saved['ready'],1)
        decorated=cache.decorate([{'wxid':next(iter(mapping)),'nickname':'伙伴','avatar':None}]);self.assertTrue(Path(decorated[0]['avatar']).is_file())
        cache.store(mapping,[],self.folder/'job');self.assertIsNone(cache.decorate([{'wxid':next(iter(mapping)),'avatar':None}])[0]['avatar'])
    def test_cache_rejects_digest_changes_and_outside_files(self):
        result=read_avatars(self.db,['unit_peer'],self.folder/'job');cache=AvatarCache(self.folder/'profile');mapping={'wechat:unit_self:unit_peer':'unit_peer'}
        result['images'][0]['sha256']='0'*64
        with self.assertRaises(ValidationError):cache.store(mapping,result['images'],self.folder/'job')
        result['images'][0]['path']=str(self.folder/'avatar.png')
        with self.assertRaises(ValidationError):cache.store(mapping,result['images'],self.folder/'job')
    def test_identity_and_image_validation(self):
        self.assertEqual(user_identity('wechat:unit_self:unit_peer'),('unit_self','unit_peer'));self.assertIsNone(user_identity('unit_peer'))
        with self.assertRaises(ValidationError):checked_image(b'')
        with self.assertRaises(ValidationError):read_avatars(self.db,['x']*1001,self.folder/'job')
    def test_exact_user_and_group_namespace_binding(self):
        from wechat_archive.importer.rich_importer import RichImporter,create_rich_archive
        from wechat_archive.ui.application_controller import ReadOnlyArchive
        archive=self.folder/'archive.db';create_rich_archive(archive);namespace='wechat:unit_self';group='unit_room@chatroom'
        payload={'format':'sixu-chat-exchange','format_version':'2.0','namespace':namespace,'users':[{'id':'unit_self','nickname':'我'},{'id':'unit_peer','nickname':'伙伴'}],
                 'chats':[{'id':group,'kind':'group','members':['unit_self','unit_peer']}],
                 'messages':[{'id':json.dumps(['message_0','local','1']),'chat_id':group,'sender_id':'unit_peer','kind':'text','content':'自建群消息','create_time':'2026-10-16T00:00:00Z'}]}
        source=self.folder/'source.json';source.write_text(json.dumps(payload),encoding='utf-8');RichImporter(archive).import_file(source)
        native,mapping=targets(ReadOnlyArchive(archive),1)
        self.assertEqual(native,'unit_self');self.assertIn(group,mapping.values())
        self.assertIn('group:'+hashlib.sha256((namespace+'\0'+group).encode()).hexdigest(),mapping)
        with self.assertRaises(ValidationError):targets(ReadOnlyArchive(archive),2)


class Release210UI(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def settle(self):
        deadline=time.monotonic()+7
        while self.app.busy and time.monotonic()<deadline:self.root.update();time.sleep(.005)
        self.root.update();self.assertFalse(self.app.busy);self.assertEqual(self.errors,[])
    def test_each_tool_has_an_independent_page_and_back(self):
        self.show();box=self.app.toolbox_panel
        for name in ('时光胶囊','文字小工坊'):
            box.open_tool(name);self.root.update();self.assertFalse(hasattr(box,'home'))
            self.assertEqual([key for key,view in box.views.items() if view.winfo_ismapped()],[name])
        self.app.show_page('随机回忆');self.root.update();self.assertTrue(self.app.memory_popup.window.winfo_viewable())
        self.assertNotIn('随机回忆',self.app.tab_routes)
        self.app.show_page('数据管理');self.root.update();self.assertFalse(any(view.winfo_ismapped() for view in box.views.values()))
    def test_capsule_pagination_filters_and_readonly_save(self):
        fixture.WorkbenchTests.add_bulk(self);box=self.app.toolbox_panel;tool=box.capsule;before=self.path.read_bytes()
        tool.start.set('2026-10-10');tool.end.set('2026-10-16');box.read('date');self.settle()
        first={r['id'] for r in tool.items};self.assertEqual(len(first),100);tool.search(100);self.settle();self.assertEqual(len(tool.items),15);self.assertTrue(first.isdisjoint(r['id'] for r in tool.items))
        saved=self.folder/'memory.txt'
        with patch('wechat_archive.ui.toolbox_panel.filedialog.asksaveasfilename',return_value=str(saved)):tool.save(page=True)
        self.assertEqual(saved.read_text(encoding='utf-8').count('[消息 #'),15)
        tool.keyword.set('记录 110');tool.search(100);self.settle();self.assertEqual(tool.total,1);self.assertEqual(tool.offset,0);self.assertEqual(self.path.read_bytes(),before)
    def test_random_avoids_repeats_and_can_revisit(self):
        box=self.app.toolbox_panel;tool=box.random
        with patch('wechat_archive.ui.toolbox_panel.random.randrange',return_value=0):
            for _ in range(4):box.read('random');self.settle()
        self.assertEqual(len({r['id'] for r in tool.history}),4);latest=tool.row['id'];tool.visit(-1);self.assertNotEqual(tool.row['id'],latest);tool.visit(1);self.assertEqual(tool.row['id'],latest)
        self.app.peer_id=3;tool.copy();self.assertIn('当前范围',self.app.status.get())
    def test_random_exhaustion_keeps_last_memory_and_explains_reset(self):
        box=self.app.toolbox_panel;tool=box.random;tool.keyword.set('论文修改')
        box.read('random');self.settle();first=tool.row['id']
        box.read('random');self.settle();self.assertEqual(tool.row['id'],first);self.assertIn('全部打捞',self.app.status.get())
        tool.clear_history();self.assertIsNone(tool.row);box.read('random');self.settle();self.assertEqual(tool.row['id'],first)

    def test_text_workshop_replace_undo_and_utf8_files(self):
        box=self.app.toolbox_panel;workshop=box.workshop;before=self.path.read_bytes();workshop.set_text('你好 hello  \n\n\nHELLO \\text')
        workshop.find.set('hello');workshop.replacement.set('world\\value');workshop.ignore_case.set(True);workshop.replace(True)
        self.assertIn('2 处',self.app.status.get());self.assertEqual(workshop.text.get('1.0','end-1c').count('world\\value'),2)
        workshop.undo(False);self.assertIn('HELLO',workshop.text.get('1.0','end-1c'));workshop.transform('blank');self.assertNotIn('\n\n\n',workshop.text.get('1.0','end-1c'))
        saved=self.folder/'notes.txt'
        with patch('wechat_archive.ui.toolbox_panel.filedialog.asksaveasfilename',return_value=str(saved)):workshop.save()
        workshop.transform('clear')
        with patch('wechat_archive.ui.toolbox_panel.filedialog.askopenfilename',return_value=str(saved)):workshop.load()
        self.assertEqual(saved.read_text(encoding='utf-8'),workshop.text.get('1.0','end-1c'));self.assertEqual(self.path.read_bytes(),before)
    def test_cards_remove_recent_message_and_show_local_avatar(self):
        image=self.folder/'picture.png';Image.new('RGB',(80,80),'#57a38b').save(image);self.service.update_user(2,avatar=str(image));self.app.load_contacts()
        card,name,preview,stamp,count=self.app.contact_tree.cards['2'];self.assertEqual(preview.cget('text'),'');self.assertFalse(preview.winfo_manager())
        canvas=next(w for w in card.content.winfo_children() if isinstance(w,tk.Canvas));self.assertTrue(canvas.avatar_available);self.assertTrue(hasattr(canvas,'avatar_image'))
        self.assertNotIn('本人 8 条',count.cget('text'))
    def test_logo_and_release_version_are_packaged_assets(self):
        from wechat_archive import __version__
        from wechat_archive.ui.app_logo import original,windows_icon
        self.assertEqual(__version__,'2.2.1');self.assertTrue(original().startswith(b'\x89PNG'))
        icon=self.folder/'app.ico';windows_icon(icon)
        with Image.open(icon) as image:self.assertIn((256,256),image.info['sizes'])
        self.assertEqual(self.app.window_logo.width(),64);self.assertTrue(self.app.brand_label.cget('image'))


if __name__=='__main__':unittest.main(verbosity=2)
