"""文件数据库、事务边界、备份与逐级迁移。"""

import os
import sqlite3
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Iterator
from datetime import datetime, timezone
from uuid import uuid4

from ..errors import ConflictError, ValidationError
from ..migration.manager import LATEST_VERSION, MAX_SUPPORTED_VERSION, execute_script, migrate, validate_schema

SCHEMA_VERSION = LATEST_VERSION
MAX_READABLE_SCHEMA_VERSION = MAX_SUPPORTED_VERSION
APPLICATION_ID = 0x57434841  # WCHA：避免误把其他 SQLite 文件当成聊天库。


def default_data_dir() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    if (project_root / "pyproject.toml").is_file():
        return project_root / "data"
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "WeChatArchive"


class Database:
    def __init__(self, path: str | Path | None = None):
        if path is not None and str(path) == ":memory:":
            raise ValidationError("归档数据库需要文件路径，不能使用 :memory:")
        self.path = Path(path if path is not None else default_data_dir() / "chat.db").expanduser().resolve()
        self.last_backup_path = None

    def _backup_before_migration(self, version):
        folder = self.path.parent / "migration_backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = folder / f"{self.path.stem}.v{version}.{stamp}.{uuid4().hex[:12]}.bak.db"
        # 另一只读连接可在当前 RESERVED 写锁下读取升级前快照。
        original = sqlite3.connect(self.path)
        backup = sqlite3.connect(target)
        try:
            original.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ConflictError("升级前备份完整性检查未通过，未修改原库")
        finally:
            backup.close()
            original.close()
        self.last_backup_path = target
        return target

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """成功时提交、异常时回滚，所有情况下关闭连接。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """空库初始化；受支持的旧库先备份，再在一个事务中升级。"""
        with self.connection() as conn:
            # 锁内检查和建表，避免两个进程同时首次初始化。
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            app_id = conn.execute("PRAGMA application_id").fetchone()[0]
            objects = list(conn.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ))
            newly_created = False
            if version == 0 and app_id == 0 and not objects:
                schema = files("wechat_archive.database").joinpath("init.sql").read_text(encoding="utf-8")
                execute_script(conn, schema)
                conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                conn.execute("PRAGMA user_version = 1")
                version = 1
                newly_created = True
            elif app_id != APPLICATION_ID or not 1 <= version <= MAX_READABLE_SCHEMA_VERSION:
                raise ConflictError("这不是受支持的归档数据库；请指定新的文件，已有文件未被改写")
            validate_schema(conn, version)
            if version < SCHEMA_VERSION:
                backup = None if newly_created else self._backup_before_migration(version)
                migrate(conn, version, backup_path=backup)
