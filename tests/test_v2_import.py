"""Synthetic large source validation; no live WeChat source or network."""
import json,sqlite3,tempfile,threading,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from test_rich_source import FakeSource
from wechat_archive.wechat_source.rich_source import capture_rich
from wechat_archive.importer.rich_importer import create_rich_archive
from wechat_archive.importer.rich_snapshot import RichSnapshotImporter
from wechat_archive.ui.source_options import selected_range
from wechat_archive.errors import ValidationError


class LargeImportV2Tests(unittest.TestCase):
    def test_100003_records_capture_and_import_in_bounded_batches(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);db=FakeSource(folder,count=100003,shards=1);self.addCleanup(db.close);progress=[]
            with patch('wechat_archive.wechat_source.media_acquisition.local_media_reader',return_value=None):
                captured=capture_rich(db,{'nick_name':'自己'},{'username':db.peer},folder/'snapshot',limit=1000000,progress=progress.append)
            manifest=json.loads((Path(captured['output'])/'rich_snapshot.json').read_text(encoding='utf-8'))
            self.assertEqual(captured['records'],100003);self.assertEqual(len(manifest['batches']),51);self.assertTrue(all(x['records']<=2000 for x in manifest['batches']));self.assertIn('100003 / 100003',progress[-1])
            target=folder/'archive.db';create_rich_archive(target);saved=[]
            report=RichSnapshotImporter(target).import_snapshot(captured['output'],progress=saved.append)
            self.assertEqual((report.success_count,report.failed_count),(100003,0));self.assertEqual(len(saved),51)
            with closing(sqlite3.connect(target)) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],100003)
            db.close();self._cleanups.pop()

    def test_ranges_are_explicit_and_unknown_selection_does_not_fall_back_to_50(self):
        self.assertEqual(selected_range('全部电脑本地记录'),(True,1000000))
        for label,value in (('最近 5000 条',5000),('最近 5 万条',50000),('最近 10 万条',100000),('最近 100 万条',1000000)):
            self.assertEqual(selected_range(label),(False,value))
        with self.assertRaises(ValidationError):selected_range('unregistered range')
        from wechat_archive.wechat_source.live_source import publish_progress
        with tempfile.TemporaryDirectory() as folder,patch.object(Path,'replace',side_effect=PermissionError('synthetic status reader lock')):
            publish_progress(Path(folder),'正在读取：100 / 1000')

    def test_cancel_between_batches_preserves_commits_and_resume_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);db=FakeSource(folder,count=4100,shards=1)
            try:
                with patch('wechat_archive.wechat_source.media_acquisition.local_media_reader',return_value=None):captured=capture_rich(db,{'nick_name':'自己'},{'username':db.peer},folder/'snapshot',all_history=True,staging_parent=folder/'job/rich_staging')
                self.assertFalse(list((folder/'job/rich_staging').iterdir()))
                target=folder/'archive.db';create_rich_archive(target);cancel=threading.Event()
                partial=RichSnapshotImporter(target).import_snapshot(captured['output'],cancel_event=cancel,progress=lambda _:cancel.set())
                self.assertEqual(partial.success_count,2000);self.assertEqual(partial.status,'partial')
                resumed=RichSnapshotImporter(target).import_snapshot(captured['output']);self.assertEqual((resumed.success_count,resumed.duplicated_count),(2100,2000))
            finally:db.close()
