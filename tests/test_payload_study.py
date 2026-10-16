import bz2
import gzip
import hashlib
import hmac
import json
import lzma
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from test_backup_adapter import fixture,envelope
from wechat_archive.importer.validator import DocumentError
from wechat_archive.wechat_adapter.backup import RMFHPayloadStudy,DecoderRegistry,PayloadDecoder,DecodeFailure
from wechat_archive.wechat_adapter.backup.bounded_reader import ReadBudget,read_region
from wechat_archive.wechat_adapter.backup.wire_probe import parse_wire,probe_wire,WireProbeError
from wechat_archive.ui.import_controller import ImportController
from wechat_archive.ui.import_window import ImportWindow

ROOT=Path(__file__).resolve().parents[1]


def varint(value):
    result=bytearray()
    while value>127: result.append((value&127)|128);value>>=7
    return bytes(result)+bytes([value])


def field(number,value):
    return varint(number<<3)+varint(value) if isinstance(value,int) else varint((number<<3)|2)+varint(len(value))+value


class WireTests(unittest.TestCase):
    def test_varint_and_length_delimited_fields(self):
        data=field(1,150)+field(2,'中文'.encode())
        result=parse_wire(data)
        self.assertEqual(result['consumed_bytes'],len(data))
        self.assertEqual(result['fields'][0]['unsigned_value'],150)
        self.assertFalse(result['schema_verified'])

    def test_nested_structure_is_compatible_not_semantically_named(self):
        result=parse_wire(field(1,field(2,7)))
        self.assertTrue(result['fields'][0]['nested_wire_compatible'])
        self.assertEqual(result['fields'][0]['nested_fields'][0]['meaning'],'unverified')

    def test_fixed32_and_fixed64_are_bounded(self):
        result=parse_wire(b'\x09'+bytes(8)+b'\x15'+bytes(4))
        self.assertEqual([r['value_bytes'] for r in result['fields']],[8,4])

    def test_empty_sample_is_not_format_evidence(self):
        self.assertFalse(probe_wire(b'')['compatible'])

    def test_truncated_varint_rejected(self):
        self.assertFalse(probe_wire(b'\x08\x80')['compatible'])

    def test_varint_overflow_rejected(self):
        self.assertFalse(probe_wire(b'\x08'+bytes([255])*10)['compatible'])

    def test_nonminimal_varint_is_outside_projection(self):
        self.assertFalse(probe_wire(b'\x08\x81\x00')['compatible'])

    def test_zero_field_and_group_rejected(self):
        for data in (b'\x00\x01',b'\x0b\x0c'):
            self.assertFalse(probe_wire(data)['compatible'])

    def test_length_larger_than_remaining_rejected(self):
        self.assertFalse(probe_wire(b'\x0a\x20abc')['compatible'])

    def test_partial_data_does_not_certify_full_wire_message(self):
        self.assertFalse(probe_wire(field(1,1),complete=False)['compatible'])

    def test_field_budget_and_nested_budget_enforced(self):
        with self.assertRaises(WireProbeError): parse_wire(field(1,1)*10,max_fields=3)
        with self.assertRaises(WireProbeError): parse_wire(field(1,field(2,1)*10),max_fields=3)

    def test_byte_cap_rejected(self):
        with self.assertRaises(WireProbeError): parse_wire(bytes(65537))

    def test_uint64_is_not_assumed_signed_or_timestamp(self):
        result=parse_wire(field(1,2**64-1))
        self.assertEqual(result['fields'][0]['unsigned_value'],2**64-1)
        self.assertEqual(result['fields'][0]['meaning'],'unverified')

    def test_key_like_token_is_not_exported_or_accepted_as_key(self):
        token=b'_wxroam:'+b'A'*88
        result=parse_wire(field(1,token))
        self.assertNotIn(token.decode(),json.dumps(result))
        self.assertEqual(result['fields'][0]['text_shape']['key_role'],'unverified')


class DecoderTests(unittest.TestCase):
    def setUp(self): self.registry=DecoderRegistry()

    def test_gzip_complete_checksum_validated(self):
        result=self.registry.decode(gzip.compress(b'known synthetic text'))
        self.assertEqual((result.code,result.data),('decoded',b'known synthetic text'))

    def test_zlib_complete_stream(self):
        result=self.registry.decode(zlib.compress(b'synthetic'))
        self.assertEqual(result.data,b'synthetic')

    def test_bzip2_complete_stream(self):
        self.assertEqual(self.registry.decode(bz2.compress(b'synthetic')).data,b'synthetic')

    def test_xz_complete_stream(self):
        self.assertEqual(self.registry.decode(lzma.compress(b'synthetic')).data,b'synthetic')

    def test_checksum_corruption_rejected(self):
        data=bytearray(gzip.compress(b'synthetic'));data[-5]^=1
        result=self.registry.decode(bytes(data))
        self.assertEqual(result.code,'invalid_stream')
        self.assertIsNone(result.data)

    def test_truncated_compressed_stream_rejected(self):
        self.assertEqual(self.registry.decode(gzip.compress(b'synthetic')[:-3]).code,'invalid_stream')

    def test_incomplete_sample_has_its_own_status(self):
        self.assertEqual(self.registry.decode(gzip.compress(b'synthetic'),complete=False).code,'needs_complete_sample')

    def test_output_limit_rejects_compression_bomb(self):
        for data in (gzip.compress(b'A'*100000),zlib.compress(b'A'*100000),bz2.compress(b'A'*100000),lzma.compress(b'A'*100000)):
            with self.subTest(signature=data[:3]):
                self.assertEqual(self.registry.decode(data,max_output=32).code,'output_limit')

    def test_trailing_bytes_and_multimember_rejected(self):
        compressed=gzip.compress(b'x')
        self.assertEqual(self.registry.decode(compressed+b'trailing').code,'unsupported_stream_layout')
        self.assertEqual(self.registry.decode(compressed+compressed).code,'unsupported_stream_layout')

    def test_unknown_data_does_not_become_needs_key(self):
        result=self.registry.decode(bytes(range(256)))
        self.assertEqual(result.code,'unknown_encoding')

    def test_unknown_encryption_profile_remains_unsupported(self):
        self.assertEqual(self.registry.decode(b'opaque',profile='unverified-aes',key=b'key').code,'unsupported_encoding')

    def test_registered_decoder_requires_key_then_validates_authentication(self):
        class AuthDecoder(PayloadDecoder):
            requires_key=True
            def decode(self,data,*,key,max_output):
                content,tag=data[:-32],data[-32:]
                if not hmac.compare_digest(tag,hmac.digest(key,content,'sha256')):
                    raise DecodeFailure('authentication_failed','invalid')
                return content,True
        self.registry.register('synthetic-auth',AuthDecoder())
        raw=b'synthetic text';key=b'only synthetic key';encoded=raw+hmac.digest(key,raw,'sha256')
        self.assertEqual(self.registry.decode(encoded,profile='synthetic-auth').code,'needs_key')
        self.assertEqual(self.registry.decode(encoded,profile='synthetic-auth',key=b'wrong').code,'authentication_failed')
        self.assertEqual(self.registry.decode(encoded,profile='synthetic-auth',key=key).data,raw)

    def test_unverified_plaintext_from_key_decoder_is_rejected(self):
        class BadDecoder(PayloadDecoder):
            requires_key=True
            def decode(self,data,*,key,max_output): return b'plaintext',False
        self.registry.register('bad-auth',BadDecoder())
        result=self.registry.decode(b'opaque',profile='bad-auth',key=b'key')
        self.assertEqual(result.code,'authentication_failed');self.assertIsNone(result.data)

    def test_failure_and_summary_never_expose_key_or_output(self):
        key=b'private-key-must-not-be-logged'
        class BadDecoder(PayloadDecoder):
            requires_key=True
            def decode(self,data,*,key,max_output): raise DecodeFailure('invalid_stream',key.decode())
        self.registry.register('redaction-test',BadDecoder())
        result=self.registry.decode(b'opaque',profile='redaction-test',key=key)
        self.assertNotIn(key.decode(),json.dumps(result.summary()))
        result=self.registry.decode(gzip.compress(b'private plaintext'))
        self.assertNotIn('private plaintext',json.dumps(result.summary()))

    def test_decoder_implementation_exception_is_redacted(self):
        class Broken(PayloadDecoder):
            def decode(self,data,*,key,max_output): raise RuntimeError('private internal text')
        self.registry.register('broken',Broken())
        self.assertEqual(self.registry.decode(b'x',profile='broken').code,'decoder_failed')

    def test_duplicate_profile_registration_rejected(self):
        from wechat_archive.wechat_adapter.backup.payload_decoder import CompressionDecoder
        with self.assertRaises(ValueError): self.registry.register('gzip',CompressionDecoder('gzip'))

    def test_invalid_api_inputs_are_rejected(self):
        self.assertEqual(self.registry.decode(b'x',profile=[]).code,'unsupported_encoding')
        self.assertEqual(self.registry.decode(b'x',key='secret').code,'invalid_key')
        self.assertEqual(self.registry.decode(bytes(65537)).code,'input_limit')


class PayloadStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.source=self.folder/'backup';self.device=fixture(self.source)
        self.session=self.device/'files/1/session_synthetic'
        self.package=self.session/'ChatPackage/1767225600000-1767225600000'
        self.index=self.session/'Index/1767225600000-1767225600000'
        self.index.write_bytes(envelope(field(1,5)))
        self.package.write_bytes(envelope(gzip.compress(b'synthetic text')))
        (self.device.parent/'roam_device_info.dat').write_bytes(field(1,b'opaque metadata'))
        self.output=self.folder/'reports'

    def study(self,**options): return RMFHPayloadStudy(self.source,**options).analyze()

    def test_read_region_tracks_cap_and_budget(self):
        budget=ReadBudget(10)
        data,complete=read_region(self.source,self.package,offset=128,length=20,cap=5,budget=budget)
        self.assertEqual((len(data),complete,budget.used),(5,False,5))

    def test_budget_refuses_read_before_open(self):
        with patch.object(Path,'open',side_effect=AssertionError('opened')):
            with self.assertRaises(DocumentError): read_region(self.source,self.package,offset=0,length=10,cap=10,budget=ReadBudget(1))

    def test_invalid_budget_state_is_rejected(self):
        budget=ReadBudget();budget.used=-1
        with self.assertRaises(DocumentError): read_region(self.source,self.package,offset=0,length=1,cap=1,budget=budget)

    def test_read_region_cannot_escape_source(self):
        outside=self.folder/'outside';outside.write_bytes(b'xx')
        with self.assertRaises(DocumentError): read_region(self.source,outside,offset=0,length=2,cap=2,budget=ReadBudget())

    def test_invalid_range_refused(self):
        for offset,length in ((-1,2),(0,10**9),(False,1)):
            with self.assertRaises(DocumentError): read_region(self.source,self.package,offset=offset,length=length,cap=3,budget=ReadBudget())

    def test_database_read_is_refused(self):
        database=self.source/'EnMicroMsg.db';database.write_bytes(b'not opened')
        with patch.object(Path,'open',side_effect=AssertionError('opened')):
            with self.assertRaises(DocumentError): read_region(self.source,database,offset=0,length=3,cap=3,budget=ReadBudget())

    def test_metadata_and_pair_sampling(self):
        result=self.study()
        self.assertEqual(result.status,'success')
        self.assertEqual((result.summary['chat_samples'],result.summary['index_samples']),(1,1))
        self.assertEqual(result.summary['metadata_wire_compatible'],1)

    def test_smallest_samples_are_selected_per_pattern(self):
        (self.package.parent/'larger').write_bytes(envelope(bytes(200)))
        result=self.study(samples_per_pattern=1)
        self.assertEqual(result.summary['chat_samples'],1)
        self.assertTrue(next(r for r in result.samples if r['role']=='ChatPackage')['path'].endswith(self.package.name))

    def test_all_patterns_are_covered(self):
        (self.package.parent/'another-pattern').write_bytes(envelope(b'opaque',flags=0x201))
        self.assertEqual(self.study().summary['patterns_sampled'],2)

    def test_registered_compression_can_decode_but_not_claim_messages(self):
        result=self.study()
        self.assertEqual(result.summary['decoded_streams'],1)
        self.assertEqual(result.assessment['real_messages_recovered'],0)
        self.assertFalse(result.assessment['message_schema_verified'])

    def test_truncated_sampling_is_explicit(self):
        result=self.study(sample_bytes=8)
        self.assertGreater(result.summary['truncated_samples'],0)
        chat=next(r for r in result.samples if r['role']=='ChatPackage')
        self.assertEqual(chat['decoder']['code'],'needs_complete_sample')

    def test_budget_failures_do_not_exceed_cap(self):
        result=self.study(total_bytes=2)
        self.assertEqual(result.status,'failed')
        self.assertLessEqual(result.summary['payload_metadata_bytes_read'],2)

    def test_database_and_media_payloads_are_not_opened(self):
        database=self.source/'EnMicroMsg.db';database.write_bytes(b'keep')
        original=Path.open
        def guard(path,*args,**kwargs):
            if path==database: raise AssertionError('database opened')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',guard),patch('sqlite3.connect',side_effect=AssertionError('database used')),patch('wechat_archive.wechat_adapter.android.parser.AndroidWeChatParser.parse',side_effect=AssertionError('Android called')):
            result=self.study()
        self.assertEqual(result.summary['media_payloads_sampled'],0)
        self.assertEqual(result.summary['database_files_opened'],0)

    def test_media_never_reaches_body_reader(self):
        from wechat_archive.wechat_adapter.backup.payload_study import read_region as original
        def body_read(source,path,**kwargs):
            if 'Media' in path.parts: raise AssertionError('Media body sampled')
            return original(source,path,**kwargs)
        with patch('wechat_archive.wechat_adapter.backup.payload_study.read_region',body_read):
            self.assertEqual(self.study().status,'success')

    def test_source_change_is_reported(self):
        from wechat_archive.wechat_adapter.backup.bounded_reader import SamplingError
        with patch.object(RMFHPayloadStudy,'_sample',side_effect=SamplingError('source_changed','changed')):
            result=self.study()
        self.assertEqual(result.status,'failed');self.assertFalse(result.source_stable)

    def test_missing_index_does_not_create_false_pair(self):
        self.index.unlink();result=self.study()
        self.assertEqual(result.summary['index_samples'],0)
        self.assertIsNone(result.samples[0]['pair_candidate'])

    def test_unknown_index_is_reported(self):
        self.index.write_bytes(b'unknown index')
        self.assertEqual(self.study().status,'partial')

    def test_reports_do_not_include_raw_strings_samples_or_keys(self):
        result=self.study();paths=result.save(self.output)
        for path in paths.values():
            text=Path(path).read_text(encoding='utf-8')
            self.assertNotIn('opaque metadata',text);self.assertNotIn('synthetic text',text)

    def test_source_hashes_unchanged_after_saved_study(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.study().save(self.output)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_report_bundle_is_unique_and_has_four_outputs(self):
        result=self.study();first=result.save(self.output).copy();second=result.save(self.output).copy()
        self.assertNotEqual(first,second);self.assertEqual(len(first),4)
        self.assertEqual(list(self.output.rglob('*.tmp')),[])

    def test_reports_inside_source_rejected(self):
        with self.assertRaises(DocumentError): self.study().save(self.source/'reports')
        self.assertFalse((self.source/'reports').exists())

    def test_options_and_file_source_rejected(self):
        for options in ({'sample_bytes':65537},{'samples_per_pattern':0},{'total_bytes':0}):
            with self.assertRaises(ValueError): RMFHPayloadStudy(self.source,**options)
        with self.assertRaises(ValueError): RMFHPayloadStudy(self.package)

    def test_controller_study_ignores_database_target(self):
        result=ImportController(report_dir=self.output).study_payload(self.source)
        self.assertTrue(Path(result['report_paths']['summary.md']).is_file())

    def test_cli_generates_assessment_without_database(self):
        archive=self.folder/'must_not_exist.db'
        run=subprocess.run([sys.executable,'-m','cli','--db',str(archive),'wechat','study-payload',str(self.source),'--report-dir',str(self.output)],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['assessment']['real_messages_recovered'],0)
        self.assertFalse(archive.exists())

    def test_gui_payload_button_returns_reports(self):
        root=tk.Tk();root.withdraw();app=ImportWindow(root,controller=ImportController(report_dir=self.output))
        try:
            app.source.set(str(self.source));app.target.set('invalid target ignored')
            app.study_button.invoke();deadline=time.monotonic()+15
            while app.busy and time.monotonic()<deadline: root.update();time.sleep(.01)
            self.assertFalse(app.busy);self.assertIn('探测完成',app.status.get())
            self.assertTrue(app.last_report.is_file());self.assertIsNone(app.last_database)
        finally: app.close()


if __name__=='__main__': unittest.main()
