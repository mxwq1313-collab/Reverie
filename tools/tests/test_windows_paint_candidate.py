"""Native geometry invalidation must stay live and preserve widget lifetime."""
import sys
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from tools.windows_paint_candidate import install


@unittest.skipUnless(sys.platform == 'win32', 'Windows native painting')
class NativePaintTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.root.geometry('700x460')
        self.frame = ttk.Frame(self.root)
        self.frame.pack(fill='both', expand=True)
        self.text = tk.Text(self.frame, wrap='word')
        self.text.pack(fill='both', expand=True)
        self.text.insert('1.0', '连续缩放时保留正文、选区与原控件。'*80)
        self.text.tag_add('sel', '1.0', '1.5')
        self.batch = install(self.root)
        self.assertIsNotNone(self.batch)
        self.addCleanup(self.cleanup)
        self.root.deiconify()
        self.root.update()

    def cleanup(self):
        self.batch.close()
        self.root.destroy()
        self.assertEqual(self.errors, [])

    def test_every_resize_flushes_without_waiting_for_the_last_resize(self):
        identity = self.text.winfo_id()
        observed = []
        for width in (760, 620, 810, 690, 780):
            before = self.batch.batches
            self.root.geometry(f'{width}x460')
            self.root.update()
            observed.append(self.batch.batches-before)
            self.assertEqual(self.text.winfo_id(), identity)
            self.assertTrue(self.text.winfo_viewable())
            self.assertEqual(self.text.get('1.0', '1.5'), '连续缩放时')
            self.assertTrue(self.text.tag_ranges('sel'))
            self.assertEqual(self.text.winfo_width(), self.frame.winfo_width())
            self.assertFalse(self.batch.pending)
        self.assertTrue(all(count > 0 for count in observed), observed)

    def test_newly_mapped_controls_are_watched_and_destroyed_handles_retired(self):
        for index in range(12):
            button = ttk.Button(self.frame, text=f'合成按钮 {index}')
            button.pack()
            self.root.update()
            handle = button.winfo_id()
            self.assertIn(handle, self.batch.windows)
            button.destroy()
            self.root.update()
            self.assertNotIn(handle, self.batch.windows)
            self.assertNotIn(handle, self.batch.pending)

    def test_popup_is_outside_the_main_window_batch(self):
        popup = tk.Toplevel(self.root)
        label = ttk.Label(popup, text='独立弹窗')
        label.pack()
        try:
            self.root.update()
            self.assertNotIn(popup.winfo_id(), self.batch.windows)
            self.assertNotIn(label.winfo_id(), self.batch.windows)
        finally:
            popup.destroy()
            self.root.update()

    def test_post_failure_falls_back_to_immediate_invalidation(self):
        with patch.object(self.batch.user, 'PostMessageW', return_value=0):
            self.root.geometry('790x490')
            self.root.update()
        self.assertGreater(self.batch.post_failures, 0)
        self.assertFalse(self.batch.pending)
        self.assertTrue(self.text.winfo_viewable())
        self.assertEqual(self.text.winfo_width(), self.frame.winfo_width())

    def test_close_detaches_only_its_bindings_and_handles(self):
        maps = []
        binding = self.root.bind('<Map>', lambda event: maps.append(event.widget), add='+')
        self.batch.close()
        self.batch.close()
        self.assertFalse(self.batch.windows)
        self.assertFalse(self.batch.pending)
        self.assertIn(binding, self.root.bind('<Map>'))
        button = ttk.Button(self.frame, text='关闭合并后仍正常布局')
        button.pack()
        self.root.geometry('800x490')
        self.root.update()
        self.assertIn(button, maps)
        self.assertTrue(button.winfo_viewable())
        self.assertFalse(self.batch.windows)

    def test_destroying_root_without_application_close_removes_native_callbacks(self):
        root = tk.Tk()
        root.withdraw()
        batch = install(root)
        root.deiconify()
        root.update()
        root.destroy()
        self.assertTrue(batch.closed)
        self.assertFalse(batch.windows)
        self.assertFalse(batch.pending)


if __name__ == '__main__':
    unittest.main()
