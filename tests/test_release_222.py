"""2.2.2 native resize, source preservation, and rounded platform icons."""
import io,time,hashlib,unittest,tkinter as tk
from PIL import Image,ImageOps
from unittest.mock import patch
import test_workbench as fixture
from wechat_archive.ui.app_logo import image,original,windows_icon

class RoundedLogoTests(unittest.TestCase):
    def test_rounded_alpha_keeps_original_art_and_central_pixels(self):
        before=hashlib.sha256(original()).hexdigest()
        for size in (16,24,32,64,256):
            result=image(size);self.assertEqual(result.size,(size,size))
            for point in ((0,0),(size-1,0),(0,size-1),(size-1,size-1)):self.assertEqual(result.getpixel(point)[3],0)
            with Image.open(io.BytesIO(original())) as source:expected=ImageOps.contain(source.convert('RGBA'),(size,size),Image.Resampling.LANCZOS)
            self.assertEqual(result.getpixel((size//2,size//2)),expected.getpixel((size//2,size//2)))
        self.assertEqual(hashlib.sha256(original()).hexdigest(),before)
    def test_icon_size_validation(self):
        for size in (True,0,-1,2048,1.5):
            with self.assertRaises(ValueError):image(size)

class Resize222Tests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def settle(self,timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.root.update()
            if not self.app.layout_job and not self.app.chat_text.layout_job and not getattr(self.app.chat_text,'reflow_busy',False):break
            time.sleep(.01)
        self.root.update();self.assertFalse(self.app.layout_job);self.assertEqual(self.errors,[])
    def test_workspace_is_retained_and_finally_fills_its_viewport(self):
        self.show(1100,720);self.settle();app=self.app;pane=app.workspace_panes;identity=str(pane)
        before=(pane.winfo_width(),pane.winfo_height())
        self.root.geometry('1450x850');self.root.update()
        self.assertTrue(pane.winfo_viewable());self.assertEqual(str(pane),identity)
        self.assertNotEqual((pane.winfo_width(),pane.winfo_height()),before)
        self.settle()
        self.assertAlmostEqual(pane.winfo_width(),app.resize_viewport.winfo_width(),delta=1)
        self.assertAlmostEqual(pane.winfo_height(),app.resize_viewport.winfo_height(),delta=1)
    def test_large_font_workspace_tracks_actual_parent_bounds(self):
        app=self.app;app.theme.update(24,app.theme.family,'dark','zh_CN',48)
        for width,height in ((820,600),(1450,850),(980,700),(820,600)):
            self.show(width,height);self.settle();viewport=app.resize_viewport;main=viewport.master
            self.assertLessEqual(viewport.winfo_x()+viewport.winfo_width(),main.winfo_width())
            self.assertAlmostEqual(viewport.winfo_height(),main.winfo_height(),delta=1)
            button=app.agent_panel.parameters_button
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
            room=max(app.theme.u(40),app.chat_header.winfo_width()-app.conversation_export_button.winfo_reqwidth()-app.theme.u(40))
            self.assertEqual(app.chat_title_label.cget('text'),app.theme.elide(app.chat_title.get(),room,renderer=app.theme.section_font))
        self.assertEqual(self.errors,[])

    def test_resize_preserves_raw_text_selection_and_widget_ids(self):
        self.show();self.settle();app=self.app;view=app.chat_text;value=next(v for v in view.bubbles.values() if v.get('text') is not None);text=value['text']
        text.tag_add('sel','1.0','1.3');before=text.get('1.0','end-1c');selected=text.get('sel.first','sel.last');identity=str(text)
        sizes=[(980,700),(1450,850),(1100,720)]
        def step(index=0):
            if index==len(sizes):self.root.after(500,self.root.quit);return
            w,h=sizes[index];self.root.geometry(f'{w}x{h}');self.root.after(35,lambda:step(index+1))
        self.root.after(1,step);self.root.mainloop();self.settle()
        self.assertTrue(text.winfo_exists());self.assertEqual(str(text),identity);self.assertEqual(text.get('1.0','end-1c'),before)
        self.assertEqual(text.get('sel.first','sel.last'),selected)
    def test_window_states_restore_and_keep_round_icon(self):
        self.show();self.settle();app=self.app
        for state in ('zoomed','normal','iconic','normal'):
            self.root.state(state);self.root.update();self.root.after(160,self.root.quit);self.root.mainloop()
        self.settle();self.assertTrue(app.workspace_panes.winfo_viewable())
        self.assertTrue(self.root.tk.call(str(app.window_logo),'transparency','get',0,0))
        icon=self.folder/'rounded.ico';windows_icon(icon)
        with Image.open(icon) as artwork:
            self.assertEqual(artwork.info['sizes'],{(n,n) for n in (16,24,32,48,64,128,256)})
            for size in artwork.info['sizes']:self.assertEqual(artwork.ico.getimage(size).convert('RGBA').getpixel((0,0))[3],0)
    def test_unchanged_title_reuses_measurement_and_font_changes_invalidate_it(self):
        self.show();self.settle();app=self.app;app.fit_chat_title()
        with patch.object(app.theme,'elide',wraps=app.theme.elide) as measure:
            app.fit_chat_title();app.fit_chat_title();self.assertEqual(measure.call_count,0)
            app.chat_title.set('新会话标题');self.assertGreater(measure.call_count,0)
            calls=measure.call_count;app.fit_chat_title();self.assertEqual(measure.call_count,calls)
            app.theme.update(20,app.theme.family,app.theme.mode,'zh_CN',48);app.fit_chat_title();self.assertGreater(measure.call_count,calls)
        self.assertEqual(self.errors,[])

    def test_identical_text_layout_does_not_reconfigure_widgets(self):
        from wechat_archive.ui.layout_config import configure_changed
        self.show();self.settle();label=self.app.chat_title_label;font=self.app.theme.section
        configure_changed(label,font=font)
        with patch.object(label,'configure',wraps=label.configure) as configure:
            self.assertFalse(configure_changed(label,font=font));self.assertEqual(configure.call_count,0)
            label.configure(font=('Arial',-12));configure.reset_mock()
            self.assertTrue(configure_changed(label,font=font));self.assertEqual(configure.call_count,1)
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main(verbosity=2)
