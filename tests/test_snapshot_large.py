"""Large synthetic selected-source acceptance; no real database access."""
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from test_snapshot import source_shard, header
from wechat_archive import ChatService
from wechat_archive.importer.snapshot_importer import SnapshotImporter
from wechat_archive.migration.copy_upgrade import upgrade_archive_copy
from wechat_archive.wechat_source.snapshot import project_snapshot


class LargeSnapshotTests(unittest.TestCase):
    def test_more_than_100000_records_preserved_with_bounded_batches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "archive-v2.db"
            target = root / "archive-v3.db"
            ChatService(source)
            upgrade_archive_copy(source, target)
            connection, table = source_shard(root / "source.db", count=100001)
            start = time.perf_counter()
            try:
                captured = project_snapshot([(connection, table, "message__message_0.db")], header(), root / "snapshot")
            finally:
                connection.close()
            progress = []
            importer = SnapshotImporter(target, report_dir=root / "logs")
            report = importer.import_snapshot(root / "snapshot", batch_size=1000, progress=lambda event: progress.append(event["processed"]))
            self.assertEqual((captured["records"], report.success_count, report.failed_count), (100001, 100001, 0))
            self.assertEqual(report.status, "success")
            self.assertEqual(ChatService(target).stats()["messages"], 100001)
            self.assertEqual(progress[-1], 100001)
            self.assertTrue(all(0 < right - left <= 1000 for left, right in zip([0] + progress, progress)))
            with ChatService(target).database.connection() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 101)
                self.assertEqual(conn.execute("SELECT SUM(record_count) FROM import_batches").fetchone()[0], 100001)
            print(f"Synthetic snapshot 100001: capture+import={time.perf_counter()-start:.3f}s batches=101")


if __name__ == "__main__":
    unittest.main()
