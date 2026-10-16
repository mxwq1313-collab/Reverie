"""Selected source projections use synthetic registered SQLite shards only."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from wechat_archive.errors import ConflictError
from wechat_archive.importer.rich_importer import create_rich_archive
from wechat_archive.importer.rich_snapshot import RichSnapshotImporter
from wechat_archive.wechat_source.rich_source import capture_rich,contacts_with_groups


class FakeSource:
    wxid='synthetic_owner'
    peer='synthetic_group@chatroom'
    def __init__(self,folder,*,count=5,shards=2,unknown=False):
        self.account_dir=str(folder/'account');Path(self.account_dir).mkdir();self.tables=[];self.labels={}
        self.table='Msg_'+hashlib.md5(self.peer.encode()).hexdigest()
        for shard in range(shards):
            conn=sqlite3.connect(folder/f'shard_{shard}.db');conn.row_factory=sqlite3.Row
            conn.execute('CREATE TABLE Name2Id(user_name TEXT)');conn.executemany('INSERT INTO Name2Id VALUES (?)',[(self.wxid,),('synthetic_peer',)])
            conn.execute(f'CREATE TABLE "{self.table}"(local_id INTEGER PRIMARY KEY,local_type INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content,source,packed_info_data,compress_content,server_id INTEGER,sort_seq INTEGER)')
            conn.executemany(f'INSERT INTO "{self.table}" VALUES (?,?,?,?,?,?,?,?,?,?)',[(i,777 if unknown and i==count else 1,1 if i%2 else 2,1767225600+i*shards+shard,'原文 '+str(i),None,None,None,10000+shard*count+i,i*shards+shard) for i in range(1,count+1)])
            conn.commit();self.tables.append((conn,self.table));self.labels[id(conn)]='message_'+str(shard)
    def _shard_label(self,conn):return self.labels[id(conn)]
    def _run_msg_query(self,peer,fn):
        if peer!=self.peer:return None
        return fn(self.tables)
    def get_group_members(self,peer):return [{'username':self.wxid,'nick_name':'自己'},{'username':'synthetic_peer','nick_name':'伙伴'}]
    def get_nickname(self,peer):return peer
    def _friendly_content(self,body,kind):return body.decode('utf-8')
    def _msg_type_name(self,code):return str(code)
    def close(self):
        for conn,_ in self.tables:conn.close()


class RichSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
    def source(self,**kwargs):
        value=FakeSource(self.folder,**kwargs);self.addCleanup(value.close);return value
    def capture(self,db,name='snapshot',**kwargs):
        with patch('wechat_archive.wechat_source.media_acquisition.local_media_reader',return_value=None):
            return capture_rich(db,{'nick_name':'自己'},{'username':db.peer,'nick_name':'自建群聊'},self.folder/name,**kwargs)

    def test_recent_is_global_across_shards_and_counts_include_members(self):
        db=self.source(count=5,shards=2)
        rows=contacts_with_groups(db,[{'username':db.peer,'nick_name':'自建群聊'}]);self.assertEqual(rows[0]['message_count'],10);self.assertEqual(rows[0]['own_count'],6)
        self.assertEqual(sum(x['message_count'] for x in rows[0]['members']),10)
        result=self.capture(db,limit=3);self.assertEqual(result['records'],3)
        manifest=json.loads((Path(result['output'])/'rich_snapshot.json').read_text(encoding='utf-8'));self.assertEqual(manifest['typed_records'],3)
        payload=json.loads((Path(result['output'])/manifest['batches'][0]['file']).read_text(encoding='utf-8'))
        self.assertEqual([x['content'] for x in payload['messages']],['原文 5','原文 5','原文 4'])
        conn,table=db.tables[1];conn.execute(f'UPDATE "{table}" SET server_id=-1 WHERE local_id=5');conn.commit()
        other=self.capture(db,name='local-id-fallback',limit=1);data=json.loads((Path(other['output'])/'batch_000000.json').read_text(encoding='utf-8'))
        self.assertEqual(json.loads(data['messages'][0]['id'])[1:],['local','5'])

    def test_all_history_batch_resume_deduplicates_and_retains_unknown(self):
        db=self.source(count=603,shards=2,unknown=True);result=self.capture(db,all_history=True)
        target=self.folder/'archive.db';create_rich_archive(target);importer=RichSnapshotImporter(target)
        report=importer.import_snapshot(result['output']);self.assertEqual((report.success_count,report.failed_count),(1206,0));self.assertEqual(report.status,'success')
        repeat=importer.import_snapshot(result['output']);self.assertEqual(repeat.duplicated_count,1206)
        with sqlite3.connect(target) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1206)

    def test_cancelled_before_import_and_changed_batch_are_explicit(self):
        db=self.source();result=self.capture(db,all_history=True);target=self.folder/'archive.db';create_rich_archive(target)
        cancel=threading.Event();cancel.set();report=RichSnapshotImporter(target).import_snapshot(result['output'],cancel_event=cancel);self.assertEqual(report.success_count,0);self.assertEqual(report.status,'partial')
        folder=Path(result['output']);batch=next(folder.glob('batch_*.json'));batch.write_text('{}',encoding='utf-8')
        with self.assertRaises(ConflictError):RichSnapshotImporter(target).import_snapshot(folder)

    def test_capture_guard_never_publishes_unstable_source(self):
        db=self.source()
        def changed():raise ConflictError('synthetic source changed')
        with self.assertRaises(ConflictError):self.capture(db,guard=changed)
        self.assertFalse((self.folder/'snapshot').exists())
        import zstandard
        conn,table=db.tables[0]
        conn.execute(f'UPDATE "{table}" SET message_content=? WHERE local_id=1',(b'\xff\xfe\x00',))
        conn.execute(f'UPDATE "{table}" SET message_content=? WHERE local_id=5',(zstandard.ZstdCompressor().compress('压缩原文 😀'.encode('utf-8')),));conn.commit()
        result=self.capture(db,name='verified-text',all_history=True);directory=Path(result['output']);manifest=json.loads((directory/'rich_snapshot.json').read_text(encoding='utf-8'))
        rows=[]
        for batch in manifest['batches']:rows.extend(json.loads((directory/batch['file']).read_text(encoding='utf-8'))['messages'])
        self.assertEqual(sum(x['kind']=='system' for x in rows),1);self.assertTrue(any(x['content']=='压缩原文 😀' for x in rows))
