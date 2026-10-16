"""Verified Schema 1/2 -> 3 copy; original archive is opened read-only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

from ..errors import ConflictError, NotFoundError, ValidationError
from .manager import BASE_COLUMNS, CURRENT_COLUMNS, execute_script, migrate, validate_schema
from .schema3 import upgrade_to_3


def _path(value):
    raw = str(value)
    if "://" in raw or raw.startswith(("\\\\", "//")) or any(ord(char) < 32 for char in raw) or ".." in Path(raw).parts:
        raise ValidationError("迁移只接受明确本机路径，不接受URI、控制字符或路径穿越")
    return Path(value).expanduser().resolve()


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stamp(path):
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _reject_sidecars(path):
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ConflictError("归档仍有SQLite日志/共享文件，请关闭写入并取得完整离线归档后创建升级副本")


def _signatures(conn, columns, *, normalize_v1=False, history_version=None):
    result = {}
    for table, names in columns.items():
        fields = ",".join(names)
        digest = hashlib.sha256()
        count = 0
        where, params = (" WHERE version<=?", (history_version,)) if table == "migration_history" and history_version is not None else ("", ())
        for row in conn.execute(f"SELECT {fields} FROM {table}{where} ORDER BY {fields}", params):
            values = list(row)
            if normalize_v1 and table == "messages":
                index = names.index("create_time")
                stamp = datetime.fromisoformat(values[index].replace("Z", "+00:00"))
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ConflictError("旧消息时间不含时区，无法验证副本迁移")
                values[index] = stamp.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
            encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def upgrade_archive_copy(source, target):
    """Create a new target. Unknown/live archives and existing targets fail closed."""
    from ..database.db import APPLICATION_ID
    source, target = _path(source), _path(target)
    if not source.is_file():
        raise NotFoundError("来源归档不存在；迁移不会创建来源文件")
    if source == target or target.exists():
        raise ConflictError("升级目标必须是新的独立文件，不能覆盖原库或既有文件")
    _reject_sidecars(source)
    original_stamp, original_digest = _stamp(source), _file_digest(source)
    connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.enable_load_extension(False)
        connection.execute("BEGIN")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or version not in {1, 2}:
            raise ConflictError("只支持已登记Schema1/2归档创建Schema3副本，未知或已升级文件不改写")
        validate_schema(connection, version)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ConflictError("来源归档完整性检查失败")
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
            raise ConflictError("来源含未经登记的触发器或视图，副本迁移明确拒绝，原文件保留")
        columns = BASE_COLUMNS if version == 1 else CURRENT_COLUMNS
        before = _signatures(connection, columns, normalize_v1=version == 1)
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        required_bytes = pages * page_size * 2 + 16 * 1024 * 1024
        if shutil.disk_usage(target.parent).free < required_bytes:
            raise ConflictError("目标磁盘空间不足，未创建升级目标")
        with tempfile.TemporaryDirectory(prefix=".archive-upgrade-", dir=target.parent) as staging_dir:
            staged = Path(staging_dir) / "archive.db"
            destination = sqlite3.connect(staged)
            destination.row_factory = sqlite3.Row
            try:
                connection.backup(destination)
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ConflictError("独立备份完整性检查失败，未迁移")
                destination.execute("PRAGMA foreign_keys=OFF")
                destination.execute("BEGIN IMMEDIATE")
                try:
                    if version == 1:
                        migrate(destination, 1)
                    upgrade_to_3(destination, execute_script)
                    validate_schema(destination, 3)
                    after = _signatures(destination, columns, history_version=version)
                    if before != after:
                        raise ConflictError("副本旧数据逐表摘要/数量不一致，迁移回滚")
                    if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ConflictError("升级副本完整性检查失败，迁移回滚")
                    destination.commit()
                except BaseException:
                    destination.rollback()
                    raise
                destination.execute("PRAGMA foreign_keys=ON")
                if destination.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ConflictError("升级副本外键检查失败，未交付")
                archive_identity = destination.execute("SELECT archive_identity FROM archive_metadata WHERE singleton=1").fetchone()[0]
            finally:
                destination.close()
            _reject_sidecars(source)
            if _stamp(source) != original_stamp or _file_digest(source) != original_digest:
                raise ConflictError("来源文件在迁移期间变化，未交付升级目标")
            with staged.open("r+b") as stream:
                os.fsync(stream.fileno())
            target_digest = _file_digest(staged)
            # Atomic create-if-absent on the same local filesystem; no overwrite race.
            try:
                os.link(staged, target)
            except FileExistsError as error:
                raise ConflictError("升级目标在操作期间被创建，保留已有文件") from error
            except OSError as error:
                raise ConflictError("目标文件系统不支持安全创建新副本，未覆盖任何文件") from error
        return {"status": "success", "source": str(source), "target": str(target), "source_version": version,
                "target_version": 3, "source_sha256": original_digest, "target_sha256": target_digest,
                "archive_identity": archive_identity, "legacy_tables": before, "source_unchanged": True,
                "compatibility": "新版可读旧库；旧版不能打开Schema3；默认仍创建Schema2"}
    finally:
        connection.close()
