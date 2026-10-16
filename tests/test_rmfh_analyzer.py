"""文件结构和 RMFH 外壳分析验证；仅使用自建数据。"""

import hashlib
import json
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from test_backup_adapter import fixture, envelope
from wechat_archive.importer.validator import DocumentError
from wechat_archive.wechat_adapter.backup import RMFHFormatAnalyzer, parse_header, parse_container
from wechat_archive.ui.import_controller import ImportController
from wechat_archive.ui.import_window import ImportWindow

ROOT = Path(__file__).resolve().parents[1]


class RMFHAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder/'backup'
        self.device = fixture(self.source)
        self.session = self.device/'files/1/session_synthetic'
        self.package = self.session/'ChatPackage/1767225600000-1767225600000'
        self.output = self.folder/'reports'

    def analyze(self, **options):
        return RMFHFormatAnalyzer(self.source, **options).analyze()

    def test_structure_lists_each_file_with_relative_parent_and_category(self):
        result = self.analyze()
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.summary['files'], 5)
        self.assertTrue(result.inventory_complete)
        self.assertEqual(len(result.file_headers), 5)
        self.assertTrue(all(not Path(row['path']).is_absolute() for row in result.files))
        self.assertEqual(result.summary['categories']['Index']['files'], 1)

    def test_directory_list_preserves_empty_directories(self):
        (self.source/'empty_account').mkdir()
        result = self.analyze()
        row = next(row for row in result.directories if row['path']=='empty_account')
        self.assertEqual((row['direct_files'],row['direct_directories']), (0,0))

    def test_directory_depth_and_parent_are_explicit(self):
        result = self.analyze()
        self.assertEqual(next(row for row in result.directories if row['path']=='.')['parent'],None)
        media = next(row for row in result.directories if row['path'].endswith('/Media'))
        self.assertEqual(media['depth'],6)
        self.assertTrue(media['parent'].endswith('/session_synthetic'))

    def test_unknown_fields_use_offsets_not_invented_semantics(self):
        header = parse_header(envelope()[:16])
        self.assertEqual([f['offset'] for f in header['fields']], [4,8,10,12])
        self.assertEqual(header['fields'][0]['little_endian'], 123)
        self.assertNotEqual(header['fields'][0]['big_endian'], 123)
        self.assertTrue(all(f['meaning']=='unverified' for f in header['fields']))
        self.assertNotIn('session_id',header)

    def test_invalid_header_magic_rejected(self):
        with self.assertRaises(DocumentError):
            parse_header(b'OTHER'+bytes(20))

    def test_short_rmfh_prefix_rejected(self):
        with self.assertRaises(DocumentError):
            parse_header(b'RMFH'+bytes(5))

    def test_container_returns_exact_payload_span_without_decoding(self):
        container = parse_container(self.package)
        self.assertEqual(container.payload.offset, 128)
        self.assertEqual(container.payload.length, self.package.stat().st_size-256)
        self.assertEqual(container.footer_offset,self.package.stat().st_size-128)
        self.assertEqual(container.payload.encoding,'unknown')
        self.assertFalse(container.content_decoded)

    def test_rmft_inside_payload_does_not_change_container_boundary(self):
        payload = b'RMFT'+bytes(32)+b'RMFH'+bytes(32)
        self.package.write_bytes(envelope(payload))
        self.assertEqual(parse_container(self.package).payload.length,len(payload))

    def test_missing_footer_rejected_by_single_file_parser(self):
        self.package.write_bytes(envelope()[:-128]+bytes(128))
        with self.assertRaises(DocumentError):
            parse_container(self.package)

    def test_unknown_projection_is_recorded_and_not_forced(self):
        self.package.write_bytes(envelope(flags=0x102))
        result = self.analyze()
        self.assertEqual(result.status,'partial')
        self.assertEqual(result.summary['categories']['ChatPackage']['rejected_envelopes'],1)
        self.assertTrue(result.issues)
        with self.assertRaises(DocumentError):
            parse_container(self.package)

    def test_invalid_backup_attr_is_not_reported_as_clean_structure(self):
        (self.device/'backup.attr').write_bytes(b'unknown')
        self.assertEqual(self.analyze().status,'partial')

    def test_index_unknown_format_is_explicit(self):
        (self.session/'Index/synthetic.dat').write_bytes(b'unknown index')
        result = self.analyze()
        self.assertEqual(result.status,'partial')
        self.assertEqual(result.summary['categories']['Index']['non_rmfh'],1)

    def test_media_container_is_analyzed(self):
        result = self.analyze()
        self.assertEqual(result.summary['categories']['Media']['supported_envelopes'],1)

    def test_category_names_accept_windows_case_variants(self):
        media = self.source/'media'
        media.mkdir();(media/'case_variant').write_bytes(envelope())
        self.assertEqual(self.analyze().summary['categories']['Media']['files'],2)

    def test_non_rmfh_media_is_unverified_and_not_interpreted(self):
        (self.session/'Media/synthetic.dat').write_bytes(b'unknown media')
        result = self.analyze()
        row = next(row for row in result.file_headers if row['category']=='Media')
        self.assertEqual(row['status'],'non_rmfh')
        self.assertIsNone(row['header'])
        self.assertIsNone(row['payload'])

    def test_non_rmfh_metadata_contents_are_not_dumped(self):
        secret = 'private-key-like-material-must-not-appear'
        (self.device.parent/'roam_device_info.dat').write_text(secret,encoding='utf-8')
        result = self.analyze()
        self.assertNotIn(secret,json.dumps(result.header_report()))

    def test_header_patterns_aggregate_by_prefix_and_category(self):
        result = self.analyze()
        patterns = result.summary['header_patterns']
        self.assertEqual(len(patterns),1)
        self.assertEqual(patterns[0]['files'],4)
        self.assertEqual(patterns[0]['categories']['ChatPackage'],1)

    def test_file_sizes_are_inventory_sizes(self):
        result = self.analyze()
        self.assertEqual(result.summary['bytes'],sum(p.stat().st_size for p in self.source.rglob('*') if p.is_file()))
        self.assertEqual(result.summary['bytes'],sum(row['bytes'] for row in result.files))

    def test_large_file_reads_only_fixed_edges(self):
        media = self.session/'Media/synthetic.dat'
        media.write_bytes(envelope(bytes(512*1024)))
        original = Path.open
        reads = []
        class Observed:
            def __init__(self, handle): self.handle=handle
            def __enter__(self): return self
            def __exit__(self,*args): return self.handle.__exit__(*args)
            def __getattr__(self,name): return getattr(self.handle,name)
            def read(self,size=-1):
                self_test.assertLessEqual(size,128)
                data=self.handle.read(size);reads.append(len(data));return data
        self_test=self
        def open_file(path,*args,**kwargs):
            handle=original(path,*args,**kwargs)
            return Observed(handle) if path==media else handle
        with patch.object(Path,'open',open_file):
            row=RMFHFormatAnalyzer(self.source).analyze_file(media)
        self.assertEqual(sum(reads),256)
        self.assertEqual(row['status'],'supported_envelope')

    def test_database_is_not_opened_and_android_parser_not_called(self):
        database=self.device/'EnMicroMsg.db'
        database.write_bytes(envelope())
        original=Path.open
        def guarded(path,*args,**kwargs):
            if path==database: raise AssertionError('Database was opened')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',guarded), patch('sqlite3.connect',side_effect=AssertionError('SQL accessed')), patch('wechat_archive.wechat_adapter.android.parser.AndroidWeChatParser.parse',side_effect=AssertionError('Android parser called')):
            result=self.analyze()
        row=next(row for row in result.file_headers if row['path'].endswith('EnMicroMsg.db'))
        self.assertEqual(row['status'],'database_skipped')
        self.assertEqual(result.summary['categories']['other']['database_skipped'],1)

    def test_single_database_container_parse_is_rejected_before_open(self):
        database=self.folder/'EnMicroMsg.db';database.write_bytes(envelope())
        with patch.object(Path,'open',side_effect=AssertionError('opened')):
            with self.assertRaisesRegex(DocumentError,'数据库'):
                parse_container(database)

    def test_unknown_directory_has_an_explicit_unsupported_status(self):
        empty=self.folder/'unknown';empty.mkdir()
        self.assertEqual(RMFHFormatAnalyzer(empty).analyze().status,'unsupported')

    def test_single_rmfh_file_is_analyzable_without_wechat_identity_claim(self):
        result=RMFHFormatAnalyzer(self.package).analyze()
        self.assertEqual((result.scope_kind,result.status),('rmfh-file','success'))
        self.assertIsNone(result.message_count)

    def test_bad_package_does_not_hide_other_file_records(self):
        bad=self.package.parent/'bad';bad.write_bytes(b'RMFH')
        result=self.analyze()
        self.assertEqual(result.summary['files'],6)
        self.assertEqual(len(result.file_headers),6)
        self.assertEqual(result.status,'partial')

    def test_source_bytes_remain_identical(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.analyze().save(self.output)
        after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_reports_are_utf8_distinct_and_have_no_pending_temp_files(self):
        result=self.analyze()
        first=result.save(self.output).copy()
        second=result.save(self.output).copy()
        self.assertNotEqual(first,second)
        for paths in (first,second):
            self.assertEqual(set(paths),{'structure_report.json','header_analysis.json','summary.md'})
            self.assertEqual(json.loads(Path(paths['header_analysis.json']).read_text(encoding='utf-8'))['report_version'],'1.0')
        self.assertEqual(list(self.output.rglob('*.tmp')),[])

    def test_reports_cannot_be_written_into_source(self):
        with self.assertRaises(DocumentError): self.analyze().save(self.source/'reports')
        self.assertFalse((self.source/'reports').exists())

    def test_bounds_fail_with_incomplete_inventory(self):
        result=self.analyze(max_files=1)
        self.assertEqual(result.status,'failed')
        self.assertFalse(result.inventory_complete)

    def test_path_traversal_rejected(self):
        with self.assertRaises(DocumentError): RMFHFormatAnalyzer('../backup')

    def test_analysis_file_cannot_escape_selected_scope(self):
        unrelated=self.folder/'unrelated';unrelated.write_bytes(envelope())
        with self.assertRaises(DocumentError): RMFHFormatAnalyzer(self.source).analyze_file(unrelated)

    def test_lock_prevents_claiming_stable_source(self):
        (self.device/'files/1/pkg.lock').write_bytes(b'')
        result=self.analyze()
        self.assertEqual(result.status,'partial')
        self.assertFalse(result.source_stable)

    def test_unreadable_file_keeps_failed_inventory_count_consistent(self):
        with patch('wechat_archive.wechat_adapter.backup.analyzer.read_edges',side_effect=OSError('unreadable')):
            result=self.analyze()
        self.assertEqual(result.status,'failed')
        self.assertFalse(result.inventory_complete)
        self.assertEqual(result.summary['files'],sum(c['files'] for c in result.summary['categories'].values()))

    def test_controller_does_not_need_database_target(self):
        with patch('sqlite3.connect',side_effect=AssertionError('DB used')):
            result=ImportController(report_dir=self.output).analyze_backup(self.source)
        self.assertEqual(result['status'],'success')
        self.assertTrue(Path(result['report_paths']['summary.md']).is_file())

    def test_cli_writes_report_bundle_without_archive(self):
        target=self.folder/'must_not_exist.db'
        result=subprocess.run([sys.executable,'-m','cli','--db',str(target),'wechat','analyze-backup',str(self.source),'--report-dir',str(self.output)],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        self.assertTrue(data['analysis_only'])
        self.assertFalse(target.exists())
        self.assertTrue(Path(data['report_paths']['header_analysis.json']).is_file())

    def test_cli_single_header_returns_neutral_fields_and_payload_span(self):
        result=subprocess.run([sys.executable,'-m','cli','wechat','rmfh-header',str(self.package)],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual(data['payload']['offset'],128)
        self.assertEqual(data['header']['fields'][0]['meaning'],'unverified')

    def test_cli_partial_format_uses_nonzero_exit_and_retains_reports(self):
        self.package.write_bytes(envelope(count=2))
        result=subprocess.run([sys.executable,'-m','cli','wechat','analyze-backup',str(self.source),'--report-dir',str(self.output)],cwd=ROOT,capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertTrue(json.loads(result.stdout)['report_paths'])

    def test_window_analysis_is_clickable_and_ignores_target_field(self):
        root=tk.Tk();root.withdraw()
        app=ImportWindow(root,controller=ImportController(report_dir=self.output))
        try:
            app.source.set(str(self.source));app.target.set('不是归档库')
            app.analysis_button.invoke()
            until=time.monotonic()+15
            while app.busy and time.monotonic()<until: root.update();time.sleep(.01)
            self.assertFalse(app.busy)
            self.assertIn('外壳分析完成',app.status.get())
            self.assertTrue(app.last_report.is_file())
            self.assertIsNone(app.last_database)
            self.assertIn('Index',app.result.get('1.0','end'))
        finally: app.close()


if __name__=='__main__': unittest.main()
