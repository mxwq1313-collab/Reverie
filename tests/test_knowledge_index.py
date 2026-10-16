import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from wechat_archive import ChatService, ConflictError, NotFoundError, ValidationError
from wechat_archive.agent import ArchiveScope
from wechat_archive.knowledge import KnowledgeSource
from wechat_archive.knowledge.index import KnowledgeIndex
from wechat_archive.knowledge.providers import LexicalEmbedding, OllamaEmbedding, OllamaEndpoint, unit_vector


class CountingEmbedding(LexicalEmbedding):
    def __init__(self): self.count=0; self.fail=False; self.action=None
    def embed(self,texts):
        self.count+=len(texts)
        if self.action:
            action,self.action=self.action,None; action()
        if self.fail: raise ConflictError('fixture failure')
        return super().embed(texts)


class KnowledgeIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'archive.db'; self.service=ChatService(self.path)
        for i in range(3): self.service.create_user(wxid=f'test_{i}',nickname=f'用户{i}')
        for receiver,text in [(2,'晶界偏聚能的计算方法'),(2,'周末咖啡馆见面'),(3,'不授权的晶界数据')]:
            self.service.create_message(sender_id=1,receiver_id=receiver,content=text,create_time='2026-10-14T00:00:00Z')
        self.source=KnowledgeSource(ArchiveScope(self.path,1,2)); self.provider=CountingEmbedding()
        self.index=KnowledgeIndex(self.path.with_name('index.db'),self.source,self.provider)

    def test_build_search_and_original_unchanged(self):
        original=hashlib.sha256(self.path.read_bytes()).hexdigest(); result=self.index.sync()
        self.assertEqual((result['embedded'],result['reused']),(2,0))
        found=self.index.search('晶界偏聚能',limit=1)['hits'][0]
        self.assertEqual(found['chunk']['reference']['message']['message_id'],1)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),original)
        self.assertTrue(self.index.status()['ready'])

    def test_incremental_reuse_update_and_delete(self):
        self.index.sync(); self.assertEqual(self.index.sync()['reused'],2); self.assertEqual(self.provider.count,2)
        self.service.update_message(1,content='晶界结合能方法'); self.service.delete_message(2)
        self.assertFalse(self.index.status()['ready'])
        with self.assertRaises(ConflictError): self.index.search('晶界')
        result=self.index.sync(); self.assertEqual((result['chunks'],result['embedded'],result['deleted']),(1,1,2))

    def test_failure_cancel_and_mutation_preserve_previous_index(self):
        self.index.sync(); before=hashlib.sha256(self.index.path.read_bytes()).hexdigest()
        self.service.update_message(1,content='新内容'); self.provider.fail=True
        with self.assertRaises(ConflictError): self.index.sync()
        self.assertEqual(before,hashlib.sha256(self.index.path.read_bytes()).hexdigest())
        self.provider.fail=False
        with self.assertRaises(ConflictError): self.index.sync(cancel=lambda:True)
        self.assertEqual(before,hashlib.sha256(self.index.path.read_bytes()).hexdigest())
        self.provider.action=lambda:self.service.update_message(1,content='生成中发生变化')
        with self.assertRaises(ConflictError): self.index.sync()
        self.assertEqual(before,hashlib.sha256(self.index.path.read_bytes()).hexdigest())

    def test_wrong_scope_original_target_processing_and_rebuild(self):
        self.index.sync()
        other=KnowledgeIndex(self.index.path,KnowledgeSource(ArchiveScope(self.path,1)),self.provider)
        with self.assertRaises(ConflictError): other.search('晶界')
        with self.assertRaises(ConflictError): other.sync()
        with self.assertRaises(ValidationError): KnowledgeIndex(self.path,self.source,self.provider)
        self.assertEqual(self.index.sync(rebuild=True)['embedded'],2)
        altered=KnowledgeIndex(self.index.path,KnowledgeSource(ArchiveScope(self.path,1,2),64,0),self.provider)
        with self.assertRaises(ConflictError): altered.search('晶界')
        self.assertEqual(altered.sync()['embedded'],2)

    def test_missing_unknown_and_corrupt_index(self):
        with self.assertRaises(NotFoundError): self.index.search('晶界')
        self.index.path.write_bytes(b'unknown bytes'); before=self.index.path.read_bytes()
        with self.assertRaises(ConflictError): self.index.sync()
        self.assertEqual(before,self.index.path.read_bytes())

    def test_tampered_vector_payload_trigger_fail_closed(self):
        self.index.sync()
        connection=sqlite3.connect(self.index.path)
        try:
            connection.execute("UPDATE chunks SET vector=x'0000'"); connection.commit()
        finally: connection.close()
        with self.assertRaises(ConflictError): self.index.search('晶界',min_score=0)
        self.index.sync(rebuild=True); connection=sqlite3.connect(self.index.path)
        try:
            row=connection.execute('SELECT id,payload FROM chunks LIMIT 1').fetchone()
            item=json.loads(row[1]); item['text']='伪造'
            connection.execute('UPDATE chunks SET payload=? WHERE id=?',(json.dumps(item),row[0])); connection.commit()
        finally: connection.close()
        with self.assertRaises(ConflictError): self.index.search('晶界',min_score=0)
        connection=sqlite3.connect(self.index.path)
        try:
            connection.execute('CREATE TRIGGER forbidden AFTER INSERT ON chunks BEGIN DELETE FROM chunks; END'); connection.commit()
        finally: connection.close()
        with self.assertRaises(ConflictError): self.index.sync()

    def test_empty_and_invalid_search(self):
        empty=KnowledgeIndex(self.path.with_name('empty.db'),KnowledgeSource(ArchiveScope(self.path,2,3)),self.provider)
        self.assertEqual(empty.sync()['chunks'],0); self.assertEqual(empty.search('没有')['hits'],[])
        for query in ('','x'*1001,'\0'):
            with self.assertRaises(ValidationError): self.index.search(query)
        for options in ({'limit':True},{'limit':21},{'min_score':float('nan')},{'min_score':1.1}):
            with self.assertRaises(ValidationError): self.index.search('晶界',**options)


class OllamaProviderTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]; self.vectors=[[3,4]]
        self.models=[{'name':'fixture:local','digest':'a'*64},{'name':'fixture:cloud','digest':'b'*64,'remote_host':'cloud.invalid'}]
        parent=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                parent.requests.append((self.path,None)); self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'models':parent.models}).encode())
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length']))); parent.requests.append((self.path,data))
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({'embeddings':parent.vectors}).encode())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.endpoint=OllamaEndpoint(f'http://127.0.0.1:{self.server.server_port}',timeout=2)

    def test_http_protocol_with_synthetic_model_server(self):
        provider=OllamaEmbedding(self.endpoint,'fixture:local'); self.assertEqual(provider.embed(['原文']),[[0.6,0.8]])
        self.assertEqual(provider.descriptor()['dimensions'],2)
        self.assertEqual(next(data for route,data in self.requests if route=='/api/embed')['truncate'],False)
        self.assertFalse(any(route=='/api/pull' for route,_ in self.requests))

    def test_cloud_missing_and_changed_model_refused(self):
        self.assertEqual(len(self.endpoint.models()),1)
        with self.assertRaises(ConflictError): OllamaEmbedding(self.endpoint,'fixture:cloud').descriptor()
        provider=OllamaEmbedding(self.endpoint,'fixture:local'); provider.descriptor(); self.models[0]['digest']='c'*64
        with self.assertRaises(ConflictError): provider.descriptor()

    def test_invalid_vector_response(self):
        for response in ([],[[float('nan'),1]],[[0,0]],[[1,2],[1,2]]):
            self.vectors=response
            with self.assertRaises(ValidationError): OllamaEmbedding(self.endpoint,'fixture:local').embed(['text'])

    def test_loopback_only_and_deterministic_labelled_offline(self):
        for url in ('https://127.0.0.1','http://example.com','http://127.0.0.1/path','http://user@localhost','http://127.0.0.1?x=1'):
            with self.assertRaises(ValidationError): OllamaEndpoint(url)
        self.assertEqual(OllamaEndpoint('http://localhost:11434').host,'127.0.0.1')
        provider=LexicalEmbedding(); self.assertEqual(provider.embed(['Fe 晶界']),provider.embed(['Fe 晶界']))
        self.assertEqual(provider.descriptor()['kind'],'lexical')
        for vector in ([True,1],[float('inf'),1],[],[0,0]):
            with self.assertRaises(ValidationError): unit_vector(vector)

if __name__=='__main__': unittest.main()
