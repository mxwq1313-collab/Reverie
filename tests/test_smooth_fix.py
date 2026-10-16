"""Synthetic stable-source and real Tk regressions for the reported failures."""
import hashlib
import logging
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from wechat_archive.errors import ArchiveError
from wechat_archive.wechat_source.snapshot_view import StableReadViews


class FakeSDK:
    def __init__(self, root):
        self.root = root
        self.workdir = str(root / 'decoded')
        Path(self.workdir).mkdir()
        self.source = root / 'source.db'
        with sqlite3.connect(self.source) as c:
            c.execute('CREATE TABLE messages(body TEXT)')
            c.execute("INSERT INTO messages VALUES ('original')")
        self.calls = 0
        self.change_open = False
        self.warn = False
        self._keys = {'message/message_0.db': b'synthetic'}
    def _db_path(self, rel):
        return str(self.source)
    def _open(self, rel):
        self.calls += 1
        path = Path(self.workdir) / 'message__message_0.db'
        shutil.copyfile(self.source, path)
        if self.change_open:
            with sqlite3.connect(self.source) as c:
                c.execute("INSERT INTO messages VALUES ('new')")
        if self.warn:
            logging.getLogger('readonly_wechat_source').warning('synthetic incomplete WAL')
        return sqlite3.connect(path)
    def _message_dbs(self):
        return list(self._keys)
    def _collect_db_files(self):
        return [(rel, str(self.source), 0) for rel in self._keys]


class FakeViews(StableReadViews, FakeSDK):
    pass


class StableViewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.db = FakeViews(Path(tmp.name))
    def test_new_live_messages_do_not_invalidate_captured_view(self):
        first = self.db._open('message/message_0.db'); first.close()
        with sqlite3.connect(self.db.source) as c:
            c.execute("INSERT INTO messages VALUES ('later')")
        other = self.db._open('message/message_0.db')
        try:
            self.assertEqual(other.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 1)
            self.assertEqual(self.db.calls, 1)
            with self.assertRaises(sqlite3.OperationalError):
                other.execute("INSERT INTO messages VALUES ('forbidden')")
        finally: other.close()
        self.db.check_read_views()
    def test_opening_a_changing_source_retries_and_then_rejects(self):
        self.db.change_open = True
        with self.assertRaisesRegex(ArchiveError, '3次'):
            self.db._open('message/message_0.db')
        self.assertEqual(self.db.calls, 3)
        self.assertEqual(self.db.__dict__.get('_read_views'), {})
    def test_transient_source_change_can_recover(self):
        sdk_open = FakeSDK._open
        def one_change(db, rel):
            db.change_open = db.calls == 0
            return sdk_open(db, rel)
        with patch.object(FakeSDK, '_open', one_change):
            conn = self.db._open('message/message_0.db')
        try: self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 2)
        finally: conn.close()
        self.assertEqual(self.db.calls, 2)
    def test_sdk_incomplete_wal_warning_is_never_accepted(self):
        self.db.warn = True
        with self.assertRaisesRegex(ArchiveError, '未合并日志'):
            self.db._open('message/message_0.db')
        self.assertEqual(self.db.calls, 3)
    def test_transient_sdk_fallback_retries_without_poisoning_success(self):
        sdk_open = FakeSDK._open
        def one_warning(db, rel):
            db.warn = db.calls == 0
            return sdk_open(db, rel)
        logger = logging.getLogger('readonly_wechat_source')
        seen = []
        class OuterWarnings(logging.Handler):
            def emit(self, record): seen.append(True)
        handler = OuterWarnings(logging.WARNING); logger.addHandler(handler)
        try:
            with patch.object(FakeSDK, '_open', one_warning):
                conn = self.db._open('message/message_0.db')
            conn.close()
            self.assertEqual(self.db.calls, 2)
            self.assertEqual(seen, [])
        finally: logger.removeHandler(handler)
    def test_changed_local_copy_is_rejected(self):
        conn = self.db._open('message/message_0.db'); conn.close()
        path = next(iter(self.db._read_views.values()))[0]
        with path.open('ab') as f: f.write(b'changed')
        with self.assertRaises(ArchiveError): self.db.check_read_views()
        with self.assertRaises(ArchiveError): self.db._open('message/message_0.db')
    def test_new_shard_inventory_is_not_silently_omitted(self):
        self.db._message_dbs()
        self.db._keys['message/message_1.db'] = b'synthetic'
        with self.assertRaisesRegex(ArchiveError, '分片清单变化'):
            self.db.check_read_views()
    def test_wal_mode_header_does_not_create_sidecars_on_read(self):
        with sqlite3.connect(self.db.source) as c:
            self.assertEqual(c.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        c.close()
        conn = self.db._open('message/message_0.db')
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 1)
            path = next(iter(self.db._read_views.values()))[0]
            self.assertFalse(Path(str(path) + '-wal').exists())
            self.assertFalse(Path(str(path) + '-shm').exists())
            self.db.check_read_views()
        finally: conn.close()


class SmoothUIFixTests(unittest.TestCase):
    def setUp(self):
        from wechat_archive.ui.theme import Theme
        self.root = tk.Tk(); self.root.attributes('-alpha', 0); self.root.geometry('760x540')
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args))
        self.theme = Theme(self.root, mode='green')
        self.addCleanup(self.root.destroy); self.addCleanup(self.theme.close)
        self.addCleanup(self.root.update_idletasks)
    def pump(self, condition, timeout=4):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.root.update()
            if condition(): return
            time.sleep(.002)
        self.fail('Pending UI work did not settle')
    def test_emoticons_are_images_while_raw_copy_search_selection_survive(self):
        from wechat_archive.ui.inline_emojis import render_inline, resize_inline
        text = tk.Text(self.root); text.pack()
        raw = '你好😀[流泪][流泪]\n[捂脸] 还有[未知表情]'
        text.insert('1.0', raw); render_inline(text, self.theme); text.configure(state='disabled')
        self.root.update()
        self.assertEqual(len(text.image_names()), 3)
        self.assertEqual(text.get('1.0', 'end-1c'), raw)
        self.assertTrue(text.search('[流泪]', '1.0', exact=True, elide=True))
        text.tag_add('sel', '1.0', 'end-1c'); before = text.tag_ranges('sel')
        self.theme.set_fonts(21, self.theme.family)
        resize_inline(text, self.theme)
        self.assertEqual(text.tag_ranges('sel'), before)
        self.assertEqual(text.get('sel.first', 'sel.last'), raw)
        self.assertEqual(len(text.image_names()), 3)
        self.assertEqual(self.errors, [])
    def test_catalog_pixels_have_provenance_and_nontransparent_tears(self):
        from wechat_archive.ui.inline_emojis import atlas, catalog
        import base64
        data = catalog()
        self.assertEqual(len(data['positions']), 109)
        self.assertEqual(hashlib.sha256(base64.b64decode(data['png_base64'])).hexdigest(), data['png_sha256'])
        self.assertIsNotNone(atlas().crop(data['positions']['[流泪]']).getbbox())
    def test_collapsed_groups_do_not_create_all_members_and_expansion_yields(self):
        from wechat_archive.ui.source_tree import SourceTreeRenderer
        tree = ttk.Treeview(self.root); tree.pack(fill='both', expand=True)
        renderer = SourceTreeRenderer(SimpleNamespace(source_tree=tree, refresh_source_selection=lambda: None))
        self.addCleanup(renderer.cancel)
        members = [{'name':str(n), 'message_count':n, 'ratio':.01} for n in range(3000)]
        rows = [{'kind':'group','name':'自建群','members':members,'message_count':3000}]
        renderer.set_rows(rows)
        self.assertEqual(len(tree.get_children('0')), 1)
        tree.focus('0'); tree.item('0', open=True); renderer.open_group()
        ticks=[]; self.root.after(1, lambda: ticks.append(True))
        self.pump(lambda: bool(ticks))
        self.assertLess(len(tree.get_children('0')), 3000)
        self.pump(lambda: len(tree.get_children('0')) == 3000)
        self.assertEqual(renderer.loaded['0'], 3000)
        self.assertEqual(self.errors, [])
    def test_cancelled_source_render_cannot_repopulate_new_account(self):
        from wechat_archive.ui.source_tree import SourceTreeRenderer
        tree = ttk.Treeview(self.root); tree.pack()
        renderer = SourceTreeRenderer(SimpleNamespace(source_tree=tree, refresh_source_selection=lambda: None))
        self.addCleanup(renderer.cancel)
        renderer.set_rows([{'name':str(n)} for n in range(1000)])
        self.assertEqual(len(tree.get_children()), 60)
        renderer.set_rows([{'name':'new'}]); self.root.after(80, self.root.quit); self.root.mainloop()
        self.assertEqual(tree.get_children(), ('0',))
        self.assertEqual(tree.item('0', 'text'), 'new')
        self.assertEqual(self.errors, [])
    def test_long_layout_yields_and_switch_cancels_old_layout(self):
        from wechat_archive.ui.message_widgets import BubbleTimeline
        view = BubbleTimeline(self.root, self.theme); view.pack(fill='both', expand=True)
        rows = [{'id':n,'sender_id':1,'sender_name':'自己','receiver_name':'伙伴','create_time':'2026-10-16T00:00:00Z','content':'混合表情[流泪]文字 '*20,'msg_type':'text'} for n in range(150)]
        view.set_rows(rows, 1); self.root.update_idletasks()
        self.pump(lambda: not view.reflow_busy and bool(getattr(view,'completed_layout',None)))
        self.theme.set_fonts(20, self.theme.family); self.theme.generation += 1
        ticks=[]; self.root.after(1, lambda: ticks.append(True)); view.reflow()
        self.assertTrue(view.reflow_busy)
        self.pump(lambda: bool(ticks))
        view.set_rows(rows[:2], 1)
        self.pump(lambda: not view.reflow_busy and bool(getattr(view,'completed_layout',None)))
        self.assertEqual(len(view.bubbles), 2)
        self.assertTrue(all(len(value['text'].image_names()) == 20 for value in view.bubbles.values()))
        self.assertEqual(self.errors, [])


if __name__ == '__main__': unittest.main(verbosity=2)
