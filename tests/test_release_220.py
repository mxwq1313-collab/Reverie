"""2.2.0 end-to-end forwards, native media interactions and resize contracts."""
import hashlib,json,sqlite3,time,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from test_sixu_v1 import RichFixture
import test_rich_source as source_fixture
import test_release_211 as forward_fixture
from wechat_archive.services.forward_resources import LocalForwardImages,verified_picture,archived_forward_image
from wechat_archive.message_content import forwarded_document
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.importer.rich_importer import sha_file

def image_forward(file,thumb=None):
    data=file.read_bytes();digest=hashlib.md5(data).hexdigest()
    fields=f'<fullmd5>{digest}</fullmd5><datasize>{len(data)}</datasize>'
    if thumb:
        body=thumb.read_bytes();fields+=f'<thumbfullmd5>{hashlib.md5(body).hexdigest()}</thumbfullmd5><thumbsize>{len(body)}</thumbsize>'
    return '<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist><dataitem datatype="2" dataid="'+'a'*32+'"><sourcename>自建伙伴</sourcename><datadesc>[图片]</datadesc>'+fields+'</dataitem></datalist></recordinfo>]]></recorditem></appmsg></msg>'

class ForwardImageUITests(RichFixture):
    def setUp(self):
        super().setUp()
        frames=[Image.new('RGBA',(90,60),color) for color in ('red','blue','green')]
        self.gif=self.folder/'animation.gif';frames[0].save(self.gif,save_all=True,append_images=frames[1:],duration=70,loop=0)
        self.payload['messages'].append({'id':'forward-1','chat_id':'group','sender_id':'unit_peer','kind':'system','content':image_forward(self.gif),'create_time':'2026-10-15T00:04:00Z','attachments':[{'kind':'image','path':'animation.gif'}]})
        self.write();self.importer().import_file(self.source)
        self.c=self.controller();self.root=tk.Tk();self.root.withdraw();self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=ApplicationWindow(self.root,controller=self.c);self.addCleanup(self.app.close)
        self.root.geometry('1100x760');self.root.deiconify();self.app.owner_id=1;self.app.peer_id=self.group(self.c)['id'];self.app.load_contacts();self.root.update()
        self.row=next(r for r in self.c.messages(1,self.app.peer_id)['items'] if r['msg_type']=='system')
        self.app.chat_text.set_rows([self.row],1);self.root.update();self.control=self.app.chat_text.bubbles[self.row['id']]['forward']
    def settle(self,condition,timeout=5):
        stop=time.monotonic()+timeout
        while time.monotonic()<stop:
            self.root.update()
            if condition():return
            time.sleep(.005)
        self.fail('2.2 native media did not settle')
    def picture(self):
        self.control.toggle();self.settle(lambda:bool(self.app.chat_text.thumbnails) and hasattr(self.app.chat_text.thumbnails[-1][1],'image'))
        return self.app.chat_text.thumbnails[-1][1]
    def test_image_acquisition_import_display_gif_play_save_and_reread_dedup(self):
        before=sha_file(self.db);canvas=self.picture();self.assertGreater(canvas.image.width(),0)
        canvas.event_generate('<Button-1>');self.root.update()
        window=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and hasattr(w,'preview_state'))
        play=next(w for w in self.app.descendants(window) if w.winfo_class()=='TButton' and w.cget('text')=='播放 / 暂停')
        play.invoke();self.root.after(230,self.root.quit);self.root.mainloop();self.assertTrue(window.preview_state['playing'])
        save=self.folder/'saved.gif'
        with patch('wechat_archive.ui.media_widgets.filedialog.asksaveasfilename',return_value=str(save)):
            button=next(w for w in self.app.descendants(window) if w.winfo_class()=='TButton' and w.cget('text')=='另存图片');button.invoke()
        self.assertEqual(save.read_bytes(),self.gif.read_bytes());self.assertEqual(sha_file(self.db),before)
        self.root.tk.call(window.protocol('WM_DELETE_WINDOW'));self.root.update()
        report=self.importer().import_file(self.source);self.assertEqual(report.duplicated_count,5);self.assertEqual(report.success_count,0)
        self.assertEqual(self.errors,[])
    def test_collapse_reopen_destroys_old_canvas_and_reloads_cached_picture(self):
        canvas=self.picture();self.control.collapse();self.root.update();self.assertFalse(canvas.winfo_exists())
        again=self.picture();self.assertIsNot(again,canvas);self.assertLessEqual(len(self.app.chat_text.thumbnails),1);self.assertEqual(self.errors,[])
    def test_exact_digest_can_reuse_existing_archive_resource_without_parent_attachment(self):
        self.row={**self.row,'attachments':[]};self.app.chat_text.set_rows([self.row],1);self.root.update();self.control=self.app.chat_text.bubbles[self.row['id']]['forward']
        self.picture();self.assertEqual(self.errors,[])
    def test_missing_resources_have_explicit_status_and_no_wrong_image(self):
        self.row={**self.row,'content':self.row['content'].replace(hashlib.md5(self.gif.read_bytes()).hexdigest(),'f'*32)}
        self.app.chat_text.set_rows([self.row],1);self.root.update();self.control=self.app.chat_text.bubbles[self.row['id']]['forward'];self.control.toggle()
        self.settle(lambda:self.control.rendered and self.control.rendered[0][2] is not None and '图片未取得' in self.control.rendered[0][2].get('1.0','end-1c'))
        self.assertEqual(self.app.chat_text.thumbnails,[]);self.assertEqual(self.errors,[])
    def test_other_parent_attachments_remain_available_beside_the_forward(self):
        other=next(r for r in self.c.messages(1,self.app.peer_id)['items'] if r['msg_type']=='file')['attachments'][0]
        self.row={**self.row,'attachments':[*self.row['attachments'],other]}
        self.app.chat_text.set_rows([self.row],1);self.root.update()
        buttons=[w for w in self.app.descendants(self.app.chat_text) if getattr(w,'attachment_item',{}).get('kind')=='file']
        self.assertEqual(len(buttons),1);self.assertEqual(buttons[0].attachment_item['sha256'],other['sha256']);self.assertEqual(self.errors,[])
    def test_destroy_pending_lookup_is_safe(self):
        self.control.toggle();self.app.chat_text.clear();self.root.after(150,self.root.quit);self.root.mainloop();self.assertEqual(self.errors,[])

class ForwardAcquisitionTests(unittest.TestCase):
    setUp=source_fixture.RichSourceTests.setUp
    source=source_fixture.RichSourceTests.source
    capture=source_fixture.RichSourceTests.capture
    def test_forward_resource_capture_import_display_binding_and_repeat(self):
        source=self.source(count=1,shards=1);cache=Path(source.account_dir)/'cache/2026-10/Record';cache.mkdir(parents=True)
        file=cache/('a'*32+'.dat');Image.new('RGB',(40,30),'#57a080').save(file,format='PNG')
        xml=image_forward(file);conn,table=source.tables[0];conn.execute(f'UPDATE "{table}" SET local_type=49,message_content=?',(xml,));conn.commit()
        result=self.capture(source);self.assertEqual((result['media_available'],result['media_missing']),(1,0))
        from wechat_archive.importer.rich_importer import create_rich_archive
        from wechat_archive.importer.rich_snapshot import RichSnapshotImporter
        target=self.folder/'forward.db';create_rich_archive(target);importer=RichSnapshotImporter(target)
        first=importer.import_snapshot(result['output']);second=importer.import_snapshot(result['output']);self.assertEqual((first.success_count,second.duplicated_count),(1,1))
        with sqlite3.connect(target) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM message_media').fetchone()[0],1)
    def test_digest_size_and_actual_format_are_all_checked(self):
        data=b'not an image';spec={'md5':hashlib.md5(data).hexdigest(),'size':len(data)};self.assertIsNone(verified_picture(data,spec))
        file=self.folder/'picture.png';Image.new('RGB',(30,20)).save(file);media=forwarded_document(image_forward(file))['items'][0]['media']
        self.assertIsNotNone(verified_picture(file.read_bytes(),media['images'][0]));media['images'][0]['size']+=1;self.assertIsNone(verified_picture(file.read_bytes(),media['images'][0]))

class Release220NavigationTests(unittest.TestCase):
    setUp=forward_fixture.Release211UITests.setUp
    show=forward_fixture.Release211UITests.show
    settle=forward_fixture.Release211UITests.settle
    forward=forward_fixture.Release211UITests.forward
    def test_removed_tools_overview_and_navigation_jump_buttons(self):
        self.show();app=self.app;app.show_page('随机回忆');self.root.update()
        self.assertNotIn('归档小工具',app.tab_routes);self.assertNotIn('归档小工具',app.pages);self.assertFalse(hasattr(app.toolbox_panel,'home'))
        for name in ('随机回忆','文字小工坊','时光胶囊'):
            labels=[str(w.cget('text')) for w in app.descendants(app.toolbox_panel.views[name]) if w.winfo_class()=='TButton']
            self.assertFalse(any(x.startswith('← ') for x in labels))
    def test_page_switch_and_generic_selection_do_not_create_a_toast(self):
        self.show();app=self.app;app.feedback.show('旧提示')
        app.feedback.receipt('聊天归档',app.status.get());self.root.update();self.assertFalse(app.feedback.frame.winfo_ismapped())
        app.feedback.receipt('任意选择',app.status.get());self.root.update();self.assertFalse(app.feedback.frame.winfo_ismapped())
        app.status.set('内容已复制。');app.feedback.receipt('复制','旧状态');self.root.update();self.assertTrue(app.feedback.frame.winfo_ismapped())
    def test_forward_fit_has_no_nested_idle_drain_and_text_width_stays_fixed_during_resize(self):
        _,control=self.forward(3,True);control.toggle();self.settle(lambda:len(control.rendered)==3 and not control.resize_job)
        widget=control.rendered[0][2];before=widget.winfo_width()
        with patch.object(control,'update_idletasks',side_effect=AssertionError('nested event drain')):
            self.root.geometry('1400x760');self.root.update_idletasks();self.assertEqual(widget.winfo_width(),before)
            self.root.after(240,self.root.quit);self.root.mainloop()
        self.assertEqual(self.errors,[])

if __name__=='__main__':unittest.main(verbosity=2)
