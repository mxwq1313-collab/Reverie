"""共享导入管线：读取 → 校验 → 中间模型 → 单事务写库 → 报告。"""

import sqlite3
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from contextlib import nullcontext

from ..database import Database
from ..database.db import default_data_dir
from ..database.hashing import ensure_private_chat, has_external_source_key, message_hash, private_chat_key
from ..errors import ArchiveError
from .import_report import ImportIssue, ImportReport, utc_now
from .validator import DocumentError, validate_document


class ReportWriteError(ArchiveError):
    def __init__(self, report, original):
        self.report = report
        super().__init__(f"导入结果为 {report.status}，但无法保存报告：{original}；请检查报告目录，不要盲目重试")


class StrictImportAbort(ArchiveError):
    pass


def default_report_dir():
    root = Path(__file__).resolve().parents[2]
    return root / "import_logs" if (root / "pyproject.toml").is_file() else default_data_dir() / "import_logs"


class BaseImporter(ABC):
    format_name = "base"

    def __init__(self, database=None, *, report_dir=None, strict=False):
        self.database = database if isinstance(database, Database) else Database(database)
        self.report_dir = Path(report_dir) if report_dir is not None else default_report_dir()
        self.strict = strict

    @abstractmethod
    def load(self, path):
        """返回 LoadedDocument；新解析器只需实现这一步。"""

    def import_file(self, path):
        started = time.perf_counter()
        path = Path(path).expanduser().resolve()
        report = ImportReport(str(path), self.format_name, str(self.database.path), strict=self.strict)
        # 先验证日志目录可写，避免明知不能记录仍开始写库。
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=self.report_dir):
                pass
        except OSError as exc:
            raise ReportWriteError(report, exc) from exc
        try:
            loaded = self.load(path)
            if isinstance(loaded.payload, dict):
                for key in ("users", "chats", "messages"):
                    rows = loaded.payload.get(key)
                    if isinstance(rows, list):
                        setattr(report, key, len(rows))
            document = validate_document(loaded.payload, loaded.line_numbers)
            if loaded.identity_strategy not in {"legacy-content", "source-id-v1"}:
                raise DocumentError("来源适配器声明了未支持的消息身份策略")
            document.identity_strategy = loaded.identity_strategy
            report.identity_strategy = loaded.identity_strategy
            if loaded.capabilities is not None:
                report.source_capabilities = loaded.capabilities.to_dict()
            report.source_namespace = document.source["id"]
            report.source_metadata = document.source
            report.users, report.chats, report.messages = document.users_total, document.chats_total, document.messages_total
            report.issues.extend(document.issues)
            report.users_failed_count = sum(issue.entity == "user" for issue in document.issues)
            report.chats_failed_count = sum(issue.entity == "chat" for issue in document.issues)
            report.failed_count = sum(issue.entity == "message" for issue in document.issues)
            if self.strict and document.issues:
                report.failed_count = report.messages
                report.issues.append(ImportIssue("file", None, "strict_rejected", "严格模式发现错误，整份文件未写入"))
            else:
                self.database.initialize()
                report.migration_backup = str(self.database.last_backup_path) if self.database.last_backup_path else None
                self._persist(document, report)
                if report.issues:
                    report.status = "partial" if report.success_count or report.duplicated_count or report.users_created_count or report.users_reused_count else "failed"
                else:
                    report.status = "success"
        except (DocumentError, OSError, UnicodeError, sqlite3.Error, ArchiveError, ValueError) as exc:
            report.status = "failed"
            report.failed_count = report.messages - report.success_count - report.duplicated_count
            report.source_metadata.update(getattr(exc, "source_metadata", {}))
            report.issues.append(ImportIssue("file", None, getattr(exc, "code", "import_failed"), str(exc)))
        report.finished_at = utc_now()
        report.duration_seconds = round(time.perf_counter() - started, 6)
        try:
            report.save(self.report_dir)
        except OSError as exc:
            raise ReportWriteError(report, exc) from exc
        return report

    def _persist(self, document, report, *, connection=None):
        user_ids, chat_ids, seen_hashes = {}, {}, set()
        counters = dict(users_created_count=0, users_reused_count=0, chats_created_count=0, chats_reused_count=0, success_count=0, duplicated_count=0)
        try:
            with (self.database.connection() if connection is None else nullcontext(connection)) as conn:
                if connection is None:
                    conn.execute("BEGIN IMMEDIATE")
                elif not conn.in_transaction:
                    raise ArchiveError("批次写入必须与状态更新共享已有事务")
                extended = conn.execute("PRAGMA user_version").fetchone()[0] >= 3
                legacy_checks = {}
                for user in document.users:
                    existing = conn.execute("SELECT id,nickname,avatar FROM users WHERE wxid=?", (user.external_id,)).fetchone()
                    if existing is not None:
                        user_ids[user.id] = existing["id"]
                        counters["users_reused_count"] += 1
                        if existing["nickname"] != user.nickname or existing["avatar"] != user.avatar:
                            report.warnings.append(ImportIssue("user", None, "metadata_preserved", "外部标识已存在，保留数据库里的昵称和头像", record_id=user.id))
                    else:
                        cursor = conn.execute("INSERT INTO users(wxid,nickname,avatar) VALUES (?,?,?)", (user.external_id, user.nickname, user.avatar))
                        user_ids[user.id] = cursor.lastrowid
                        counters["users_created_count"] += 1
                for chat in document.chats:
                    index = chat.index
                    members = tuple(user_ids[value] for value in chat.participant_ids)
                    first, second = members[0], members[-1]
                    alias = conn.execute("SELECT c.chat_key FROM chat_sources s JOIN chats c ON c.id=s.chat_id WHERE s.source=? AND s.external_id=?", (document.source["id"], chat.external_id)).fetchone()
                    if alias is not None and alias[0] != private_chat_key(first, second):
                        report.chats_failed_count += 1
                        report.issues.append(ImportIssue("chat", index, "chat_source_conflict", "会话外部标识已绑定其他参与者", "external_id", chat.id))
                        continue
                    chat_id, created = ensure_private_chat(conn, first, second, chat.title)
                    chat_ids[chat.id] = chat_id
                    counters["chats_created_count" if created else "chats_reused_count"] += 1
                    conn.execute("INSERT OR IGNORE INTO chat_sources(source,external_id,chat_id) VALUES (?,?,?)", (document.source["id"], chat.external_id, chat_id))
                for message in document.messages:
                    index = message.index
                    if message.chat_id not in chat_ids:
                        report.failed_count += 1
                        report.issues.append(ImportIssue("message", index, "invalid_chat", f"第{index}条消息失败：对应会话写入失败", "chat_id", message.id, message.line))
                        continue
                    sender, receiver = user_ids[message.sender_id], user_ids[message.receiver_id]
                    digest = message_hash(sender, receiver, message.timestamp, message.content)
                    if document.identity_strategy == "source-id-v1":
                        decision, code, reason = self._source_identity_decision(conn, document, message, sender, receiver, chat_ids[message.chat_id], digest, legacy_checks)
                        if decision == "conflict":
                            report.failed_count += 1
                            report.issues.append(ImportIssue("message", index, code, reason, "source_id", message.id, message.line))
                            continue
                        duplicate = decision == "duplicate"
                    else:
                        duplicate = digest in seen_hashes or conn.execute("SELECT 1 FROM messages WHERE message_hash=? LIMIT 1", (digest,)).fetchone() is not None
                    if duplicate:
                        counters["duplicated_count"] += 1
                        seen_hashes.add(digest)
                        continue
                    conn.execute("SAVEPOINT import_message")
                    try:
                        inserted = conn.execute("INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,chat_id,message_hash,source,source_id,source_hash,external_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (sender, receiver, message.timestamp, message.content, message.type, chat_ids[message.chat_id], digest, document.source["id"], message.source_id or message.id, message.source_hash, message.id))
                        if extended:
                            conn.execute("INSERT INTO message_sources(message_id,namespace,source_key,source_hash,identity_strategy) VALUES (?,?,?,?,?)", (inserted.lastrowid, document.source["id"], message.source_id or message.id, message.source_hash, document.identity_strategy))
                    except sqlite3.IntegrityError as exc:
                        if not conn.in_transaction:
                            raise  # RAISE(ROLLBACK) 等已中断整批事务。
                        conn.execute("ROLLBACK TO import_message")
                        report.failed_count += 1
                        report.issues.append(ImportIssue("message", index, "database_constraint", f"第{index}条消息失败：数据库约束冲突（{exc}）", record_id=message.id, line=message.line))
                    else:
                        counters["success_count"] += 1
                        seen_hashes.add(digest)
                    finally:
                        if conn.in_transaction:
                            conn.execute("RELEASE import_message")
                if self.strict and report.issues:
                    raise StrictImportAbort("严格模式遇到写入错误，整批数据已回滚")
        except (OSError, sqlite3.Error, ArchiveError):
            report.rolled_back = True
            report.failed_count = report.messages
            raise
        for key, value in counters.items():
            setattr(report, key, value)

    @staticmethod
    def _source_identity_decision(conn, document, message, sender, receiver, chat_id, digest, legacy_checks=None):
        source = document.source["id"]
        if not has_external_source_key(source, message.source_id, message.id):
            return "conflict", "invalid_source_identity", "来源复合消息身份不符合登记契约，未写入"
        existing = conn.execute("SELECT * FROM messages WHERE source=? AND source_id=? LIMIT 2", (source, message.source_id)).fetchall()
        if len(existing) > 1:
            return "conflict", "source_identity_ambiguous", "同一来源身份对应多条已有记录，需核对，未覆盖或合并"
        if existing:
            row = existing[0]
            actual = (row["sender_id"], row["receiver_id"], row["create_time"], row["content"], row["msg_type"], row["chat_id"])
            expected = (sender, receiver, message.timestamp, message.content, message.type, chat_id)
            if actual == expected:
                return "duplicate", None, None
            return "conflict", "source_identity_conflict", "同一来源消息身份的双方、时间或原文与已有归档冲突，未覆盖"
        if legacy_checks is None or digest not in legacy_checks:
            candidates = conn.execute("SELECT source,source_id,external_id FROM messages WHERE message_hash=?", (digest,))
            ambiguous = any(not has_external_source_key(row["source"], row["source_id"], row["external_id"]) for row in candidates)
            if legacy_checks is not None:
                legacy_checks[digest] = ambiguous
        else:
            ambiguous = legacy_checks[digest]
        if ambiguous:
            return "conflict", "legacy_identity_ambiguous", "相同双方、时间与正文已有缺少登记来源身份的旧记录，无法判定同一事件；未静默去重或追加"
        return "insert", None, None
