"""协议边界的自建单元数据；真实验收另见手动记录，不把本文件当真实成功。"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wechat_archive import ChatService
from wechat_archive.importer.validator import DocumentError,validate_document
from wechat_archive.wechat_adapter.external_adapter import ExternalExportAdapter
from wechat_archive.wechat_adapter import WeChatImporter,detect_source
from wechat_archive.ui.import_controller import ImportController
from wechat_archive.wechat_source.acquisition import capture_private,run_worker

ROOT=Path(__file__).resolve().parents[1]


def record(local,sender,time,content,shard='message_0',kind=1):
    raw={'local_id':local,'local_type':kind,'server_id':1000+local,'sender_username':sender,'create_time':time,'content':content,'sort_seq':local,'shard':shard}
    return {'local_id':local,'source_database':shard,'source_message_id':str(1000+local),'source_id_kind':'server',
            'sender_wxid':sender,'timestamp':time,'content':content,'raw_type':kind,'raw_payload':{'native':{},'database_row':raw}}


def data():
    return {'format':'wechat-external-export','format_version':'1.0','source_platform':'wechat',
            'provider':{'name':'wechatauto-replica','version':'1.2.6.1','api':'WeChatDB.get_messages+get_message_row','distribution_sha256':'0'*64},
            'account':{'wxid':'wxid_unit_owner','nickname':'测试自己','verification':'contact_row'},
            'conversation':{'wxid':'wxid_unit_peer','nickname':'测试对方','kind':'private'},'timestamp_unit':'unix_seconds',
            'capture':{'origin':'unit_test_only','client_version':'unit_test','captured_at':'2026-01-01T00:00:00Z','validated_database_keys':0,'key_cache_written':False},
            'records':[record(2,'wxid_unit_peer',1767225660,'收到'),record(1,'wxid_unit_owner',1767225600,'你好')]}


class ExternalSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.file=self.folder/'native_export.json';self.db=self.folder/'archive.db';self.logs=self.folder/'logs'

    def write(self,payload):
        self.file.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');return self.file

    def load(self,payload):return ExternalExportAdapter().load(self.write(payload))

    def importing(self,payload,**options):return WeChatImporter(self.db,report_dir=self.logs,**options).import_file(self.write(payload))

    def test_known_marker_is_candidate(self):
        self.write(data());found=detect_source(self.file)
        self.assertEqual(found.kind,'external');self.assertTrue(found.supported)

    def test_adapter_returns_valid_standard_document(self):
        payload=self.load(data()).payload
        self.assertEqual(validate_document(payload).issues,[])
        self.assertEqual((len(payload['users']),len(payload['chats']),len(payload['messages'])),(2,1,2))

    def test_direction_uses_wxid_not_sender_number_or_nickname(self):
        row=data();row['account']['nickname']=row['conversation']['nickname']='同名'
        doc=self.load(row).payload
        self.assertEqual((doc['messages'][0]['sender_id'],doc['messages'][0]['receiver_id']),('wxid_unit_owner','wxid_unit_peer'))
        self.assertTrue(doc['users'][0]['external_id'].startswith('wechat:wxid_unit_owner:'))

    def test_utc_time_is_from_original_unix_seconds(self):
        self.assertEqual(self.load(data()).payload['messages'][0]['timestamp'],'2026-01-01T00:00:00.000000Z')

    def test_original_whitespace_and_unicode_preserved(self):
        row=data();text='  中文🙂\n原文  ';row['records'][1]['content']=text;row['records'][1]['raw_payload']['database_row']['content']=text
        self.assertEqual(self.load(row).payload['messages'][0]['content'],text)

    def test_source_id_contains_account_chat_shard_and_kind(self):
        message=self.load(data()).payload['messages'][0]
        composite=json.loads(message['source_id'])
        self.assertEqual(composite,['wxid_unit_owner','wxid_unit_peer','message_0','server','1001'])

    def test_reused_local_id_in_another_shard_is_distinct(self):
        row=data();extra=record(1,'wxid_unit_owner',1767225720,'另一条',shard='message_1');row['records'].append(extra)
        doc=self.load(row).payload
        self.assertEqual(len({m['id'] for m in doc['messages']}),3)

    def test_unknown_type_is_retained_not_silently_dropped(self):
        row=data();row['records'].append(record(3,'wxid_unit_owner',1767225720,'原始未知',kind=777))
        report=self.importing(row)
        details=report.source_metadata['metadata']['external_parse']
        self.assertEqual((report.success_count,details['quarantined_count']),(2,1))
        self.assertEqual(details['quarantine_records'][0]['raw_type'],777)
        self.assertTrue(details['quarantine_records'][0]['raw_payload'])
        self.assertTrue(any(w.code=='external_records_retained' for w in report.warnings))

    def test_all_unknown_rows_fail_and_are_still_retained(self):
        row=data();row['records']=[record(1,'wxid_unit_owner',1767225600,'unknown',kind=777)]
        report=self.importing(row)
        self.assertEqual(report.status,'failed');self.assertFalse(self.db.exists())
        self.assertEqual(report.source_metadata['metadata']['external_parse']['quarantined_count'],1)

    def test_strict_rejects_quarantine_without_db(self):
        row=data();row['records'].append(record(3,'wxid_unit_owner',1767225720,'image',kind=3))
        report=self.importing(row,strict=True)
        self.assertEqual(report.status,'failed');self.assertFalse(self.db.exists())

    def test_unknown_sender_retained(self):
        row=data();row['records'][0]['sender_wxid']='missing'
        doc=self.load(row).payload
        self.assertEqual(doc['source']['metadata']['external_parse']['quarantine_records'][0]['parse_status'],'unknown_sender')

    def test_invalid_unhashable_sender_and_kind_are_retained(self):
        for key in ('sender_wxid','source_id_kind'):
            row=data();row['records'][0][key]=[]
            with self.subTest(key=key):self.assertEqual(len(self.load(row).payload['messages']),1)

    def test_missing_stable_account_not_inferred_from_nickname(self):
        row=data();row['account']['wxid']=''
        with self.assertRaises(DocumentError):self.load(row)

    def test_unknown_tool_version_rejected(self):
        row=data();row['provider']['version']='unknown'
        self.assertEqual(self.importing(row).status,'failed');self.assertFalse(self.db.exists())

    def test_unknown_exchange_version_rejected(self):
        row=data();row['format_version']='2.0'
        with self.assertRaises(DocumentError):self.load(row)

    def test_bare_legacy_export_not_guessed(self):
        with self.assertRaises(DocumentError):self.load({'wxid':'x','messages':[]})

    def test_group_rejected(self):
        row=data();row['conversation']['wxid']='room@chatroom';row['conversation']['kind']='group'
        with self.assertRaises(DocumentError):self.load(row)

    def test_time_unit_not_guessed(self):
        row=data();row['timestamp_unit']='milliseconds'
        with self.assertRaises(DocumentError):self.load(row)

    def test_invalid_time_retained(self):
        row=data();row['records'][0]['timestamp']=True
        self.assertEqual(len(self.load(row).payload['messages']),1)

    def test_database_raw_evidence_mismatch_retained(self):
        row=data();row['records'][0]['raw_payload']['database_row']['sender_username']='other'
        meta=self.load(row).payload['source']['metadata']['external_parse']
        self.assertEqual(meta['quarantined_count'],1)

    def test_binary_placeholder_not_accepted_as_real_text(self):
        row=data();row['records'][0]['raw_payload']['database_row']['content']={'encoding':'base64','data':'AA=='}
        meta=self.load(row).payload['source']['metadata']['external_parse']
        self.assertEqual(meta['quarantine_records'][0]['parse_status'],'unsupported_text_storage')

    def test_same_source_id_conflict_rejected(self):
        row=data();extra=copy.deepcopy(row['records'][1]);extra['content']='不同';extra['raw_payload']['database_row']['content']='不同';row['records'].append(extra)
        with self.assertRaises(DocumentError):self.load(row)

    def test_same_time_content_distinct_source_id_is_not_silently_merged(self):
        row=data();row['records'].append(record(3,'wxid_unit_owner',1767225600,'你好'))
        report=self.importing(row)
        self.assertEqual(report.status,'success')
        self.assertEqual((report.success_count,report.duplicated_count),(3,0))

    def test_exact_duplicate_source_record_is_retained_once(self):
        row=data();row['records'].append(copy.deepcopy(row['records'][1]))
        report=self.importing(row)
        self.assertEqual(report.success_count,2)
        self.assertEqual(report.source_metadata['metadata']['external_parse']['quarantined_count'],1)

    def test_import_and_repeat_use_existing_dedup(self):
        first=self.importing(data());second=WeChatImporter(self.db,report_dir=self.logs).import_file(self.file)
        self.assertEqual((first.success_count,second.success_count,second.duplicated_count),(2,0,2))
        self.assertEqual(ChatService(self.db).stats(),{'users':2,'messages':2})

    def test_source_file_bytes_preserved(self):
        self.write(data());before=self.file.read_bytes();WeChatImporter(self.db,report_dir=self.logs).import_file(self.file)
        self.assertEqual(before,self.file.read_bytes())

    def test_source_target_collision_rejected(self):
        self.write(data());before=self.file.read_bytes()
        report=WeChatImporter(self.file,report_dir=self.logs).import_file(self.file)
        self.assertEqual(report.status,'failed');self.assertEqual(before,self.file.read_bytes())

    def test_source_read_is_bounded(self):
        self.write(data())
        with patch('wechat_archive.wechat_source.parser.file_stamp',return_value=(70*1024*1024,0,0)):
            with self.assertRaises(DocumentError):ExternalExportAdapter().load(self.file)

    def test_duplicate_json_keys_rejected(self):
        self.file.write_text('{"format":"x","format":"y"}',encoding='utf-8')
        with self.assertRaises(DocumentError):ExternalExportAdapter().load(self.file)

    def test_controller_auto_imports_external_marker(self):
        payload=data();payload['records'].append(record(3,'wxid_unit_owner',1767225720,'未支持原记录',kind=777))
        self.write(payload);controller=ImportController(report_dir=self.logs)
        preview=controller.preview(self.file,self.db)
        self.assertEqual(preview['messages'],2)
        self.assertEqual(preview['retained'],1)
        self.assertEqual(preview['issues'],[])
        with self.assertRaises(DocumentError) as strict:
            controller.preview(self.file,self.db,strict=True)
        self.assertIn('严格模式',str(strict.exception))
        self.assertEqual(strict.exception.source_metadata['metadata']['external_parse']['quarantined_count'],1)
        self.assertFalse(self.db.exists())
        self.assertEqual(controller.import_data(self.file,self.db)[0].success_count,2)

    def test_layer_one_import_does_not_require_adapter_initialization(self):
        result=subprocess.run([sys.executable,'-c','import wechat_archive.wechat_source.acquisition; print("ok")'],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('ok',result.stdout)

    def test_acquisition_preserves_existing_output(self):
        self.file.write_text('keep',encoding='utf-8')
        with self.assertRaises(Exception):capture_private(self.file)
        self.assertEqual(self.file.read_text(encoding='utf-8'),'keep')

    def test_missing_extractor_environment_is_explicit(self):
        with self.assertRaises(Exception):run_worker(self.folder/'missing-python.exe',self.file)

    def test_cli_actual_format_has_report_and_repeats(self):
        self.write(data())
        args=[sys.executable,'-m','cli','--db',str(self.db),'wechat','import',str(self.file),'--adapter','external','--report-dir',str(self.logs)]
        first=subprocess.run(args,cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        second=subprocess.run(args,cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(second.returncode,0,second.stderr)
        self.assertEqual(json.loads(second.stdout)['duplicated_count'],2)


if __name__=='__main__':unittest.main()
