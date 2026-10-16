"""Public regressions reproduce failure mechanisms without private data or live CDN."""
import hashlib,io,json,threading,time,tkinter as tk,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from test_sixu_v1 import RichFixture
from wechat_archive.wechat_source.emoji_fetch import checked_url,CdnRedirects,EmojiFetch
from wechat_archive.wechat_source.emoji_cache import EmojiCache
from wechat_archive.message_content import forwarded_records,forwarded_text
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ui.symbol_actions import symbolize
from wechat_archive.ui.thumbnail_service import ThumbnailService
from urllib.request import Request

class MediaRepairDataTests(RichFixture):
    def gif(self):
        data=io.BytesIO();frames=[Image.new('RGB',(24,20),color) for color in ('red','blue')];frames[0].save(data,format='GIF',save_all=True,append_images=frames[1:],duration=80,loop=0);return data.getvalue()
    def test_monthly_emoticon_cache_is_resolved_and_verified(self):
        data=self.gif();key=hashlib.md5(data).hexdigest();account=self.folder/'account';cache=account/'cache/2026-10/Emoticon';cache.mkdir(parents=True);(cache/key).write_bytes(data)
        result=EmojiCache(account).acquire({'message_content':'<msg><emoji md5="'+key+'"/></msg>'},self.folder/'out')
        self.assertEqual(result.read_bytes(),data)
    def test_cdn_policy_preserves_source_transport_and_rejects_unlisted_targets(self):
        self.assertEqual(checked_url('http://vweixinf.tc.qq.com/resource'),'http://vweixinf.tc.qq.com/resource')
        self.assertEqual(checked_url('https://emoji.qpic.cn/resource'),'https://emoji.qpic.cn/resource')
        for target in ('https://127.0.0.1/x','file:///x','https://emoji.qpic.cn.attacker.invalid/x','https://unit_user@emoji.qpic.cn/x','https://emoji.qpic.cn:9999/x'):
            with self.assertRaises(ValueError):checked_url(target)
        with self.assertRaises(ValueError):CdnRedirects().redirect_request(Request('https://emoji.qpic.cn/a'),None,302,'',{},'http://127.0.0.1/private')
    def test_cdn_download_requires_matching_digest_and_decodable_bytes(self):
        data=self.gif();key=hashlib.md5(data).hexdigest()
        class Response(io.BytesIO):headers={}
        fetch=EmojiFetch();fetch.opener=SimpleNamespace(open=lambda *a,**k:Response(data))
        result=fetch.acquire([{'md5':key,'cdnurl':'http://wxapp.tc.qq.com/resource'}],self.folder/'cdn')
        self.assertEqual(result.read_bytes(),data);self.assertEqual(fetch.last_status,'cdn_verified')
        bad=EmojiFetch();bad.opener=SimpleNamespace(open=lambda *a,**k:Response(data))
        self.assertIsNone(bad.acquire([{'md5':'0'*32,'cdnurl':'http://wxapp.tc.qq.com/resource'}],self.folder/'bad'))
        self.assertEqual(bad.last_status,'cdn_digest_mismatch');self.assertFalse((self.folder/'bad').exists())
    def test_offline_mode_does_not_fetch_declared_urls(self):
        account=self.folder/'account';account.mkdir()
        with patch('wechat_archive.wechat_source.emoji_fetch.EmojiFetch.acquire') as fetch:
            result=EmojiCache(account,allow_cdn=False).acquire({'message_content':'<msg><emoji md5="'+('a'*32)+'" cdnurl="https://emoji.qpic.cn/a"/></msg>'},self.folder/'out')
        self.assertIsNone(result);fetch.assert_not_called()
    def test_image_uses_packed_local_identity_before_cdn_plaintext_md5(self):
        from wechat_archive.wechat_source.acquisition import _load_sdk
        from wechat_archive.wechat_source.media_acquisition import local_media_reader,acquire_media
        _load_sdk();peer='synthetic_peer';packed='a'*32;xml='b'*32;account=self.folder/'account'
        image_dir=account/'msg/attach'/hashlib.md5(peer.encode()).hexdigest()/'2026-10/Img';image_dir.mkdir(parents=True);(image_dir/(packed+'.dat')).write_bytes(b'synthetic encrypted cache')
        class DB:
            account_dir=str(account)
            def get_message_row(self,*args,**kwargs):return {'local_type':3,'content':'<msg><img md5="'+xml+'"/></msg>','packed_info':b'\x12\x20'+packed.encode()}
        reader=local_media_reader(DB(),self.folder/'assets');data=io.BytesIO();Image.new('RGB',(30,20),'green').save(data,format='PNG')
        with patch.object(reader,'decrypt_image',return_value=data.getvalue()):result=acquire_media(reader,peer,{'local_type':3,'local_id':1,'shard':'message_0'},self.folder/'assets/one')
        self.assertEqual(result.read_bytes(),data.getvalue());self.assertEqual(len(reader._sixu_file_indexes),1)
    def test_forwarded_record_text_is_visible_without_changing_original_xml(self):
        body='<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist><dataitem datatype="1"><sourcename>合成伙伴</sourcename><datadesc>第一条原文</datadesc></dataitem><dataitem datatype="2"><sourcename>自己</sourcename></dataitem></datalist></recordinfo>]]></recorditem></appmsg></msg>'
        self.assertEqual(len(forwarded_records(body)),2);text=forwarded_text(body)
        self.assertIn('第一条原文',text);self.assertIn('[图片]',text);self.assertIn('<recorditem>',body)
        self.assertEqual(forwarded_records('<!DOCTYPE msg [<!ENTITY x "bad">]><msg/>'),[])

class MediaRepairUITests(RichFixture):
    def app(self):
        self.importer().import_file(self.source);root=tk.Tk();root.geometry('1080x760');app=ApplicationWindow(root,controller=self.controller());self.addCleanup(app.close);root.update();return app
    def test_hover_symbols_keep_names_and_do_not_add_duplicate_bindings(self):
        app=self.app();app.show_page('电脑微信');app.root.update();button=app.detect_button
        self.assertNotEqual(str(button.cget('compound')),'image');self.assertEqual(button.cget('text'),'检测账号')
        self.assertEqual(app.nav_note.cget('text'),'统计');self.assertEqual(app.nav_note.icon,'stats')
        self.assertFalse(hasattr(button,'_action_hint'))
        app.show_page('聊天归档');app.root.update();button=app.date_button
        binding=button.bind('<Enter>');hint=button._action_hint;symbolize(button,app.theme)
        self.assertEqual(button.bind('<Enter>'),binding);self.assertIs(button._action_hint,hint)
        hint.show();app.root.update();self.assertIsNotNone(hint.tip);hint.hide()
        from wechat_archive.ui.icon_button import IconButton
        for name in (*app.PAGE_NAMES,'电脑微信','导入文件'):
            app.show_page(name);app.root.update()
            icons=[x.icon for x in app.descendants(app.root) if isinstance(x,IconButton) and x.winfo_ismapped()]
            self.assertEqual(len(icons),len(set(icons)),(name,icons))
        self.assertNotEqual(str(app.acquire_button.cget('compound')),'image');self.assertNotEqual(str(app.source_upgrade_button.cget('compound')),'image')
    def test_background_work_keeps_navigation_and_locks_archive_mutations(self):
        app=self.app();release=threading.Event()
        app.run('正在只读获取微信…',lambda:release.wait(2),lambda _:None)
        try:
            self.assertNotEqual(str(app.nav_buttons['帮助'].cget('state')),'disabled');app.nav_buttons['帮助'].invoke();app.root.update();self.assertEqual(app.current_page,'帮助')
        finally:
            release.set();deadline=time.monotonic()+4
            while app.busy and time.monotonic()<deadline:app.root.update();time.sleep(.01)
            self.assertFalse(app.busy)
    def test_cached_green_page_does_not_walk_message_tree_again(self):
        app=self.app();app.theme.update(15,app.theme.family,'green','zh_CN',48);app.chat_text.reflow();app.root.update()
        changed=[{**row,'nickname':row['nickname']+' 更新'} for row in app.contact_rows];app.contact_tree.set_rows(changed,app.peer_id);app.root.update();self.assertTrue(app.contact_tree.cards)
        app.show_page('帮助');app.show_page('聊天归档');app.root.update()
        with patch.object(app.theme,'apply_tree',wraps=app.theme.apply_tree) as apply:
            for _ in range(3):app.show_page('帮助');app.show_page('聊天归档');app.root.update()
            self.assertFalse(any(x.args and x.args[0] is app.chat_text.body for x in apply.call_args_list))
    def test_thumbnail_decode_is_off_tk_thread(self):
        self.importer().import_file(self.source);controller=self.controller();row=controller.messages(1,self.group(controller)['id'])['items'][1];item=row['attachments'][0]
        root=tk.Tk();root.withdraw();app=SimpleNamespace(root=root,controller=controller,theme=SimpleNamespace(palette={'SECONDARY':'#555'},section=('Arial',12)))
        service=ThumbnailService(app);canvas=tk.Canvas(root,width=120,height=100);canvas.pack();entered=threading.Event();release=threading.Event()
        from wechat_archive.importer.rich_importer import ready_media
        def blocked(*args):entered.set();release.wait(3);return ready_media(*args)
        try:
            with patch('wechat_archive.importer.rich_importer.ready_media',side_effect=blocked):
                started=time.monotonic();service.submit(item,canvas,120,100);self.assertLess(time.monotonic()-started,.5);self.assertTrue(entered.wait(1));root.update();release.set()
                deadline=time.monotonic()+4
                while not hasattr(canvas,'image') and time.monotonic()<deadline:root.update();time.sleep(.01)
            self.assertTrue(hasattr(canvas,'image'))
        finally:release.set();service.close();root.destroy()

    def test_font_changes_preserve_selection_and_apply_latest_size_to_hidden_chat(self):
        app=self.app();text=next(iter(app.chat_text.bubbles.values()))['text'];text.tag_add('sel','1.0','1.2')
        original=text.get('1.0','end-1c');app.show_page('归档与界面');app.root.update();images=tuple(map(str,app.theme.images))
        with patch.object(app.agent_panel,'_render',wraps=app.agent_panel._render) as render:
            for size in (18,20):app.text_size.set(size);app.apply_user_settings();app.root.update()
            render.assert_not_called()
        self.assertEqual(tuple(map(str,app.theme.images)),images)
        self.assertTrue(hasattr(app.pages['聊天归档'],'_pending_theme'))
        app.show_page('聊天归档');app.root.update()
        self.assertEqual(text.get('1.0','end-1c'),original);self.assertTrue(text.tag_ranges('sel'))
        self.assertEqual(int(app.root.tk.splitlist(text.cget('font'))[1]),app.theme.body[1])
        self.assertFalse(hasattr(app.pages['聊天归档'],'_pending_theme'))
    def test_wheel_or_unchanged_preferences_do_not_repaint_theme(self):
        app=self.app();generation=app.theme.generation;images=tuple(map(str,app.theme.images))
        with patch.object(app.theme,'configure_styles',wraps=app.theme.configure_styles) as styles,patch.object(app.theme,'apply_tree',wraps=app.theme.apply_tree) as paint:
            app.theme.update(app.theme.text_size,app.theme.family,app.theme.mode,app.theme.language,96)
            styles.assert_not_called();paint.assert_not_called()
        self.assertEqual(app.theme.generation,generation);self.assertEqual(tuple(map(str,app.theme.images)),images)
        self.assertEqual(app.theme.wheel_router.pixels,app.theme.u(96))
    def test_repeated_apply_coalesces_latest_preferences_and_close_cancels_pending(self):
        app=self.app();app.show_page('归档与界面');app.root.update()
        with patch.object(app,'apply_user_settings',wraps=app.apply_user_settings) as apply:
            for size in (18,19,20):app.text_size.set(size);app.request_user_settings()
            deadline=time.monotonic()+3
            while getattr(app,'settings_apply_job',None) and time.monotonic()<deadline:app.root.update();time.sleep(.01)
            self.assertEqual(apply.call_count,1);self.assertEqual(app.ui_settings['text_size'],20)
        app.text_size.set(21);app.request_user_settings();self.assertIsNotNone(app.settings_apply_job);app.close();self.assertIsNone(app.settings_apply_job)
