"""受支持版本的逐级迁移，调用者持有事务；已有记录不删除。"""

import sqlite3
from datetime import datetime, timezone
from importlib.resources import files

from ..database.hashing import ensure_private_chat, message_hash
from ..errors import ConflictError

LATEST_VERSION = 2
MAX_SUPPORTED_VERSION = 3  # Explicit copy only; default initialization stays at 2.
BASE_COLUMNS = {
    "users": ("id", "wxid", "nickname", "avatar"),
    "messages": ("id", "sender_id", "receiver_id", "create_time", "content", "msg_type"),
}
CURRENT_COLUMNS = {
    **BASE_COLUMNS,
    "messages": BASE_COLUMNS["messages"] + ("chat_id", "message_hash", "source", "source_id", "source_hash", "external_id"),
    "chats": ("id", "chat_key", "kind", "title"),
    "chat_members": ("chat_id", "user_id"),
    "chat_sources": ("source", "external_id", "chat_id"),
    "migration_history": ("version", "name", "applied_at", "backup_path"),
}


def execute_script(conn, script):
    # 不用 executescript，避免它隐式提交调用者的迁移事务。
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ""
    if statement.strip():
        raise ConflictError("迁移 SQL 包含未结束的语句")


def validate_schema(conn, version):
    if version not in {1, 2, 3}:
        raise ConflictError("归档数据库版本未登记")
    columns = BASE_COLUMNS if version == 1 else CURRENT_COLUMNS
    if version == 3:
        from .schema3 import EXTRA_COLUMNS
        columns = {**CURRENT_COLUMNS, "messages": CURRENT_COLUMNS["messages"] + ("revision",), **EXTRA_COLUMNS}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if tables != set(columns):
        raise ConflictError("归档数据库表结构与声明版本不匹配")
    for table, expected in columns.items():
        actual = tuple(row["name"] for row in conn.execute(f"PRAGMA table_info({table})"))
        if actual != expected:
            raise ConflictError(f"归档数据库的 {table} 字段与声明版本不匹配")
    required = {("sender_id", "users", "id", "RESTRICT"), ("receiver_id", "users", "id", "RESTRICT")}
    if version >= 2:
        required.add(("chat_id", "chats", "id", "RESTRICT"))
    actual = {(row["from"], row["table"], row["to"], row["on_delete"]) for row in conn.execute("PRAGMA foreign_key_list(messages)")}
    if actual != required:
        raise ConflictError("归档数据库的消息外键不完整")
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ConflictError("归档数据库已有外键违规，请先检查原文件")
    if version == 3:
        from .schema3 import validate_extra
        validate_extra(conn)


def _upgrade_to_2(conn):
    script = files("wechat_archive.migration").joinpath("sql", "002_import_engine.sql").read_text(encoding="utf-8")
    execute_script(conn, script)
    # 分批读取旧消息，保留相同内容的旧重复记录及其原 ID。
    cursor = conn.execute("SELECT id, sender_id, receiver_id, create_time, content FROM messages ORDER BY id")
    chat_cache = {}
    while rows := cursor.fetchmany(1000):
        updates = []
        for row in rows:
            pair = tuple(sorted({row["sender_id"], row["receiver_id"]}))
            if pair not in chat_cache:
                chat_cache[pair] = ensure_private_chat(conn, row["sender_id"], row["receiver_id"])[0]
            # 版本 1 的公共接口已使用带时区 UTC；拒绝损坏时间，不猜测。
            try:
                stamp = datetime.fromisoformat(row["create_time"].replace("Z", "+00:00"))
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("缺少时区")
                normalized = stamp.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
            except (ValueError, OverflowError) as exc:
                raise ConflictError(f"旧消息 {row['id']} 时间不合法，迁移已回滚：{exc}") from exc
            updates.append((chat_cache[pair], message_hash(row["sender_id"], row["receiver_id"], normalized, row["content"]), normalized, row["id"]))
        conn.executemany("UPDATE messages SET chat_id=?, message_hash=?, create_time=? WHERE id=?", updates)


MIGRATIONS = {2: ("import_engine", _upgrade_to_2)}


def migrate(conn, version, *, backup_path=None):
    for target in range(version + 1, LATEST_VERSION + 1):
        name, upgrade = MIGRATIONS[target]
        upgrade(conn)
        validate_schema(conn, target)
        stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        conn.execute("INSERT INTO migration_history(version,name,applied_at,backup_path) VALUES (?,?,?,?)", (target, name, stamp, str(backup_path) if backup_path else None))
        conn.execute(f"PRAGMA user_version={target}")
