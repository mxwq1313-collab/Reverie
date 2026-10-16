"""Legacy missing stickers recover without message edits; all downloads are mocked."""
import hashlib,io,json,sqlite3,threading,time,tkinter as tk,unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError
from PIL import Image
from test_sixu_v1 import RichFixture
from wechat_archive.wechat_source.emoji_fetch import EmojiFetch
from wechat_archive.services.emoji_repair import repair_emojis
from wechat_archive.ui.thumbnail_service import thumbnail_picture
from wechat_archive.ui.application_window import ApplicationWindow


class StickerV2Tests(RichFixture):
    def prepare(self):
        data=io.BytesIO();Image.new('RGB',(28,24),'green').save(data,format='GIF');data=data.getvalue();key=hashlib.md5(data).hexdigest()
        xml='<msg><emoji md5="'+key+'" cdnurl="https://emoji.qpic.cn/synthetic-resource"/></msg>'
        for row in self.payload['messages']:
            if row['kind']=='emoji':row.update(content=xml,attachments=[{'kind':'image','path':None,'name':'synthetic missing sticker'}])
        self.write();self.importer().import_file(self.source)
        class Response(io.BytesIO):headers={}
        return data,Response
    def test_old_missing_attachment_repaired_once_and_messages_unchanged(self):
        data,Response=self.prepare()
        with closing(sqlite3.connect(self.db)) as db:before=list(db.execute('SELECT * FROM messages ORDER BY id'))
        with patch('wechat_archive.wechat_source.emoji_fetch.build_opener',return_value=SimpleNamespace(open=lambda *a,**k:Response(data))):result=repair_emojis(self.db,allow_cdn=True)
        self.assertEqual((result['repaired'],result['missing']),(1,0))
        with closing(sqlite3.connect(self.db)) as db:self.assertEqual(list(db.execute('SELECT * FROM messages ORDER BY id')),before)
        with patch('wechat_archive.wechat_source.emoji_fetch.EmojiFetch.acquire') as network:
            repeat=repair_emojis(self.db,allow_cdn=True);self.assertEqual(repeat['ready'],1);network.assert_not_called()
        self.assertEqual(self.importer().import_file(self.source).duplicated_count,4)

    def test_offline_and_cancel_never_download_or_rewrite_messages(self):
        self.prepare();before=self.db.read_bytes();cancel=threading.Event();cancel.set()
        with patch('wechat_archive.wechat_source.emoji_fetch.EmojiFetch.acquire') as network:
            offline=repair_emojis(self.db);stopped=repair_emojis(self.db,allow_cdn=True,cancel_event=cancel);network.assert_not_called()
        self.assertEqual(offline['missing'],1);self.assertTrue(stopped['cancelled']);self.assertEqual(self.db.read_bytes(),before)

    def test_download_allowance_is_per_resource_not_first_50_or_first_90_seconds(self):
        data,Response=self.prepare();fetch=EmojiFetch();fetch.attempts=80;fetch.started=time.monotonic()-300
        fetch.opener=SimpleNamespace(open=lambda *a,**k:Response(data));key=hashlib.md5(data).hexdigest()
        self.assertIsNotNone(fetch.acquire([{'md5':key,'cdnurl':'https://emoji.qpic.cn/synthetic-new-resource'}],self.folder/'download'))
        self.assertEqual(fetch.last_status,'cdn_verified')

    def test_repeated_failed_resource_does_not_repeat_network_requests(self):
        fetch=EmojiFetch();open_mock=unittest.mock.Mock(side_effect=URLError('synthetic offline'));fetch.opener=SimpleNamespace(open=open_mock)
        record={'md5':'0'*32,'cdnurl':'https://emoji.qpic.cn/synthetic-unavailable'}
        for _ in range(100):self.assertIsNone(fetch.acquire([record],self.folder/'download'))
        self.assertEqual(open_mock.call_count,1);self.assertEqual(fetch.last_status,'cdn_connection_failed')
        from wechat_archive.wechat_source.emoji_cache import EmojiCache
        data=io.BytesIO();Image.new('RGB',(28,24),'blue').save(data,format='PNG');data=data.getvalue();key=hashlib.md5(data).hexdigest();account=self.folder/'account';(account/'emoji').mkdir(parents=True);(account/'emoji'/key).write_bytes(data)
        cache=EmojiCache(account);row={'message_content':'<msg><emoji md5="'+key+'"/></msg>'};first=cache.acquire(row,self.folder/'one');first.write_bytes(b'changed cached output')
        self.assertEqual(cache.acquire(row,self.folder/'two').read_bytes(),data)

    def test_transparent_gif_first_frame_uses_visible_poster(self):
        path=self.folder/'blank-first.gif';frames=[Image.new('P',(24,20),index) for index in (0,1)]
        for frame in frames:frame.putpalette([0,0,0,10,180,40]+[0]*762)
        frames[0].save(path,save_all=True,append_images=frames[1:],duration=100,disposal=2,transparency=0,optimize=False)
        with Image.open(path) as image:poster=thumbnail_picture(image,100,100)
        self.assertIsNotNone(poster.getchannel('A').getbbox())

    def test_repair_entry_default_full_range_and_restored_sticker_is_displayed(self):
        data,Response=self.prepare();controller=self.controller();root=tk.Tk();root.geometry('1100x760');root.attributes('-alpha',0);app=ApplicationWindow(root,controller=controller);self.addCleanup(app.close);root.update()
        self.assertEqual(app.source_scope.get(),'全部电脑本地记录');app.show_page('电脑微信');app.source_advanced.set_expanded(True);root.update();self.assertTrue(app.repair_emoji_button.winfo_ismapped())
        with patch('wechat_archive.wechat_source.emoji_fetch.build_opener',return_value=SimpleNamespace(open=lambda *a,**k:Response(data))):
            app.repair_emoji_button.invoke();deadline=time.monotonic()+5
            while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        self.assertFalse(app.busy);app.show_page('聊天归档');app.owner_id=1;app.peer_id=self.group(controller)['id'];app.load_contacts();root.update()
        deadline=time.monotonic()+5
        while not any(hasattr(canvas,'image') for _,canvas in app.chat_text.thumbnails) and time.monotonic()<deadline:root.update();time.sleep(.01)
        self.assertTrue(any(hasattr(canvas,'image') for _,canvas in app.chat_text.thumbnails))
