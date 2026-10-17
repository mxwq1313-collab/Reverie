"""Internal split drags must resize real panels and survive queued layouts."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_workbench as fixture


class InternalResizeTests(unittest.TestCase):
    setUp = fixture.WorkbenchTests.setUp
    show = fixture.WorkbenchTests.show

    def drag_native(self, panes, target):
        x, y = panes.sash_coord(0)
        panes.event_generate('<ButtonPress-1>', x=x+2, y=180)
        self.root.update()
        panes.event_generate('<B1-Motion>', x=target+2, y=180, state=256)
        self.root.update()
        return target+2

    def release_native(self, panes, x):
        panes.event_generate('<ButtonRelease-1>', x=x, y=180)
        self.root.update()

    def test_contact_split_tracks_drag_before_release_and_saves_once(self):
        self.show(1800,850)
        app=self.app;panes=app.browser_panes
        before=app.conversation_column.winfo_width()
        with patch.object(app.controller,'save_browser_layout',wraps=app.controller.save_browser_layout) as save:
            x=self.drag_native(panes,before+70)
            during=app.conversation_column.winfo_width()
            self.assertGreater(during,before+40)
            self.assertTrue(panes._split_dragging)
            app.layout_key=None;app.adapt_layout();self.root.update()
            self.assertAlmostEqual(app.conversation_column.winfo_width(),during,delta=2)
            save.assert_not_called()
            self.release_native(panes,x)
            self.assertEqual(save.call_count,1)
        self.assertFalse(panes._split_dragging)
        self.assertAlmostEqual(app.controller.browser_layout()['width'],during/app.theme.scale,delta=2)
        self.assertEqual(self.errors,[])

    def test_copilot_native_split_does_not_snap_back_before_commit(self):
        self.show(1800,850)
        app=self.app;panes=app.workspace_panes
        before=app.copilot_host.winfo_width();sx=panes.sash_coord(0)[0]
        with patch.object(app.controller,'save_copilot_layout',wraps=app.controller.save_copilot_layout) as save:
            x=self.drag_native(panes,sx-80)
            during=app.copilot_host.winfo_width()
            self.assertGreater(during,before+50)
            app.layout_key=None;app.adapt_layout();self.root.update()
            self.assertAlmostEqual(app.copilot_host.winfo_width(),during,delta=2)
            save.assert_not_called()
            self.release_native(panes,x)
            self.assertEqual(save.call_count,1)
        self.assertFalse(panes._split_dragging)
        self.assertAlmostEqual(app.controller.copilot_layout()['width'],during/app.theme.scale,delta=2)
        self.assertEqual(self.errors,[])

    def test_grip_motion_coalesces_and_does_not_map_a_black_guide(self):
        self.show(900,700);app=self.app;identity=str(app.copilot_host)
        app.start_copilot_drag(SimpleNamespace(x_root=600))
        with patch.object(app.controller,'save_copilot_layout',wraps=app.controller.save_copilot_layout) as save:
            job=None
            for x in range(599,520,-1):
                app.drag_copilot(SimpleNamespace(x_root=x))
                if job is None:job=app.copilot_drag_job
                self.assertEqual(app.copilot_drag_job,job)
            self.root.update()
            self.assertGreater(app.copilot_host.winfo_width(),app.theme.u(400))
            self.assertFalse(app.copilot_guide.winfo_ismapped())
            self.assertEqual(str(app.copilot_host),identity)
            save.assert_not_called()
            app.finish_copilot_drag();self.root.update()
            self.assertEqual(save.call_count,1)
        self.assertIsNone(app.copilot_grip.grab_current())
        self.assertEqual(self.errors,[])

    def test_cancel_releases_capture_and_cancels_pending_motion(self):
        self.show(900,700);app=self.app;original=app.copilot_width
        app.start_copilot_drag(SimpleNamespace(x_root=600))
        app.drag_copilot(SimpleNamespace(x_root=530))
        app.cancel_copilot_drag();self.root.update()
        self.assertEqual(app.copilot_width,original)
        self.assertIsNone(app.copilot_drag_job)
        self.assertIsNone(app.copilot_drag)
        self.assertIsNone(app.copilot_grip.grab_current())
        self.assertFalse(app.copilot_guide.winfo_ismapped())
        self.assertEqual(app.controller.copilot_layout()['width'],original)
        self.assertEqual(self.errors,[])

    def test_unmapping_drag_handle_cancels_uncommitted_width(self):
        self.show(900,700);app=self.app;original=app.copilot_width
        app.start_copilot_drag(SimpleNamespace(x_root=600))
        app.drag_copilot(SimpleNamespace(x_root=530));self.root.update()
        self.assertNotEqual(app.copilot_width,original)
        app.copilot_grip.grid_remove();self.root.update()
        self.assertEqual(app.copilot_width,original)
        self.assertIsNone(app.copilot_drag_job)
        self.assertIsNone(app.copilot_grip.grab_current())
        self.assertFalse(app.copilot_guide.winfo_ismapped())
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main()
