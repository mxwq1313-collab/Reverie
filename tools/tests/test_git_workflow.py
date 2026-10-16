"""本地临时仓库验证；不访问网络、不测试用户私有资料。"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('git_privacy_check',ROOT/'tools/git_privacy_check.py')
GUARD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(GUARD)


class GitWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.repo=Path(self.temp.name)/'repo';self.repo.mkdir()
        self.call('init','--initial-branch=main');self.call('config','core.autocrlf','false')

    def call(self,*args):
        result=subprocess.run(['git','-C',str(self.repo),*args],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'));return result.stdout

    def stage(self,name,data):
        target=self.repo/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        self.call('add','--',name)

    def test_regular_source_is_accepted(self):
        self.stage('app.py',b'print("unit")\n');self.assertEqual(GUARD.scan(self.repo)['findings'],[])

    def test_databases_credentials_and_artifacts_are_rejected(self):
        for name in ('data/chat.db','other/archive.sqlite3','auth.json','.env','secrets/key.txt','dist/app.exe'):
            self.stage(name,b'unit');self.assertTrue(any(item['path']==name for item in GUARD.scan(self.repo)['findings']))

    def test_already_indexed_private_file_is_not_hidden_by_ignore(self):
        self.stage('data/chat.db',b'unit');self.stage('.gitignore',b'data/\n')
        self.assertTrue(any(item['path']=='data/chat.db' for item in GUARD.scan(self.repo)['findings']))

    def test_scanner_reads_staged_blob_instead_of_safe_worktree(self):
        self.stage('config.txt',('sk-proj-'+'a'*40).encode());(self.repo/'config.txt').write_text('safe working tree',encoding='utf-8')
        self.assertTrue(any(item['reason']=='API 密钥' for item in GUARD.scan(self.repo)['findings']))

    def test_sensitive_value_is_not_printed(self):
        token='sk-proj-'+'b'*40;self.stage('config.txt',token.encode())
        result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/git_privacy_check.py'),'--repo',str(self.repo),'--staged'],capture_output=True)
        self.assertEqual(result.returncode,1);self.assertNotIn(token.encode(),result.stdout+result.stderr)

    def test_unreviewed_chat_export_is_rejected(self):
        self.stage('sample.json',json.dumps({'format':'chat-exchange','users':[],'messages':[]}).encode())
        self.assertTrue(any(item['reason']=='未登记的聊天/来源样例' for item in GUARD.scan(self.repo)['findings']))

    def test_schema_mapping_is_not_mistaken_for_chat_export(self):
        self.stage('schema.json',json.dumps({'messages':{'columns':{'content':'content'}}}).encode())
        self.assertEqual(GUARD.scan(self.repo)['findings'],[])

    def test_worktree_policy_cannot_approve_staged_export(self):
        data=json.dumps({'format':'chat-exchange','messages':[]}).encode();self.stage('examples/unit.json',data)
        policy=self.repo/'tools/privacy_fixtures.json';policy.parent.mkdir(parents=True);policy.write_text(json.dumps({'synthetic_files':{'examples/unit.json':hashlib.sha256(data).hexdigest()}}),encoding='utf-8')
        self.assertTrue(GUARD.scan(self.repo)['findings'])

    def test_indexed_reviewed_synthetic_sample_is_allowed(self):
        data=json.dumps({'format':'chat-exchange','messages':[]}).encode();self.stage('examples/unit.json',data)
        self.stage('tools/privacy_fixtures.json',json.dumps({'synthetic_files':{'examples/unit.json':hashlib.sha256(data).hexdigest()}}).encode())
        self.assertEqual(GUARD.scan(self.repo)['findings'],[])

    def test_policy_cannot_allow_database(self):
        data=b'unit';self.stage('examples/never.db',data)
        self.stage('tools/privacy_fixtures.json',json.dumps({'synthetic_files':{'examples/never.db':hashlib.sha256(data).hexdigest()}}).encode())
        self.assertTrue(any(item['path']=='examples/never.db' for item in GUARD.scan(self.repo)['findings']))

    def test_modified_sample_requires_new_review(self):
        old=json.dumps({'format':'chat-exchange','messages':[]}).encode();self.stage('examples/unit.json',old+b' ')
        self.stage('tools/privacy_fixtures.json',json.dumps({'synthetic_files':{'examples/unit.json':hashlib.sha256(old).hexdigest()}}).encode())
        self.assertTrue(GUARD.scan(self.repo)['findings'])

    def test_actual_commit_hook_blocks_sensitive_content(self):
        self.call('config','user.name','Synthetic Test');self.call('config','user.email','unit@localhost')
        hooks=self.repo/'.githooks';hooks.mkdir();shutil.copy2(ROOT/'.githooks/pre-commit',hooks/'pre-commit')
        tools=self.repo/'tools';tools.mkdir();shutil.copy2(ROOT/'tools/git_privacy_check.py',tools/'git_privacy_check.py')
        self.call('config','core.hooksPath','.githooks');self.stage('config.txt',('sk-proj-'+'c'*40).encode())
        result=subprocess.run(['git','-C',str(self.repo),'commit','-m','本地负例，不应产生提交'],capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotEqual(subprocess.run(['git','-C',str(self.repo),'rev-parse','--verify','HEAD'],capture_output=True).returncode,0)

    def test_push_hook_blocks_without_any_network(self):
        shell=shutil.which('sh') or r'C:\Program Files\Git\bin\bash.exe'
        env=dict(os.environ);env.pop('WECHAT_ARCHIVE_APPROVED_PUSH',None)
        result=subprocess.run([shell,str(ROOT/'.githooks/pre-push'),'unused','unused'],input=b'',env=env,capture_output=True)
        self.assertEqual(result.returncode,1)

    def test_fixture_bootstrap_creates_only_synthetic_data(self):
        target=self.repo/'tools';target.mkdir();shutil.copy2(ROOT/'tools/prepare_fixtures.py',target/'prepare_fixtures.py')
        tests=self.repo/'tests';tests.mkdir();shutil.copy2(ROOT/'tests/android_fixture.py',tests/'android_fixture.py')
        command=[sys.executable,'-X','utf8',str(target/'prepare_fixtures.py')]
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
        database=self.repo/'android_mock/MicroMsg/mock-account-001/EnMicroMsg.db';before=database.read_bytes()
        self.assertTrue(json.loads(database.with_name('android_source.json').read_text(encoding='utf-8'))['simulation'])
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,0);self.assertEqual(database.read_bytes(),before)

    def test_fixture_bootstrap_does_not_overwrite_partial_directory(self):
        target=self.repo/'tools';target.mkdir();shutil.copy2(ROOT/'tools/prepare_fixtures.py',target/'prepare_fixtures.py')
        partial=self.repo/'android_mock/MicroMsg/mock-account-001';partial.mkdir(parents=True);marker=partial/'android_source.json';marker.write_text('preserve',encoding='utf-8')
        result=subprocess.run([sys.executable,'-X','utf8',str(target/'prepare_fixtures.py')],capture_output=True)
        self.assertEqual(result.returncode,1);self.assertEqual(marker.read_text(encoding='utf-8'),'preserve')
