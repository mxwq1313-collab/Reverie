"""只读离线 SQLite 快照，拒绝日志侧文件，不恢复或写入来源。"""

import hashlib
import sqlite3
from abc import ABC, abstractmethod

from .detector import SQLITE_HEADER, local_path
from .errors import AndroidSourceError


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quote_identifier(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AndroidSourceError("invalid_identifier", "数据库标识符不合法")
    return '"' + value.replace('"', '""') + '"'


class DatabaseReader(ABC):
    @abstractmethod
    def list_tables(self):
        pass

    @abstractmethod
    def table_columns(self, table):
        pass

    @abstractmethod
    def schema_report(self):
        pass


class SQLiteDatabaseReader(DatabaseReader):
    def __init__(self, path):
        self.path = local_path(path)
        if not self.path.is_file():
            raise AndroidSourceError("invalid_database_path", "数据库路径必须是普通文件")
        self._conn = None
        self._before = None

    def __enter__(self):
        for suffix in ("-wal", "-shm", "-journal"):
            if self.path.with_name(self.path.name + suffix).exists():
                raise AndroidSourceError("incomplete_snapshot", "快照带有 WAL/SHM/journal 文件；不能忽略日志或修改来源，请提供已合并的离线快照")
        with self.path.open("rb") as handle:
            header = handle.read(100)
        if len(header) < 100 or header[:16] != SQLITE_HEADER:
            raise AndroidSourceError("not_plain_sqlite", "不是可读取的明文 SQLite；解密接口未实现")
        if header[18:20] != b"\x01\x01":
            raise AndroidSourceError("unsupported_journal", "当前只接受独立 rollback-journal 模式快照，不猜测 WAL 完整性")
        self._before = (self.path.stat().st_size, self.path.stat().st_mtime_ns, file_hash(self.path))
        try:
            self._conn = sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=5)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA query_only=ON")
            self._conn.execute("PRAGMA trusted_schema=OFF")
            self._conn.enable_load_extension(False)
            self._conn.set_authorizer(self._authorize)
            if self._conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise AndroidSourceError("corrupt_database", "SQLite 完整性检查失败")
        except Exception:
            if self._conn:
                self._conn.close()
                self._conn = None
            raise
        return self

    @staticmethod
    def _authorize(action, arg1, arg2, database, trigger):
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION}
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() == "load_extension":
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_PRAGMA:
            if str(arg1).lower() in {"table_info", "table_xinfo"}:
                return sqlite3.SQLITE_OK
            if str(arg1).lower() in {"quick_check", "integrity_check", "user_version", "query_only"} and arg2 is None:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def __exit__(self, kind, error, trace):
        if self._conn:
            self._conn.close()
            self._conn = None
        after = (self.path.stat().st_size, self.path.stat().st_mtime_ns, file_hash(self.path))
        if after != self._before:
            raise AndroidSourceError("source_changed", "读取期间源快照发生变化，解析结果作废")

    @property
    def sha256(self):
        return self._before[2]

    def _connection(self):
        if self._conn is None:
            raise AndroidSourceError("reader_closed", "请在 reader 上下文中读取数据库")
        return self._conn

    def list_tables(self):
        return [row[0] for row in self._connection().execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    def table_columns(self, table):
        if table not in self.list_tables():
            raise AndroidSourceError("missing_table", f"表不存在：{table}")
        return [dict(row) for row in self._connection().execute(f"PRAGMA table_info({quote_identifier(table)})")]

    def schema_report(self):
        connection = self._connection()
        tables = {}
        for table in self.list_tables():
            sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
            tables[table] = {"columns": self.table_columns(table), "virtual": bool(sql and "CREATE VIRTUAL TABLE" in sql.upper())}
        return {"database": str(self.path), "sqlite_version": sqlite3.sqlite_version, "user_version": connection.execute("PRAGMA user_version").fetchone()[0], "read_only": True, "sha256": self.sha256, "tables": tables}

    def iter_rows(self, table, columns, *, order_by=None):
        names = {row["name"] for row in self.table_columns(table)}
        if any(name not in names for name in columns) or order_by is not None and order_by not in names:
            raise AndroidSourceError("missing_field", "请求字段不属于该表")
        query = "SELECT " + ",".join(quote_identifier(name) for name in columns) + " FROM " + quote_identifier(table)
        if order_by:
            query += " ORDER BY " + quote_identifier(order_by)
        for row in self._connection().execute(query):
            yield dict(row)
