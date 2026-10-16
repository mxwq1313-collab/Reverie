"""Explicit-copy rich-schema foundation. Default archives remain version 2."""
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
from uuid import uuid4
import re
import sqlite3
from functools import lru_cache

from ..errors import ConflictError

EXTRA_COLUMNS = {
    "media": ("id", "kind", "relative_uri", "sha256", "size_bytes", "availability", "variant"),
    "message_media": ("message_id", "media_id", "ordinal"),
    "message_sources": ("id", "message_id", "namespace", "source_key", "source_hash", "identity_strategy"),
    "import_sessions": ("id", "snapshot_id", "status", "last_batch_id", "cursor", "updated_at"),
    "import_batches": ("session_id", "batch_id", "digest", "record_count", "committed_at"),
    "archive_metadata": ("singleton", "archive_identity", "content_revision"),
}

REVISION_TRIGGERS = {"messages_revision_insert", "messages_revision_update", "messages_revision_delete", "messages_chat_receiver_insert", "messages_chat_receiver_update"}


def _sql_key(statement):
    # Preserve SQL string literal case; GROUP and group are different values.
    return re.sub(r"\s+", " ", statement).strip().rstrip(";").strip()


@lru_cache(maxsize=1)
def _expected_triggers():
    script = files("wechat_archive.migration").joinpath("sql", "003_rich_archive.sql").read_text(encoding="utf-8")
    result, statement = {}, ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            match = re.match(r"\s*CREATE TRIGGER (\w+)", statement)
            if match:
                result[match.group(1)] = _sql_key(statement)
            statement = ""
    return result


def validate_extra(conn):
    rows = conn.execute("SELECT singleton,archive_identity,content_revision FROM archive_metadata").fetchall()
    if len(rows) != 1 or rows[0]["singleton"] != 1 or not isinstance(rows[0]["archive_identity"], str) or not re.fullmatch(r"[a-f0-9]{64}", rows[0]["archive_identity"]) or type(rows[0]["content_revision"]) is not int or rows[0]["content_revision"] < 0:
        raise ConflictError("归档元信息损坏，未使用新版本归档")
    triggers = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    if REVISION_TRIGGERS != triggers:
        raise ConflictError("新归档缺少内容版本维护触发器")
    expected = _expected_triggers()
    for row in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"):
        if row["name"] in expected and _sql_key(row["sql"]) != expected[row["name"]]:
            raise ConflictError("新归档维护触发器定义与登记版本不符")
    expected_keys = {
        "message_media": {("message_id", "messages", "id", "CASCADE"), ("media_id", "media", "id", "RESTRICT")},
        "message_sources": {("message_id", "messages", "id", "CASCADE")},
        "import_batches": {("session_id", "import_sessions", "id", "CASCADE")},
    }
    for table, expected in expected_keys.items():
        actual = {(row["from"], row["table"], row["to"], row["on_delete"]) for row in conn.execute(f"PRAGMA foreign_key_list({table})")}
        if actual != expected:
            raise ConflictError("新归档外键定义与登记结构不符")


def upgrade_to_3(conn, execute_script):
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 0 or not conn.in_transaction:
        raise ConflictError("副本升级需要事务外预先关闭外键，且当前持有迁移事务")
    sequences = {row["name"]: row["seq"] for row in conn.execute("SELECT name,seq FROM sqlite_sequence WHERE name IN ('messages','chats')")}
    index_sql = [row[0] for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name IN ('messages','chats') AND sql IS NOT NULL")]
    script = files("wechat_archive.migration").joinpath("sql", "003_rich_archive.sql").read_text(encoding="utf-8")
    execute_script(conn, script)
    for statement in index_sql:
        conn.execute(statement)
    for name, sequence in sequences.items():
        if conn.execute("SELECT 1 FROM sqlite_sequence WHERE name=?", (name,)).fetchone():
            conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name=?", (sequence, name))
        else:
            conn.execute("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (name, sequence))
    identity = hashlib.sha256(uuid4().bytes).hexdigest()
    conn.execute("INSERT INTO archive_metadata(singleton,archive_identity,content_revision) VALUES (1,?,0)", (identity,))
    conn.execute("INSERT INTO message_sources(message_id,namespace,source_key,source_hash,identity_strategy) SELECT id,source,source_id,source_hash,'legacy-preserved' FROM messages WHERE source IS NOT NULL AND source_id IS NOT NULL")
    stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    conn.execute("INSERT INTO migration_history(version,name,applied_at,backup_path) VALUES (3,'rich_archive_copy',?,NULL)", (stamp,))
    conn.execute("PRAGMA user_version=3")
