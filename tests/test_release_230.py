"""2.3 navigation, stable hover lifecycle and retained native controls."""
import time
import unittest
from unittest.mock import patch
import test_workbench as fixture
class Release230UITests(unittest.TestCase):
    def setUp(self):
        fixture.WorkbenchTests.setUp(self)
        self.root.tk.createcommand('bgerror',lambda message:self.errors.append(message))
    show=fixture.WorkbenchTests.show

    def test_removed_workshop_has_no_widget_instance_or_navigation(self):
        self.show();app=self.app
        self.assertNotIn('文字小工坊',app.pages);self.assertNotIn('文字小工坊',app.tab_routes);self.assertFalse(hasattr(app.toolbox_panel,'workshop'))
        self.assertFalse(hasattr(app,'memory_popup'));self.assertFalse(hasattr(app,'memory_button'))
        app.show_page('随机回忆');self.root.update();self.assertEqual(app.current_subpage,'随机回忆');self.assertTrue(app.toolbox_panel.random.memory.winfo_viewable())
        labels=[w.cget('text') for w in app.descendants(app.toolbox_panel.views['随机回忆']) if w.winfo_class()=='TLabel']
        self.assertEqual(labels.count('随机回忆'),1)
        self.assertEqual({app.capsule_button.icon,app.nav_note.icon},{'capsule','stats'});self.assertEqual(self.errors,[])

    def test_hover_is_single_instance_stays_beside_target_and_keeps_focus(self):
        self.show();button=self.app.capsule_button;button.focus_force();self.root.update();hint=button._action_hint;hint.hide();before=self.root.focus_get()
        hint.enter();hint.show();self.root.update();tip=hint.tip;self.assertIsNotNone(tip)
        first=str(tip);hint.enter();hint.show();self.root.update();self.assertEqual(str(hint.tip),first)
        self.assertEqual(self.root.focus_get(),before)
        self.assertGreaterEqual(tip.winfo_rootx(),button.winfo_rootx()+button.winfo_width())
        self.assertLessEqual(tip.winfo_rooty()+tip.winfo_height(),self.root.winfo_screenheight())
        self.app.nav_note.show_tip();self.root.update();self.assertIsNone(hint.tip);self.assertIsNotNone(self.app.nav_note._action_hint.tip)
        self.app.nav_note.hide_tip();self.assertEqual(self.errors,[])

    def test_tooltip_cancels_on_resize_click_and_fast_enter_leave(self):
        self.show();hint=self.app.capsule_button._action_hint
        for _ in range(20):hint.enter();hint.leave()
        self.root.after(350,self.root.quit);self.root.mainloop();self.assertIsNone(hint.tip);self.assertIsNone(hint.job)
        hint.show();self.root.update();self.assertIsNotNone(hint.tip)
        self.root.geometry('1240x800');self.root.update();self.assertIsNone(hint.tip);self.assertIsNone(hint.owner_binding)
        hint.show();hint.hide();self.root.update();self.assertIsNone(hint.tip);self.assertEqual(self.errors,[])

    def test_new_scroll_intent_supersedes_a_pending_layout_restore(self):
        self.show(1100,650);view=self.app.chat_text
        self.root.update();view.canvas.yview_moveto(.2);self.root.update()
        before=view.canvas.yview()[0]
        self.assertGreater(before,0)
        view.pending_top=0;view.pending_anchor=(next(iter(view.bubbles)),0)
        view.restore_job=view.after(100,view.restore_scroll)
        view.body.event_generate('<MouseWheel>',delta=-120);self.root.update()
        self.root.after(150,self.root.quit);self.root.mainloop()
        self.assertGreater(view.canvas.yview()[0],before)
        view.pending_top=0;view.pending_anchor=(next(iter(view.bubbles)),0)
        view.restore_job=view.after(100,view.restore_scroll)
        view.user_yview('moveto',.4)
        self.root.after(150,self.root.quit);self.root.mainloop()
        self.assertGreater(view.canvas.yview()[0],.35)
        self.assertEqual(self.errors,[])

    def test_resize_reuses_theme_textures_and_retains_actual_control_dimensions(self):
        self.show();app=self.app;photos=tuple(map(str,app.theme.images));before=app.owner_box.winfo_reqheight()
        self.assertTrue(app.theme.images)
        for geometry in ('980x700','1450x850','1100x760'):
            self.root.geometry(geometry);self.root.update()
            self.assertEqual(tuple(map(str,app.theme.images)),photos)
            self.assertEqual(app.owner_box.winfo_reqheight(),before)
            self.assertTrue(app.workspace_panes.winfo_viewable())
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main(verbosity=2)
