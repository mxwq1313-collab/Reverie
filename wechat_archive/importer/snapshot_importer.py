"""Resumable explicit streaming import through the existing shared message writer."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from ..errors import ArchiveError, ConflictError, ValidationError
from ..models.contracts import MessageKind, SourceCapabilities
from ..wechat_source.mapper import normalize_export
from ..wechat_source.snapshot import SnapshotReader
from .base_importer import BaseImporter, StrictImportAbort
from .import_report import ImportIssue, ImportReport, utc_now
from .validator import DocumentError, validate_document

CAPABILITIES = SourceCapabilities("snapshot", ("wechat-source-snapshot-1.0",), ("private",), (MessageKind.TEXT,),
                                  stable_source_identity=True, streaming=True,
                                  input_requirement="已封存且摘要/计数通过的选定私聊消息投影")


class _BatchWriter(BaseImporter):
    def load(self, path):
        raise ValidationError("批次只能来自已验证快照")


class SnapshotImporter:
    def __init__(self, database, *, report_dir=None, strict=False):
        if strict:
            raise ValidationError("封存快照使用明确逐批提交模式，不能套用整文件严格原子导入")
        self.writer = _BatchWriter(database, report_dir=report_dir, strict=True)

    def import_file(self, path):
        return self.import_snapshot(path)

    def preview(self, path):
        reader = SnapshotReader(path)
        return {"kind": "snapshot", "database": str(self.writer.database.path), "source_records": reader.total,
                "users": 2, "chats": 1, "messages": None, "issues": [], "retained": None,
                "note": "这是封存来源记录数，支持文本数需逐批核验；导入需要Schema3副本，已提交批次可恢复",
                "source_capabilities": CAPABILITIES.to_dict()}

    def _document(self, reader, records):
        provenance = {"snapshot_id": reader.snapshot_id, "snapshot_directory": str(reader.root)}
        try:
            loaded = normalize_export({**reader.header, "records": records}, provenance)
        except DocumentError as error:
            metadata = getattr(error, "source_metadata", {}).get("metadata", {}).get("external_parse", {})
            if metadata.get("quarantined_count") != len(records):
                raise
            loaded = normalize_export({**reader.header, "records": []}, provenance)
            loaded.payload["source"]["metadata"]["external_parse"] = metadata
        document = validate_document(loaded.payload)
        if document.issues:
            raise DocumentError("快照批次的标准记录校验失败，未提交此批")
        document.identity_strategy = "source-id-v1"
        return document

    def import_snapshot(self, path, *, batch_size=1000, max_bytes=8 * 1024 * 1024, cancel_event=None, progress=None, after_batch=None, restart=False):
        database = self.writer.database
        if not database.path.is_file():
            raise ValidationError("流式导入需要已存在的Schema3升级副本，默认归档不自动升级")
        with database.connection() as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] != 3:
                raise ValidationError("请先创建并打开Schema3升级副本，再导入封存历史快照")
        database.initialize()
        reader = SnapshotReader(path)
        if database.path == reader.root or reader.root in database.path.parents:
            raise ValidationError("目标归档不能放在来源快照内部")
        logs = self.writer.report_dir.resolve()
        if logs == reader.root or reader.root in logs.parents:
            raise ValidationError("导入报告不能写入封存来源快照内部")
        logs.mkdir(parents=True, exist_ok=True)
        from tempfile import TemporaryFile
        with TemporaryFile(dir=logs):
            pass
        report = ImportReport(str(reader.root), "wechat-snapshot", str(database.path), identity_strategy="source-id-v1",
                              source_capabilities=CAPABILITIES.to_dict())
        with database.connection() as conn:
            archive_id = conn.execute("SELECT archive_identity FROM archive_metadata").fetchone()[0]
        with database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            archive_revision = conn.execute("SELECT content_revision FROM archive_metadata").fetchone()[0]
            existing = conn.execute("SELECT * FROM import_sessions WHERE snapshot_id=? AND status!='complete' ORDER BY updated_at DESC LIMIT 1", (reader.snapshot_id,)).fetchone()
            if restart and existing is not None:
                conn.execute("UPDATE import_sessions SET status='cancelled',updated_at=? WHERE id=?", (utc_now(), existing["id"]))
                existing = None
            if existing is None:
                session_id = hashlib.sha256((archive_id + reader.snapshot_id + uuid4().hex).encode("ascii")).hexdigest()
                state = {"snapshot_id": reader.snapshot_id, "positions": {}, "counts": {"raw": 0, "added": 0, "duplicated": 0, "quarantined": 0, "source_duplicates": 0}, "batch": 0, "archive_revision": archive_revision}
                conn.execute("INSERT INTO import_sessions(id,snapshot_id,status,cursor,updated_at) VALUES (?,?,'active',?,?)", (session_id, reader.snapshot_id, json.dumps(state), utc_now()))
            else:
                session_id = existing["id"]
                if existing["snapshot_id"] != reader.snapshot_id:
                    raise ConflictError("导入会话快照身份冲突")
                state = json.loads(existing["cursor"])
                if set(state) != {"snapshot_id", "positions", "counts", "batch", "archive_revision"} or state.get("snapshot_id") != reader.snapshot_id or not isinstance(state.get("positions"), dict) or not isinstance(state.get("counts"), dict):
                    raise ConflictError("保存的导入游标不符合快照身份")
                if set(state["counts"]) != {"raw", "added", "duplicated", "quarantined", "source_duplicates"} or any(type(value) is not int or value < 0 for value in state["counts"].values()):
                    raise ConflictError("保存的导入计数不合法")
                if type(state["batch"]) is not int or state["batch"] < 0 or type(state["archive_revision"]) is not int or state["archive_revision"] < 0:
                    raise ConflictError("保存的批次或归档版本不合法")
                if archive_revision != state["archive_revision"]:
                    raise ConflictError("归档在批次间发生变化，请先核对已有数据，不覆盖或盲目恢复")
                conn.execute("UPDATE import_sessions SET status='active',updated_at=? WHERE id=?", (utc_now(), session_id))
        starting_counts = dict(state["counts"])
        active_messages, active_raw, session_owned = 0, 0, True
        try:
            for records, positions in reader.batches(positions=state["positions"], limit=batch_size, max_bytes=max_bytes):
                if cancel_event is not None and cancel_event.is_set():
                    report.status = "cancelled"
                    break
                active_raw = len(records)
                document = self._document(reader, records)
                active_raw, active_messages = len(records), document.messages_total
                details = document.source["metadata"]["external_parse"]
                retained = details["quarantined_count"]
                duplicates = sum(item["parse_status"] == "duplicate_source_record" for item in details["quarantine_records"])
                batch_report = ImportReport(str(reader.root), "wechat-snapshot-batch", str(database.path), messages=document.messages_total, identity_strategy="source-id-v1")
                batch_id = str(state["batch"] + 1)
                digest = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
                with database.connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    current = conn.execute("SELECT cursor,status FROM import_sessions WHERE id=?", (session_id,)).fetchone()
                    if json.loads(current["cursor"]) != state or current["status"] != 'active':
                        session_owned = False
                        raise ConflictError("另一导入操作已推进同一会话，请重新恢复")
                    if conn.execute("SELECT content_revision FROM archive_metadata").fetchone()[0] != state["archive_revision"]:
                        raise ConflictError("归档在批次间变化，未提交当前批次")
                    self.writer._persist(document, batch_report, connection=conn)
                    counts = dict(state["counts"])
                    counts["raw"] += len(records)
                    counts["added"] += batch_report.success_count
                    counts["duplicated"] += batch_report.duplicated_count
                    counts["quarantined"] += retained - duplicates
                    counts["source_duplicates"] += duplicates
                    revision = conn.execute("SELECT content_revision FROM archive_metadata").fetchone()[0]
                    next_state = {"snapshot_id": reader.snapshot_id, "positions": positions, "counts": counts, "batch": int(batch_id), "archive_revision": revision}
                    conn.execute("INSERT INTO import_batches(session_id,batch_id,digest,record_count,committed_at) VALUES (?,?,?,?,?)", (session_id, batch_id, digest, len(records), utc_now()))
                    conn.execute("UPDATE import_sessions SET status='active',last_batch_id=?,cursor=?,updated_at=? WHERE id=?", (batch_id, json.dumps(next_state), utc_now(), session_id))
                state = next_state
                active_raw, active_messages = 0, 0
                if progress:
                    progress({"session_id": session_id, "processed": counts["raw"], "total": reader.total, "added": counts["added"]})
                if after_batch:
                    after_batch(int(batch_id))  # Controlled crash probe; not supplied by source data.
            else:
                reader.check_unchanged(full=True)
                if state["counts"]["raw"] != reader.total:
                    raise ConflictError("提交游标与来源总计数不一致，不能宣称完成")
                report.status = "partial" if state["counts"]["quarantined"] else "success"
        except (ArchiveError, ValueError, OSError, sqlite3.Error) as error:
            report.status = "failed"
            report.issues.append(ImportIssue("file", None, "snapshot_import_failed", str(error)))
        finally:
            counts = state["counts"]
            report.success_count = counts["added"] - starting_counts["added"]
            report.duplicated_count = counts["duplicated"] - starting_counts["duplicated"]
            report.failed_count = active_messages if report.status == 'failed' else 0
            report.messages = report.success_count + report.duplicated_count + report.failed_count
            report.finished_at = utc_now()
            report.source_metadata = {"snapshot_id": reader.snapshot_id, "snapshot_directory": str(reader.root), "session_id": session_id,
                                      "source_records": reader.total, "processed_records": counts["raw"], "quarantined_count": counts["quarantined"],
                                      "source_duplicate_records": counts["source_duplicates"], "committed_batches": state["batch"], "session_counts": counts,
                                      "failed_batch_records": active_raw, "mode": "streaming-partial-commit"}
            if counts["quarantined"]:
                report.warnings.append(ImportIssue("file", None, "snapshot_records_retained", f"{counts['quarantined']}条未支持原记录保留在封存快照，未伪装为文字"))
            if session_owned:
                with database.connection() as conn:
                    status = "complete" if report.status in {"success", "partial"} else "cancelled" if report.status == "cancelled" else "failed"
                    conn.execute("UPDATE import_sessions SET status=?,updated_at=? WHERE id=? AND cursor=? AND status!='complete'", (status, utc_now(), session_id, json.dumps(state)))
            report.save(self.writer.report_dir)
        return report
