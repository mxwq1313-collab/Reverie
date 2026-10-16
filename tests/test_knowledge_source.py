import hashlib
import json
from importlib.resources import files
import os
from pathlib import Path
import tempfile
import sqlite3
import unittest

from wechat_archive import ChatService, ConflictError, NotFoundError, ValidationError
from wechat_archive.agent import ArchiveScope
from wechat_archive.knowledge import ChunkRef, KnowledgeSource


class KnowledgeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"archive.db"
        self.service = ChatService(self.path)
        for i in range(4):
            self.service.create_user(wxid=f"fixture_{i}", nickname=f"姓名{i}")
        self.text = "  原文🙂\n"*24+"末尾"
        self.service.create_message(sender_id=1, receiver_id=2, content=self.text, create_time="2026-10-12T00:00:00Z")
        self.service.create_message(sender_id=2, receiver_id=1, content="第二条", create_time="2026-10-12T00:00:01Z")
        self.service.create_message(sender_id=1, receiver_id=3, content="其他会话", create_time="2026-10-12T00:00:02Z")
        self.service.create_message(sender_id=3, receiver_id=4, content="禁止读取", create_time="2026-10-12T00:00:03Z")
        self.source = KnowledgeSource(ArchiveScope(self.path, 1, 2), 32, 7)

    def collect(self, source=None, limit=2):
        source = source or self.source
        items = []
        cursor = None
        while True:
            page = source.page(limit=limit, cursor=cursor)
            items.extend(page["items"])
            if not page["has_more"]:
                return items
            cursor = page["next_cursor"]

    def test_unicode_original_fragments_and_round_trip(self):
        for item in self.collect():
            ref = item["reference"]
            resolved = self.source.resolve(ref).to_dict()
            self.assertEqual(item, resolved)
            if ref["message"]["message_id"] == 1:
                self.assertEqual(item["text"], self.text[ref["start"]:ref["end"]])
            self.assertEqual(item["kind"], "original_fragment")
            self.assertNotIn(str(self.path), json.dumps(item))

    def test_pagination_no_loss_duplicate_or_out_of_scope(self):
        small = self.collect(limit=1)
        large = self.collect(limit=100)
        self.assertEqual(small, large)
        self.assertEqual(len({item["chunk_id"] for item in small}), len(small))
        self.assertEqual({item["reference"]["message"]["message_id"] for item in small}, {1, 2})
        starts = [item["reference"]["start"] for item in small if item["reference"]["message"]["message_id"]==1]
        self.assertEqual(starts, list(range(0, len(self.text)-7, 25)))

    def test_same_text_different_messages_keep_different_refs(self):
        self.service.create_message(sender_id=1, receiver_id=2, content="第二条", create_time="2026-10-12T00:00:04Z")
        equal = [item for item in self.collect() if item["text"]=="第二条"]
        self.assertEqual(len(equal), 2)
        self.assertNotEqual(equal[0]["chunk_id"], equal[1]["chunk_id"])

    def test_update_delete_and_scope_switch_revoke(self):
        ref = self.source.page(1)["items"][0]["reference"]
        with self.assertRaises(ConflictError):
            KnowledgeSource(ArchiveScope(self.path, 1)).resolve(ref)
        self.service.update_message(1, content="改后的消息")
        with self.assertRaises(ConflictError): self.source.resolve(ref)
        fresh = self.source.page(1)["items"][0]["reference"]
        self.service.delete_message(1)
        with self.assertRaises(NotFoundError): self.source.resolve(fresh)

    def test_cursor_revoked_on_change_or_wrong_scope_processing(self):
        cursor = self.source.page(1)["next_cursor"]
        for source in (KnowledgeSource(ArchiveScope(self.path, 1)), KnowledgeSource(ArchiveScope(self.path, 1, 2), 33, 7)):
            with self.assertRaises(ConflictError): source.page(cursor=cursor)
        self.service.create_message(sender_id=1, receiver_id=2, content="新消息", create_time="2026-10-12T00:00:05Z")
        with self.assertRaises(ConflictError): self.source.page(cursor=cursor)

    def test_empty_scope(self):
        page = KnowledgeSource(ArchiveScope(self.path, 1, 4)).page()
        self.assertEqual(page["items"], [])
        self.assertEqual(page["messages"], 0)
        self.assertIsNone(page["next_cursor"])

    def test_no_original_or_schema_writes(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.collect()
        self.source.resolve(self.source.page(1)["items"][0]["reference"])
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_invalid_ref_offsets_versions_extra_keys_and_types(self):
        ref = self.source.page(1)["items"][0]["reference"]
        for change in ({"start": True}, {"end": 0}, {"version": 2}, {"version": True}, {"text_sha256": "bad"}, {"path": "bad"}):
            with self.assertRaises(ValidationError): ChunkRef.from_dict({**ref, **change})
        altered = {**ref, "text_sha256": "0"*64}
        with self.assertRaises(ConflictError): self.source.resolve(altered)

    def test_page_validation(self):
        for limit in (True, 0, 101):
            with self.assertRaises(ValidationError): self.source.page(limit)
        for cursor in ("bad", "x"*1025, 1):
            with self.assertRaises(ValidationError): self.source.page(cursor=cursor)

    def test_snapshot_consistency_and_revision(self):
        first = self.source.page()["source_revision"]
        self.service.update_message(1, content="更改")
        self.assertNotEqual(first, self.source.page()["source_revision"])

    def test_schema3_copy_read_and_reference_compatibility(self):
        from wechat_archive.migration.copy_upgrade import upgrade_archive_copy
        target = self.path.with_name("upgraded.db")
        upgrade_archive_copy(self.path, target)
        source = KnowledgeSource(ArchiveScope(target, 1, 2), 32, 7)
        self.assertEqual([c["text"] for c in self.collect(source)], [c["text"] for c in self.collect()])
        source.resolve(source.page(1)["items"][0]["reference"])

    def test_schema1_no_source_columns_stays_readable_and_unchanged(self):
        from wechat_archive.database.db import APPLICATION_ID
        target=self.path.with_name('schema1.db')
        connection=sqlite3.connect(target)
        try:
            connection.executescript(files('wechat_archive.database').joinpath('init.sql').read_text(encoding='utf-8'))
            connection.execute(f'PRAGMA application_id={APPLICATION_ID}'); connection.execute('PRAGMA user_version=1')
            connection.executemany('INSERT INTO users(wxid,nickname) VALUES(?,?)',[('one','自己'),('two','对方')])
            connection.execute('INSERT INTO messages(sender_id,receiver_id,create_time,content) VALUES(1,2,?,?)',('2026-10-14T00:00:00Z','旧库原文'))
            connection.commit()
        finally: connection.close()
        original=target.read_bytes(); source=KnowledgeSource(ArchiveScope(target,1,2))
        item=source.page()['items'][0]; self.assertIsNone(item['source'])
        self.assertEqual(source.resolve(item['reference']).text,'旧库原文'); self.assertEqual(target.read_bytes(),original)

    def test_replaced_archive_revokes_existing_source(self):
        ref=self.source.page(1)['items'][0]['reference']
        replacement=self.path.with_name('replacement.db'); replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement,self.path)
        with self.assertRaises(ConflictError): self.source.page()
        with self.assertRaises(ConflictError): self.source.resolve(ref)


if __name__ == "__main__":
    unittest.main()
