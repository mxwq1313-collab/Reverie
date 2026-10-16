"""Sealed, selected-conversation projection and bounded keyset reader."""
import heapq
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from ..errors import ArchiveError, ConflictError, ValidationError
from ..importer.json_importer import _unique_keys, _invalid_number
from .parser import checked_path, ExternalExportParser, file_stamp
from .acquisition import _json_value

SNAPSHOT_API = "WeChatDB.snapshot_projection-v1"
SNAPSHOT_APPLICATION_ID = 0x5743534E
MAX_RECORD_BYTES = 16 * 1024 * 1024
SOURCE_COLUMNS = ("local_id", "local_type", "real_sender_id", "create_time", "message_content", "source", "packed_info_data", "compress_content", "server_id", "sort_seq")
SCHEMA = """CREATE TABLE source_rows (
source_local_id INTEGER PRIMARY KEY,
order_time INTEGER NOT NULL,
order_seq INTEGER NOT NULL,
record_json TEXT NOT NULL
);
CREATE INDEX idx_source_rows_order ON source_rows(order_time,order_seq,source_local_id);
"""


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _header(header):
    if not isinstance(header, dict) or "records" in header:
        raise ValidationError("快照头不能包含未登记字段或整份记录数组")
    ExternalExportParser.validate_payload({**header, "records": []}, allowed_apis=(SNAPSHOT_API,))
    return header


def _record_from_row(row, label):
    local = row["local_id"]
    if type(local) is not int:
        raise ValidationError("消息局部ID不是登记整数，未建立快照")
    server = row["server_id"]
    if type(server) is int and server > 0:
        kind, message_id = "server", str(server)
    elif server in (None, 0):
        kind, message_id = "local", str(local)
    else:
        kind, message_id = "unknown", str(local)
    raw = dict(local_id=local, local_type=row["local_type"], server_id=server,
               sender_id=row["real_sender_id"], sender_username=row["sender_username"], create_time=row["create_time"],
               content=row["message_content"], source=row["source"], packed_info=row["packed_info_data"],
               compress_content=row["compress_content"], sort_seq=row["sort_seq"], shard=label)
    return _json_value({"local_id": local, "source_database": label, "source_message_id": message_id,
                        "source_id_kind": kind, "sender_wxid": row["sender_username"], "timestamp": row["create_time"],
                        "content": row["message_content"], "raw_type": row["local_type"],
                        "raw_payload": {"native": {}, "database_row": raw}})


def project_snapshot(tables, header, output, *, guard=None, staging_parent=None):
    """Project only the chosen conversation tables, never copy whole source DBs."""
    header = _header(header)
    from ..exporter.readable import _local_path
    output = _local_path(output)
    if output.exists():
        raise ConflictError("快照目标已存在，不能覆盖")
    output.parent.mkdir(parents=True, exist_ok=True)
    shards, labels = [], set()
    staging_parent = _local_path(staging_parent) if staging_parent is not None else output.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-snapshot-", dir=staging_parent) as staging_name:
        staging = Path(staging_name).resolve()
        if staging.parent != staging_parent:
            raise ConflictError("快照临时目录越出本操作范围")
        for index, (connection, table, label) in enumerate(tables):
            if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", label) or label in labels:
                raise ValidationError("消息分片标识缺失或重复，不能猜测")
            labels.add(label)
            expected_table = "Msg_" + hashlib.md5(header["conversation"]["wxid"].encode("utf-8")).hexdigest()
            if not isinstance(table, str) or table != expected_table:
                raise ValidationError("会话表名称不符合登记投影")
            columns = {row["name"]: row for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if not set(SOURCE_COLUMNS) <= set(columns) or columns["local_id"]["pk"] != 1:
                raise ValidationError("消息字段/局部ID结构未登记")
            names = {row["name"] for row in connection.execute("PRAGMA table_info(Name2Id)")}
            if "user_name" not in names:
                raise ValidationError("分片没有登记的发送者身份映射")
            size_columns = ("message_content", "source", "packed_info_data", "compress_content")
            size_sql = "+".join(f"COALESCE(length(CAST({name} AS BLOB)),0)" for name in size_columns)
            maximum = connection.execute(f'SELECT MAX({size_sql}) FROM "{table}"').fetchone()[0] or 0
            if maximum > MAX_RECORD_BYTES // 4:
                raise ValidationError("单条原始记录超过快照内存保护预算，未读取正文或交付快照")
            filename = f"part-{index:04d}.db"
            path = staging / filename
            sink = sqlite3.connect(path)
            count = 0
            try:
                sink.executescript(SCHEMA)
                sink.execute(f"PRAGMA application_id={SNAPSHOT_APPLICATION_ID}")
                sink.execute("PRAGMA user_version=1")
                source_count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                fields = ",".join("m." + name for name in SOURCE_COLUMNS)
                rows = connection.execute(f'SELECT {fields},n.user_name AS sender_username FROM "{table}" m LEFT JOIN Name2Id n ON n.rowid=m.real_sender_id ORDER BY m.local_id')
                for row in rows:
                    record = _record_from_row(row, label)
                    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    if len(encoded.encode("utf-8")) > MAX_RECORD_BYTES:
                        raise ValidationError("单条来源记录超过16MiB保护预算，未交付快照")
                    timestamp = row["create_time"] if type(row["create_time"]) is int else -1
                    sequence = row["sort_seq"] if type(row["sort_seq"]) is int else -1
                    sink.execute("INSERT INTO source_rows VALUES (?,?,?,?)", (row["local_id"], timestamp, sequence, encoded))
                    count += 1
                    if count % 1000 == 0 and guard:
                        guard()
                if count != source_count:
                    raise ConflictError("选定会话的来源计数不一致，未交付快照")
                sink.commit()
                if sink.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ConflictError("投影快照完整性检查失败")
            finally:
                sink.close()
            shards.append({"label": label, "file": filename, "records": count, "sha256": digest_file(path)})
        if guard:
            guard()
        manifest = {"format": "wechat-source-snapshot", "format_version": "1.0", "header": header,
                    "records": sum(shard["records"] for shard in shards), "shards": shards}
        path = staging / "snapshot.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows directory rename refuses existing destinations. Fail closed elsewhere.
        if os.name != "nt":
            raise ConflictError("当前快照交付仅验收Windows安全新目录语义")
        if staging.resolve().parent != staging_parent or output.exists() or staging.anchor.lower() != output.anchor.lower():
            raise ConflictError("快照目标在操作期间变化")
        os.rename(staging, output)
    return {"output": str(output), "records": manifest["records"], "shards": len(shards), "snapshot": True, "keys_written": False}


class SnapshotReader:
    def __init__(self, path):
        self.root = checked_path(path)
        if not self.root.is_dir():
            raise ValidationError("请选择登记快照目录")
        manifest_file = checked_path(self.root / "snapshot.json")
        if manifest_file.stat().st_size > 256 * 1024:
            raise ValidationError("快照清单超过保护预算")
        manifest_stamp = file_stamp(manifest_file)
        data = manifest_file.read_bytes()
        if file_stamp(manifest_file) != manifest_stamp:
            raise ConflictError("快照清单在读取期间变化")
        self.snapshot_id = hashlib.sha256(data).hexdigest()
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=_invalid_number)
        if not isinstance(manifest, dict) or set(manifest) != {"format", "format_version", "header", "records", "shards"} or (manifest["format"], manifest["format_version"]) != ("wechat-source-snapshot", "1.0"):
            raise ValidationError("未知的来源快照格式")
        self.header = _header(manifest["header"])
        self.manifest_file = manifest_file
        self.shards, self.stamps = [], {manifest_file: manifest_stamp}
        if not isinstance(manifest["shards"], list) or len(manifest["shards"]) > 512:
            raise ValidationError("快照分片清单不合法或超过预算")
        seen, count = set(), 0
        for shard in manifest["shards"]:
            if not isinstance(shard, dict) or set(shard) != {"label", "file", "records", "sha256"} or not isinstance(shard["label"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", shard["label"]) or shard["label"] in seen:
                raise ValidationError("分片身份未知或重复")
            seen.add(shard["label"])
            if not isinstance(shard["file"], str) or not re.fullmatch(r"part-[0-9]{4,6}\.db", shard["file"]):
                raise ValidationError("分片路径越出登记快照范围")
            path = checked_path(self.root / shard["file"])
            before = file_stamp(path)
            if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")) or digest_file(path) != shard["sha256"] or file_stamp(path) != before:
                raise ConflictError("快照分片未封存或摘要不一致")
            self.stamps[path] = before
            with self.connection(path) as conn:
                if conn.execute("PRAGMA application_id").fetchone()[0] != SNAPSHOT_APPLICATION_ID or conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValidationError("分片不是登记的来源投影，不能打开微信原库")
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                columns = tuple(row["name"] for row in conn.execute("PRAGMA table_info(source_rows)"))
                if tables != {"source_rows"} or columns != ("source_local_id", "order_time", "order_seq", "record_json"):
                    raise ValidationError("快照投影结构不符合登记Schema")
                actual = conn.execute("SELECT COUNT(*) FROM source_rows").fetchone()[0]
                if type(shard["records"]) is not int or actual != shard["records"] or conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ConflictError("分片记录数或完整性不一致")
            self.shards.append({**shard, "path": path})
            count += actual
        if type(manifest["records"]) is not int or count != manifest["records"]:
            raise ConflictError("快照总记录数不一致")
        self.total = count
        self.check_unchanged()

    @staticmethod
    def connection(path):
        from contextlib import contextmanager
        @contextmanager
        def opened():
            conn = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.enable_load_extension(False)
            try:
                yield conn
            finally:
                conn.close()
        return opened()

    def check_unchanged(self, *, full=False):
        for path, stamp in self.stamps.items():
            if file_stamp(path) != stamp or any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
                raise ConflictError("封存快照在读取期间变化，停止导入")
        if full:
            if digest_file(self.manifest_file) != self.snapshot_id:
                raise ConflictError("快照清单内容摘要变化，停止导入")
            for shard in self.shards:
                if digest_file(shard["path"]) != shard["sha256"]:
                    raise ConflictError("封存快照内容摘要变化，停止导入")

    def batches(self, *, positions=None, limit=1000, max_bytes=8 * 1024 * 1024):
        from contextlib import ExitStack
        if type(limit) is not int or not 1 <= limit <= 10000 or type(max_bytes) is not int or not 1024 <= max_bytes <= 32 * 1024 * 1024:
            raise ValidationError("批次行数或字节预算不合法")
        positions = dict(positions or {})
        if set(positions) - {shard["label"] for shard in self.shards}:
            raise ValidationError("恢复游标包含未知分片")
        with ExitStack() as stack:
            heap = []
            for shard in self.shards:
                conn = stack.enter_context(self.connection(shard["path"]))
                last = positions.get(shard["label"])
                if last is not None and (not isinstance(last, (list, tuple)) or len(last) != 3 or not all(type(value) is int for value in last)):
                    raise ValidationError("恢复游标不符合稳定排序键")
                where = " WHERE (order_time,order_seq,source_local_id)>(?,?,?)" if last is not None else ""
                cursor = conn.execute("SELECT * FROM source_rows" + where + " ORDER BY order_time,order_seq,source_local_id", last or ())
                row = cursor.fetchone()
                if row is not None:
                    key = (row["order_time"], row["order_seq"], shard["label"], row["source_local_id"])
                    heapq.heappush(heap, (key, row, cursor))
            records, size = [], 0
            while heap:
                self.check_unchanged()
                key, row, cursor = heapq.heappop(heap)
                encoded = row["record_json"]
                if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > MAX_RECORD_BYTES:
                    raise ValidationError("快照记录类型或大小不符合保护预算")
                count = len(encoded.encode("utf-8"))
                if count > max_bytes:
                    raise ValidationError("单条封存记录超过当前批次字节预算")
                if records and (len(records) >= limit or size + count > max_bytes):
                    yield records, dict(positions)
                    records, size = [], 0
                record = json.loads(encoded, object_pairs_hook=_unique_keys, parse_constant=_invalid_number)
                if not isinstance(record, dict) or record.get("source_database") != key[2] or record.get("local_id") != key[3]:
                    raise ValidationError("原记录与分片游标证据不一致")
                records.append(record)
                size += count
                positions[key[2]] = [key[0], key[1], key[3]]
                next_row = cursor.fetchone()
                if next_row is not None:
                    next_key = (next_row["order_time"], next_row["order_seq"], key[2], next_row["source_local_id"])
                    heapq.heappush(heap, (next_key, next_row, cursor))
            if records:
                yield records, dict(positions)
        self.check_unchanged(full=True)
