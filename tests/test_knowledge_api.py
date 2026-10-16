import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from wechat_archive import ChatService
from wechat_archive.agent import ArchiveScope
from wechat_archive.knowledge import KnowledgeSource
from wechat_archive.knowledge.api import KnowledgeAPI
from wechat_archive.knowledge.index import KnowledgeIndex
from wechat_archive.knowledge.providers import LexicalEmbedding


class KnowledgeAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name); self.path=self.folder/'archive.db'; self.service=ChatService(self.path)
        for i in range(3): self.service.create_user(wxid=f'fixture_{i}',nickname=f'测试身份{i}')
        for peer,text in ((2,'晶界偏聚能计算需要总能量'),(3,'禁止读取')):
            self.service.create_message(sender_id=1,receiver_id=peer,content=text,create_time='2026-10-14T00:00:00Z')
        self.source=KnowledgeSource(ArchiveScope(self.path,1,2)); self.api=KnowledgeAPI(self.source)
        self.index=KnowledgeIndex(self.folder/'index.db',self.source,LexicalEmbedding())

    def request(self,name,params=None,**extra):
        return self.api.dispatch({'version':'1.0','id':'test','method':name,'params':params or {},**extra})

    def test_capabilities_only_actual_read_methods_and_no_paths(self):
        result=self.request('capabilities'); self.assertTrue(result['ok'])
        self.assertEqual(result['result']['methods'],['capabilities','chunks','resolve'])
        self.assertNotIn(str(self.path),json.dumps(result))
        self.assertFalse(self.request('search',{'query':'晶界'})['ok'])

    def test_reference_roundtrip_scope_and_read_only(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        item=self.request('chunks')['result']['items'][0]
        self.assertEqual(self.request('resolve',{'reference':item['reference']})['result'],item)
        self.assertNotIn('禁止读取',json.dumps(self.request('chunks'),ensure_ascii=False))
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_version_args_id_and_arbitrary_plugin_or_sql_rejected(self):
        for value in ({'version':'2.0'},{'id':True},{'id':[]},{'params':{'path':str(self.path)}},{'extra':1},
                      {'method':'delete_message'},{'method':'run_plugin'},{'params':{'sql':'SELECT * FROM messages'}}):
            self.assertFalse(self.request('capabilities',**value)['ok'])
        self.assertFalse(self.api.dispatch(None)['ok'])

    def test_error_after_change_and_delete(self):
        ref=self.request('chunks')['result']['items'][0]['reference']
        self.service.update_message(1,content='changed')
        self.assertEqual(self.request('resolve',{'reference':ref})['error']['code'],'conflict')
        self.service.delete_message(1)
        self.assertEqual(self.request('resolve',{'reference':ref})['error']['code'],'not_found')

    def test_index_search_is_read_only(self):
        self.index.sync(); self.api=KnowledgeAPI(self.source,self.index)
        before=hashlib.sha256(self.index.path.read_bytes()).hexdigest()
        self.assertTrue(self.request('status')['result']['ready'])
        self.assertEqual(self.request('search',{'query':'晶界偏聚能'})['result']['hits'][0]['chunk']['reference']['message']['message_id'],1)
        self.assertEqual(before,hashlib.sha256(self.index.path.read_bytes()).hexdigest())

    def test_jsonlines_malformed_then_valid_and_budget(self):
        request=json.dumps({'version':'1.0','id':1,'method':'capabilities','params':{}})
        output=io.StringIO(); self.assertEqual(self.api.serve(io.StringIO('bad\n'+request+'\n'),output),0)
        rows=[json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual([r['ok'] for r in rows],[False,True])
        output=io.StringIO(); self.assertEqual(self.api.serve(io.StringIO('x'*65537+'\n'),output),2)
        self.assertFalse(json.loads(output.getvalue())['ok'])

    def cli(self,*args,input=None):
        result=subprocess.run([sys.executable,'-B','-X','utf8','-m','wechat_archive','--db',str(self.path),
            'knowledge','--user','1','--peer','2',*args],input=input,text=True,encoding='utf-8',capture_output=True,timeout=15)
        return result

    def test_cli_build_search_and_stdio_second_client(self):
        index_args=('--index',str(self.index.path))
        result=self.cli(*index_args,'build'); self.assertEqual(result.returncode,0,result.stderr)
        result=self.cli(*index_args,'search','晶界偏聚能'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['hits']),1)
        request=json.dumps({'version':'1.0','id':7,'method':'chunks','params':{}})+'\n'
        result=self.cli('api',input=request); self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertFalse(self.cli('ask','question').returncode==0)

    def test_cli_requires_existing_explicit_archive_does_not_initialize(self):
        missing=self.folder/'missing.db'
        result=subprocess.run([sys.executable,'-B','-X','utf8','-m','wechat_archive','--db',str(missing),
            'knowledge','--user','1','capabilities'],capture_output=True,timeout=15)
        self.assertNotEqual(result.returncode,0); self.assertFalse(missing.exists())
        result=subprocess.run([sys.executable,'-B','-X','utf8','-m','wechat_archive','knowledge','--user','1','capabilities'],capture_output=True,timeout=15)
        self.assertNotEqual(result.returncode,0)


if __name__=='__main__': unittest.main()
