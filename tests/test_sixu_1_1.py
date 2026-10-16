"""1.1 regressions with generated sources, no private chats or model calls."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image

from test_rich_source import FakeSource
from test_sixu_v1 import RichFixture
from wechat_archive.agent import ArchiveScope,ArchiveTools,CodexClient
from wechat_archive.agent.evidence import evidence_packet
from wechat_archive.importer.rich_importer import create_rich_archive,ready_media,sha_file
from wechat_archive.importer.rich_snapshot import RichSnapshotImporter
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.wechat_source.emoji_cache import EmojiCache
from wechat_archive.wechat_source.rich_source import capture_rich


class EvidenceTests(RichFixture):
    def test_evidence_contains_real_scoped_body_and_citations_without_paths(self):
        self.importer().import_file(self.source)
        scope=ArchiveScope(self.db,1,2)
        packet=json.loads(evidence_packet(ArchiveTools(scope)))['archive_evidence']
        self.assertEqual([x['content'] for x in packet['messages']['items']],['  原文 😀\n第二行  '])
        self.assertTrue(packet['coverage']['complete'])
        self.assertEqual(packet['messages']['items'][0]['citation'],'[消息 #1]')
        self.assertNotIn(str(self.folder),json.dumps(packet))

    def test_per_turn_rpc_input_has_body_even_without_model_tool_dispatch(self):
        self.importer().import_file(self.source);trace=self.folder/'trace.jsonl'
        client=CodexClient(self.folder/'rpc',timeout=5,command=[sys.executable,'-X','utf8','-u',str(Path(__file__).parent/'fake_codex_server.py'),str(trace)])
        try:
            client.start();client.login();client.send('自建测试',ArchiveScope(self.db,1,2))
            for _ in range(500):
                if not client.active:break
                time.sleep(.01)
            rows=[json.loads(x) for x in trace.read_text(encoding='utf-8').splitlines()]
            request=next(x for x in rows if x.get('method')=='turn/start')
            text=request['params']['input'][0]['text']
            self.assertIn('原文 😀',text);self.assertIn('[消息 #1]',text)
            self.assertNotIn('群内本人',text)
        finally:client.close()

    def test_filtered_evidence_and_incomplete_coverage_are_explicit(self):
        self.importer().import_file(self.source);c=self.controller();root=tk.Tk();root.withdraw();app=ApplicationWindow(root,controller=c)
        try:
            app.owner_id=1;app.peer_id=2
            scope=ArchiveScope(self.db,1,2);context=app.agent_panel.ai_service.provider.capture(scope)
            context=replace(context,date_filter=('2026-10-16','2026-10-16'))
            packet=json.loads(evidence_packet(ArchiveTools(scope),context))['archive_evidence']
            self.assertEqual(packet['messages']['items'],[])
            self.assertEqual(packet['filters']['end_time'],'2026-10-17T00:00:00+08:00')
            class Many:
                def execute(self,name,args):
                    if name=='archive_overview':return {'messages':120}
                    return {'total':120,'items':[{'content':'合成片段'}],'offset':args.get('offset',0),'has_more':True}
            packet=json.loads(evidence_packet(Many()))['archive_evidence']
            self.assertFalse(packet['coverage']['complete']);self.assertEqual(packet['coverage']['earlier_omitted'],70)
        finally:app.close()


class DirectMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)

    def test_one_click_source_captures_animated_emoji_and_imports_bytes(self):
        db=FakeSource(self.folder,count=1,shards=1);self.addCleanup(db.close)
        frames=[Image.new('RGB',(24,24),c) for c in ('red','blue')];buffer=io.BytesIO();frames[0].save(buffer,format='GIF',save_all=True,append_images=frames[1:],duration=100,loop=0)
        data=buffer.getvalue();key=hashlib.md5(data).hexdigest()
        cache=Path(db.account_dir)/'cache/emoji';cache.mkdir(parents=True);original=cache/key;original.write_bytes(data)
        conn,table=db.tables[0];conn.execute(f'UPDATE "{table}" SET local_type=47,message_content=?',('<msg><emoji md5="'+key+'"/></msg>',));conn.commit()
        with patch('wechat_archive.wechat_source.media_acquisition.local_media_reader',return_value=None):
            result=capture_rich(db,{'nick_name':'自己'},{'username':db.peer},self.folder/'capture',all_history=True)
        self.assertEqual((result['media_available'],result['media_missing']),(1,0))
        target=self.folder/'archive.db';create_rich_archive(target);report=RichSnapshotImporter(target).import_snapshot(result['output'])
        self.assertEqual(report.success_count,1)
        with sqlite3.connect(target) as conn:conn.row_factory=sqlite3.Row;media=dict(conn.execute('SELECT * FROM media').fetchone())
        self.assertEqual(ready_media(target,media).read_bytes(),data);self.assertEqual(original.read_bytes(),data)
        with Image.open(ready_media(target,media)) as image:self.assertEqual(image.n_frames,2)

    def test_missing_or_mismatched_cache_is_not_fabricated(self):
        account=self.folder/'account';cache=account/'cache/emoji';cache.mkdir(parents=True)
        key='0'*32;(cache/key).write_bytes(b'wrong')
        row={'message_content':'<msg><emoji md5="'+key+'" cdnurl="https://invalid.example/x"/></msg>'}
        self.assertIsNone(EmojiCache(account).acquire(row,self.folder/'output'));self.assertFalse((self.folder/'output').exists())

    def test_pinned_image_reader_writes_inside_requested_output_and_handles_xml(self):
        from wechat_archive.wechat_source.acquisition import _load_sdk
        from wechat_archive.wechat_source.media_acquisition import local_media_reader,acquire_media
        _load_sdk()
        class DB:
            account_dir=str(self.folder/'account');wxid='synthetic_owner'
            def get_message_row(db,*args,**kwargs):
                self.assertEqual(kwargs['shard'],'message_0')
                return {'local_type':3,'content':'<msg><img md5="'+('a'*32)+'"/></msg>'}
        reader=local_media_reader(DB(),self.folder/'assets');raw=io.BytesIO();Image.new('RGB',(30,20),'green').save(raw,format='PNG')
        source=self.folder/'encrypted.dat';source.write_bytes(b'generated')
        row={'local_type':3,'local_id':5,'shard':'message_0'}
        with patch.object(reader,'_image_files',return_value={'mid':(str(source),source.stat().st_size)}),patch.object(reader,'decrypt_image',return_value=raw.getvalue()):
            output=acquire_media(reader,'synthetic_peer',row,self.folder/'assets/one-message')
        self.assertTrue(output.is_relative_to(self.folder/'assets/one-message'));self.assertEqual(output.read_bytes(),raw.getvalue())


class DialogueUITests(RichFixture):
    def app(self):
        self.importer().import_file(self.source);c=self.controller();root=tk.Tk();root.geometry('1240x820');app=ApplicationWindow(root,controller=c);self.addCleanup(app.close)
        root.update();return app

    def test_user_right_codex_left_and_wait_indicator_lifecycle(self):
        app=self.app();panel=app.agent_panel
        panel._add('你','用户问题 😀\n第二行');panel._add('Codex','回答')
        self.assertEqual(panel.transcript.tag_cget('turn_user','justify'),'right');self.assertEqual(panel.transcript.tag_cget('turn_codex','justify'),'left')
        self.assertIn('turn_user',panel.transcript.tag_names('1.0'))
        panel.active=True;panel._controls();app.root.update();self.assertIn('千丝万绪',panel.reply_indicator.get())
        panel.active=False;panel._controls();self.assertEqual(panel.reply_indicator.get(),'');self.assertIsNone(panel.reply_job)
        self.assertNotIn('千丝万绪',panel.conversation_text())

    def test_stream_deltas_render_once_per_poll_and_page_switch_reuses_widgets(self):
        app=self.app();panel=app.agent_panel
        panel._notification('item/agentMessage/delta',{'itemId':'i','delta':'一'})
        with patch.object(panel,'_render',wraps=panel._render) as rendered:
            for _ in range(80):panel._notification('item/agentMessage/delta',{'itemId':'i','delta':'二'})
            self.assertEqual(rendered.call_count,0)
        panel._render();self.assertIn('一'+'二'*80,panel.transcript.get('1.0','end'))
        app.show_page('帮助');app.show_page('聊天归档');app.root.update();controls=tuple(str(x) for x in app.descendants(app.root))
        with patch.object(app.localizer,'apply',wraps=app.localizer.apply) as localize:
            for _ in range(4):app.show_page('帮助');app.show_page('聊天归档')
            self.assertEqual(localize.call_count,0)
        self.assertEqual(controls,tuple(str(x) for x in app.descendants(app.root)))
