import hashlib
from html.parser import HTMLParser
from importlib.resources import files
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from wechat_archive import ChatService, ConflictError, NotFoundError, ValidationError
from wechat_archive.database.db import APPLICATION_ID
from wechat_archive.exporter import export_readable
from wechat_archive.ui.import_window import ImportWindow

ROOT = Path(__file__).resolve().parents[1]


class ChatHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.articles=[]; self.tags=[]; self.body=None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs=dict(attrs)
        if tag=='article':
            self.articles.append({'attributes':attrs,'content':''})
        if tag=='p' and attrs.get('class')=='body':
            self.body=self.articles[-1]

    def handle_data(self, data):
        if self.body is not None:self.body['content']+=data

    def handle_endtag(self, tag):
        if tag=='p':self.body=None


class ReadableExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.db=self.folder/'archive.db';self.out=self.folder/'readable'
        self.service=ChatService(self.db)
        self.a=self.service.create_user('unit_owner','测试自己')
        self.b=self.service.create_user('unit_peer','测试对方')
        self.c=self.service.create_user('unit_third','另一位')
        self.text='  中文🙂\n<script>alert("x")</script> & 原文  '
        self.service.create_message(self.a.id,self.b.id,self.text,create_time='2026-01-01T00:00:00.001Z')
        self.service.create_message(self.b.id,self.a.id,'回复\r\n第二行',create_time='2026-01-01T00:00:01Z')
        self.service.create_message(self.a.id,self.c.id,'另一会话',create_time='2026-01-02T00:00:00Z')

    def exporting(self, **options):return export_readable(self.db,self.out,**options)

    def test_selected_private_chat_preserves_body_and_direction(self):
        report=self.exporting(user_id=self.a.id,peer_id=self.b.id)
        self.assertEqual((report['messages'],report['conversations']),(2,1))
        parser=ChatHTML();parser.feed((self.out/'chat_1_2.html').read_bytes().decode('utf-8'))
        self.assertEqual([row['content'] for row in parser.articles],[self.text,'回复\r\n第二行'])
        self.assertEqual([row['attributes']['data-sender-id'] for row in parser.articles],['1','2'])
        self.assertEqual([row['attributes']['data-receiver-id'] for row in parser.articles],['2','1'])

    def test_html_text_is_escaped_and_has_no_active_resources(self):
        self.exporting()
        parser=ChatHTML();source=(self.out/'chat_1_2.html').read_text(encoding='utf-8');parser.feed(source)
        self.assertNotIn('script',parser.tags);self.assertNotIn('iframe',parser.tags);self.assertNotIn('img',parser.tags)
        self.assertIn('&lt;script&gt;',source);self.assertIn('Content-Security-Policy',source)

    def test_txt_utf8_original_whitespace_and_lines(self):
        self.exporting()
        text=(self.out/'chat_1_2.txt').read_bytes().decode('utf-8')
        self.assertIn(self.text,text);self.assertIn('回复\r\n第二行',text)
        self.assertIn('用户 1',text);self.assertIn('用户 2',text)

    def test_display_time_does_not_change_database(self):
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.exporting(display_timezone='+08:00')
        text=(self.out/'chat_1_2.txt').read_text(encoding='utf-8')
        self.assertIn('2026-01-01 08:00:00.001000+08:00',text)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)

    def test_all_pairs_have_index_and_counted_manifest(self):
        report=self.exporting()
        manifest=json.loads((self.out/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((report['messages'],report['conversations']),(3,2))
        self.assertEqual(manifest['messages'],3)
        self.assertIn('chat_1_3.html',(self.out/'index.html').read_text(encoding='utf-8'))
        for file in manifest['files']:
            self.assertEqual(hashlib.sha256((self.out/file['name']).read_bytes()).hexdigest(),file['sha256'])

    def test_view_identity_exports_its_full_range(self):
        self.assertEqual(self.exporting(user_id=self.b.id)['messages'],2)

    def test_existing_output_never_overwritten(self):
        self.out.mkdir();marker=self.out/'keep.txt';marker.write_text('original',encoding='utf-8')
        with self.assertRaises(ConflictError):self.exporting()
        self.assertEqual(marker.read_text(encoding='utf-8'),'original')
        self.assertEqual(len(list(self.out.iterdir())),1)

    @unittest.skipUnless(os.name=='nt','Windows directory publication')
    def test_transient_windows_folder_lock_is_retried(self):
        original=Path.rename;calls=[]
        def rename(path,target):
            calls.append(str(path))
            if len(calls)==1:
                error=PermissionError('temporary lock');error.winerror=5;raise error
            return original(path,target)
        with patch('wechat_archive.exporter.readable.Path.rename',new=rename),patch('wechat_archive.exporter.readable.time.sleep'):
            report=self.exporting()
        self.assertEqual(report['messages'],3);self.assertEqual(len(calls),2)

    @unittest.skipUnless(os.name=='nt','Windows directory publication')
    def test_retry_does_not_overwrite_concurrently_created_folder(self):
        def rename(path,target):
            self.out.mkdir();(self.out/'keep.txt').write_text('other writer',encoding='utf-8')
            error=PermissionError('temporary lock');error.winerror=32;raise error
        with patch('wechat_archive.exporter.readable.Path.rename',new=rename),patch('wechat_archive.exporter.readable.time.sleep'),self.assertRaises(ConflictError):
            self.exporting()
        self.assertEqual((self.out/'keep.txt').read_text(encoding='utf-8'),'other writer')
        self.assertEqual(list(self.folder.glob('.chat-export-*')),[])

    def test_source_cannot_be_output(self):
        before=self.db.read_bytes()
        with self.assertRaises(ConflictError):export_readable(self.db,self.db)
        self.assertEqual(self.db.read_bytes(),before)

    def test_missing_database_not_created(self):
        missing=self.folder/'missing.db'
        with self.assertRaises(NotFoundError):export_readable(missing,self.out)
        self.assertFalse(missing.exists());self.assertFalse(self.out.exists())

    def test_unknown_sqlite_not_modified(self):
        unknown=self.folder/'unknown.db'
        with sqlite3.connect(unknown) as connection:connection.execute('CREATE TABLE unrelated(id)')
        before=unknown.read_bytes()
        with self.assertRaises(ConflictError):export_readable(unknown,self.out)
        self.assertEqual(unknown.read_bytes(),before);self.assertFalse(self.out.exists())

    def test_missing_identity_and_invalid_filter_rejected(self):
        with self.assertRaises(NotFoundError):self.exporting(user_id=999)
        with self.assertRaises(ValidationError):self.exporting(peer_id=2)
        with self.assertRaises(ValidationError):self.exporting(user_id=True)
        with self.assertRaises(ValidationError):self.exporting(user_id=2**63)
        self.assertFalse(self.out.exists())

    def test_bad_display_zone_rejected_before_output(self):
        for value in ('Asia/Shanghai','+15:00','+08:70','+14:01'):
            with self.subTest(value=value),self.assertRaises(ValidationError):self.exporting(display_timezone=value)
        self.assertFalse(self.out.exists())

    def test_bad_time_leaves_no_partial_export(self):
        with sqlite3.connect(self.db) as connection:connection.execute("UPDATE messages SET create_time='unknown' WHERE id=1")
        with self.assertRaises(ConflictError):self.exporting()
        self.assertFalse(self.out.exists());self.assertEqual(list(self.folder.glob('.chat-export-*')),[])

    def test_empty_archive_has_clear_empty_index(self):
        empty=self.folder/'empty.db';ChatService(empty)
        report=export_readable(empty,self.out)
        self.assertEqual((report['messages'],report['conversations']),(0,0))
        self.assertIn('暂无聊天消息',(self.out/'index.html').read_text(encoding='utf-8'))

    def test_html_and_txt_can_be_requested_separately(self):
        txt=export_readable(self.db,self.out,formats=('txt',))
        self.assertIsNone(txt['index']);self.assertFalse((self.out/'index.html').exists())
        html=export_readable(self.db,self.folder/'html_only',formats=('html',))
        self.assertIsNotNone(html['index']);self.assertFalse(list((self.folder/'html_only').glob('*.txt')))

    def test_export_does_not_stop_at_browser_page_limit(self):
        for index in range(120):self.service.create_message(self.a.id,self.b.id,f'unit row {index}',create_time='2026-01-03T00:00:00Z')
        self.assertEqual(self.exporting(user_id=1,peer_id=2)['messages'],122)
        parser=ChatHTML();parser.feed((self.out/'chat_1_2.html').read_text(encoding='utf-8'))
        self.assertEqual(len(parser.articles),122)

    def test_notes_are_exported_as_notes(self):
        self.service.create_message(self.c.id,self.c.id,'自己的笔记',create_time='2026-01-01T00:00:00Z')
        self.exporting(user_id=3,peer_id=3)
        self.assertIn('的笔记',(self.out/'chat_3_3.txt').read_text(encoding='utf-8'))

    def test_legacy_archive_is_read_without_migration(self):
        legacy=self.folder/'legacy.db'
        with sqlite3.connect(legacy) as connection:
            connection.executescript(files('wechat_archive.database').joinpath('init.sql').read_text(encoding='utf-8'))
            connection.execute(f'PRAGMA application_id={APPLICATION_ID}');connection.execute('PRAGMA user_version=1')
            connection.executemany('INSERT INTO users(wxid,nickname) VALUES (?,?)',[('unit_1','一'),('unit_2','二')])
            connection.execute("INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type) VALUES (1,2,'2026-01-01T00:00:00.000000Z','legacy text','text')")
        before=legacy.read_bytes()
        self.assertEqual(export_readable(legacy,self.out)['messages'],1)
        self.assertEqual(legacy.read_bytes(),before)
        self.assertEqual(json.loads((self.out/'manifest.json').read_text(encoding='utf-8'))['database_schema'],1)

    def test_cli_exports_without_initializing_missing_database(self):
        result=subprocess.run([sys.executable,'-m','cli','--db',str(self.db),'export-readable',str(self.out),'--user','1','--peer','2'],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['messages'],2)
        missing=self.folder/'absent.db'
        result=subprocess.run([sys.executable,'-m','cli','--db',str(missing),'export-readable',str(self.folder/'absent_output')],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,1);self.assertFalse(missing.exists())


class ReadableExportWindowTest(unittest.TestCase):
    def test_button_exports_selected_archive_without_source_or_browser(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);database=folder/'archive.db';service=ChatService(database)
            a=service.create_user('unit_a','甲');b=service.create_user('unit_b','乙')
            service.create_message(a.id,b.id,'GUI unit text',create_time='2026-01-01T00:00:00Z')
            root=tk.Tk();root.withdraw();app=ImportWindow(root)
            try:
                app.target.set(str(database));app.source.set('')
                with patch('wechat_archive.ui.import_window.filedialog.askdirectory',return_value=str(folder)),patch('wechat_archive.ui.import_window.webbrowser.open') as browser:
                    app.export_button.invoke()
                    deadline=time.monotonic()+15
                    while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
                    self.assertFalse(app.busy);root.update();browser.assert_not_called()
                outputs=list(folder.glob('聊天导出_*'))
                self.assertEqual(len(outputs),1);self.assertTrue((outputs[0]/'index.html').is_file())
                self.assertIn('可读导出完成',app.status.get())
                self.assertIn('文本消息：1',app.result.get('1.0','end'))
            finally:app.close()
