"""Revision-bound caches, responsive reads, lazy images and allocation-light resizing."""
import copy,sqlite3,threading,time,tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_workbench as fixture
from test_sixu_v1 import RichFixture
from wechat_archive.ui.application_controller import ApplicationController
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.errors import ConflictError,ValidationError
from wechat_archive.ui.thumbnail_service import ThumbnailService
from wechat_archive.ui.theme import Theme


class LargeReadTests(RichFixture):
    def test_cache_reuses_validation_but_invalidates_on_external_change(self):
        self.importer().import_file(self.source);c=self.controller()
        import wechat_archive.ui.application_controller as module
        with patch.object(module,'inspect_archive',wraps=module.inspect_archive) as inspect:
            first=c.messages(1,2);first['items'][0]['content']='仅修改返回值'
            self.assertNotEqual(c.messages(1,2)['items'][0]['content'],'仅修改返回值')
            c.contacts(1);c.contacts(1,'伙伴');self.assertEqual(inspect.call_count,0)
            with sqlite3.connect(self.db) as conn:conn.execute("UPDATE messages SET content='外部已更新' WHERE id=1")
            self.assertEqual(c.messages(1,2)['items'][0]['content'],'外部已更新');self.assertEqual(inspect.call_count,1)
        with self.assertRaises(ValidationError):c.messages(True,2)

    def test_invalid_changed_archive_cannot_reuse_validated_results(self):
        self.importer().import_file(self.source);c=self.controller();c.messages(1,2)
        with sqlite3.connect(self.db) as conn:conn.execute('PRAGMA foreign_keys=OFF');conn.execute('DELETE FROM users WHERE id=2')
        with self.assertRaises(ConflictError):c.messages(1,2)

    def test_rich_page_offset_is_preserved_after_attachment_batch(self):
        for index in range(205):
            row=copy.deepcopy(self.payload['messages'][0]);row.update(id='page-'+str(index),content='分页 '+str(index));self.payload['messages'].append(row)
        self.write();self.importer().import_file(self.source);c=self.controller()
        page=c.messages(1,2,offset=200)
        self.assertEqual(page['offset'],200);self.assertFalse(page['has_more']);self.assertEqual(len(page['items']),6)


class ResponsiveBrowseTests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def wait_for(self,predicate,timeout=4):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.root.update()
            if predicate():return
            time.sleep(.005)
        self.fail('后台读取未在测试期限内完成')

    def test_latest_search_replaces_pending_work_and_keeps_tk_responsive(self):
        self.show();app=self.app;app.background_browsing=True;entered=threading.Event();release=threading.Event();self.addCleanup(release.set);calls=[]
        original=ApplicationController._messages
        def slow(reader,*args,**kwargs):
            calls.append(args);entered.set();release.wait(2);return original(reader,*args,**kwargs)
        with patch.object(ApplicationController,'_messages',slow):
            app.search_word.set('旧搜索');app.load_messages();self.wait_for(entered.is_set)
            ticks=[];self.root.after(5,lambda:ticks.append(True));self.wait_for(lambda:bool(ticks))
            for index in range(20):app.search_word.set('已替换'+str(index));app.load_messages()
            app.search_word.set('论文修改');app.load_messages();app.busy=True;release.set()
            try:
                self.wait_for(lambda:app.browser_reads.future.done());self.assertNotEqual(getattr(app,'loaded_query',None)[2],'论文修改')
            finally:app.busy=False
            self.wait_for(lambda:app.browser_reads.future is None)
        self.assertEqual(app.loaded_query[2],'论文修改');self.assertLessEqual(len(calls),2)
        self.assertGreater(app.message_total,0)
        app.search_scope.set('全部会话');app.load_messages();self.wait_for(lambda:app.browser_reads.future is None and not getattr(app.chat_text,'rendering',False))
        saved=[row['id'] for row in app.message_rows];app.show_context(self.second)
        self.wait_for(lambda:app.browser_reads.future is None and not getattr(app.chat_text,'rendering',False));self.assertEqual(app.peer_id,3)
        app.return_search_results();self.wait_for(lambda:not getattr(app.chat_text,'rendering',False) and not getattr(app.chat_text,'render_after_job',None))
        self.assertEqual([row['id'] for row in app.message_rows],saved);self.assertIsNone(app.loaded_query[1])
        self.assertEqual(self.errors,[])

    def test_default_startup_reads_off_tk_and_can_close_pending(self):
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        profile=self.folder/'startup-profile';c=ApplicationController(profile);c.open_archive(self.app.controller.database)
        other_root=tk.Tk();other_root.withdraw();original=ApplicationController._contacts
        def slow(reader,*args):entered.set();release.wait(2);return original(reader,*args)
        with patch.object(ApplicationController,'_contacts',slow):
            other=ApplicationWindow(other_root,data_dir=profile)
            try:
                end=time.monotonic()+2
                while not entered.is_set() and time.monotonic()<end:other_root.update();time.sleep(.005)
                self.assertTrue(entered.is_set());ticks=[];other_root.after(1,lambda:ticks.append(True))
                end=time.monotonic()+1
                while not ticks and time.monotonic()<end:other_root.update();time.sleep(.002)
                self.assertTrue(ticks);self.assertTrue(other.background_browsing)
            finally:other.close();release.set()

    def test_resize_burst_coalesces_and_reuses_surface_item(self):
        self.show();app=self.app;self.root.after(100,self.root.quit);self.root.mainloop()
        view=app.chat_text
        with patch.object(view,'reflow',wraps=view.reflow) as reflow:
            for width in range(900,1100,10):self.root.geometry(str(width)+'x700');self.root.update_idletasks()
            self.root.after(180,self.root.quit);self.root.mainloop();self.root.update()
            self.assertLess(reflow.call_count,6)
        card=next(iter(app.contact_tree.cards.values()))[0];shape=card.find_withtag('surface')
        for width in range(200,230):card.resize(SimpleNamespace(width=width,height=90))
        self.assertEqual(shape,card.find_withtag('surface'))
        self.assertFalse(app.header_archive.winfo_ismapped());self.assertIn('Quiet.TButton',str(app.copilot_button.cget('style')))
        self.assertEqual(self.errors,[])

    def test_navigation_feedback_is_cancellable_and_respects_reduce_motion(self):
        self.show();app=self.app;app.ui_settings['reduce_motion']=False
        for page in ('设置','添加记录','帮助','聊天归档'):app.show_page(page);self.root.update_idletasks()
        self.wait_for(lambda:app.navigation_feedback.job is None)
        self.assertIsNone(app.navigation_feedback.job);self.assertTrue(app.navigation_feedback.rail.winfo_ismapped())
        app.ui_settings['reduce_motion']=True;app.show_page('设置');self.root.update_idletasks()
        self.assertIsNone(app.navigation_feedback.job);self.assertEqual(self.errors,[])

    def test_incremental_rows_virtualize_content_and_keep_append_position(self):
        self.show();app=self.app;app.background_browsing=True;view=app.chat_text;base=app.message_rows[0]
        rows=[{**base,'id':1000+index,'content':'需要核对的自建消息，'*8+str(index)} for index in range(100)]
        app.message_rows=rows;app.message_total=110;view.set_rows_incremental(rows,app.owner_id)
        self.wait_for(lambda:not view.rendering and not getattr(view,'cleanup_job',None))
        self.assertEqual(len(view.rows),100);self.assertGreater(sum(bool(x.get('collapsed_children')) for x in view.bubbles.values()),50)
        view.canvas.yview_moveto(1);self.root.update();self.root.after(80,self.root.quit);self.root.mainloop()
        self.assertFalse(view.bubbles[1099].get('collapsed_children'));top=view.canvas.canvasy(0)
        more=[{**base,'id':2000+index,'content':'更多 '+str(index)} for index in range(10)]
        app.message_rows+=more;view.set_rows_incremental(more,app.owner_id,append=True)
        self.wait_for(lambda:not view.rendering);self.root.after(100,self.root.quit);self.root.mainloop()
        self.assertEqual(len(view.rows),110);self.assertAlmostEqual(top,view.canvas.canvasy(0),delta=4)
        self.root.geometry('980x700');self.root.after(160,self.root.quit);self.root.mainloop();self.root.update()
        self.wait_for(lambda:not view.reflow_busy and not view.layout_job)
        visible=[value['text'] for value in view.bubbles.values() if value['text'].winfo_ismapped()]
        self.assertTrue(visible)
        for text in visible:
            bounds=text.bbox('end-1c');self.assertIsNotNone(bounds)
            self.assertLessEqual(bounds[1]+bounds[3],text.winfo_height()+2)
        self.assertEqual(self.errors,[])


class ThumbnailResponsivenessTests(RichFixture):
    def setUp(self):
        super().setUp();self.importer().import_file(self.source);self.c=self.controller()
        self.root=tk.Tk();self.root.withdraw();self.addCleanup(self.close_root);self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.theme=Theme(self.root,mode='green');self.addCleanup(self.theme.close)
        self.app=SimpleNamespace(root=self.root,controller=self.c,theme=self.theme,owner_id=1)
        self.service=ThumbnailService(self.app);self.app.thumbnail_service=self.service;self.addCleanup(self.service.close)
        self.row=next(row for row in self.c.messages(1,self.group(self.c)['id'])['items'] if any(item['kind']=='image' for item in row['attachments']))
        self.item=self.row['attachments'][0]
    def close_root(self):
        self.root.update_idletasks();self.root.destroy()
    def pump(self,predicate):
        end=time.monotonic()+3
        while time.monotonic()<end:
            self.root.update()
            if predicate():return
            time.sleep(.005)
        self.fail('缩略图未在期限内完成')
    def test_duplicate_images_share_one_decode_and_idle_poll_stops(self):
        import wechat_archive.importer.rich_importer as media
        original=media.ready_media;entered=threading.Event();release=threading.Event();self.addCleanup(release.set);calls=[]
        def blocked(*args):calls.append(threading.current_thread().name);entered.set();release.wait(2);return original(*args)
        canvases=[tk.Canvas(self.root,width=80,height=60) for _ in range(4)]
        with patch.object(media,'ready_media',blocked):
            for canvas in canvases:self.service.submit(self.item,canvas,120,100)
            self.assertTrue(entered.wait(1));self.assertEqual(len(self.service.active),1);release.set()
            self.pump(lambda:all(hasattr(canvas,'image') for canvas in canvases))
        self.assertEqual(len(calls),1);self.assertTrue(calls[0].startswith('sixu-thumbnail'))
        self.assertIsNone(self.service.job);self.assertEqual(self.errors,[])
    def test_thumbnail_pending_queue_is_bounded(self):
        import wechat_archive.importer.rich_importer as media
        original=media.ready_media;release=threading.Event();self.addCleanup(release.set)
        def blocked(*args):release.wait(2);return original(*args)
        canvases=[tk.Canvas(self.root,width=80,height=60) for _ in range(50)]
        with patch.object(media,'ready_media',blocked):
            for index,canvas in enumerate(canvases):self.service.submit(self.item,canvas,100+index,100)
            self.assertLessEqual(len(self.service.active),2);self.assertLessEqual(len(self.service.pending),24)
            self.service.close();release.set()
        self.assertEqual(self.errors,[])

    def test_changed_media_does_not_reuse_cached_picture(self):
        canvas=tk.Canvas(self.root,width=80,height=60);self.service.submit(self.item,canvas,120,100)
        self.pump(lambda:hasattr(canvas,'image'))
        from wechat_archive.importer.rich_importer import resource_path,media_root
        path=resource_path(media_root(self.db),self.item['relative_uri']);path.write_bytes(path.read_bytes()+b'changed')
        self.service.submit(self.item,canvas,120,100);self.pump(lambda:not self.service.active)
        self.assertTrue(any(canvas.type(item)=='text' and canvas.itemcget(item,'text')=='预览未完成' for item in canvas.find_all()))
        self.assertEqual(self.errors,[])
    def test_offscreen_images_wait_until_visible(self):
        from wechat_archive.ui.message_widgets import BubbleTimeline
        import wechat_archive.importer.rich_importer as media
        original=media.ready_media;release=threading.Event();self.addCleanup(release.set)
        def blocked(*args):release.wait(2);return original(*args)
        self.root.geometry('440x320');self.root.attributes('-alpha',0);self.root.deiconify()
        view=BubbleTimeline(self.root,self.theme);view.app=self.app;view.pack(fill='both',expand=True)
        rows=[{**copy.deepcopy(self.row),'id':1000+index} for index in range(50)]
        with patch.object(media,'ready_media',blocked):
            view.set_rows(rows,1);self.root.update()
            requested=sum(canvas._thumbnail_requested for _,canvas in view.thumbnails)
            self.assertGreater(requested,0);self.assertLess(requested,15)
            self.assertLessEqual(len(self.service.active),1)
            view.canvas.yview_moveto(1);self.root.update();release.set()
            self.pump(lambda:len(self.service.active)==0 and len(self.service.pending)==0)
        view.destroy();self.assertEqual(self.errors,[])
