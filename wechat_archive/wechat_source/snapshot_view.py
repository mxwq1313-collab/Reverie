"""Per-database stable SDK views; no decryption or source writes here."""
from pathlib import Path
import sqlite3
import os
import time
import logging

from ..errors import ArchiveError


class SnapshotRetry(RuntimeError):
    pass


def stamp(path):
    info = Path(path).stat()
    return info.st_size, info.st_mtime_ns, info.st_ino


def source_version(path):
    path = Path(path)
    wal = Path(str(path) + '-wal')
    return stamp(path), stamp(wal) if wal.exists() else None


class StableReadViews:
    """Compose before the pinned SDK. Retain its verified local view per job.

    A source must be stable while the SDK opens it, rather than throughout
    slow media acquisition. Different shards have individual capture times.
    """
    def _open(self, rel):
        views = self.__dict__.setdefault('_read_views', {})
        if rel in views:
            path, version, factory = views[rel]
            if stamp(path) != version:
                raise ArchiveError('本次读取副本发生变化，已停止；请重新读取。')
            conn = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
            conn.row_factory = sqlite3.Row
            conn.text_factory = factory
            conn.execute('PRAGMA query_only=ON')
            return conn
        source = self._db_path(rel)
        for attempt in range(3):
            conn = None
            try:
                before = source_version(source)
                class Warnings(logging.Filter):
                    count = 0
                    def filter(self, record):
                        if record.levelno >= logging.WARNING:
                            self.count += 1
                            return False
                        return True
                warnings = Warnings()
                logger = logging.getLogger('readonly_wechat_source')
                logger.addFilter(warnings)
                try:
                    conn = super()._open(rel)
                finally:
                    logger.removeFilter(warnings)
                if warnings.count:
                    raise SnapshotRetry('读取组件报告未合并日志或较旧副本。')
                if source_version(source) == before:
                    path = Path(conn.execute('PRAGMA database_list').fetchone()[2]).resolve()
                    if not path.is_relative_to(Path(self.workdir).resolve()):
                        raise ArchiveError('读取组件没有返回本次工作目录内的副本。')
                    # The decrypted file can retain WAL mode in its SQLite header.
                    # Close the SDK connection before any application query can
                    # create empty WAL/SHM sidecars; immutable opens never do so.
                    factory = conn.text_factory
                    conn.close()
                    conn = None
                    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
                        raise ArchiveError('读取副本尚未封存，未导入。')
                    version = stamp(path)
                    conn = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
                    conn.row_factory = sqlite3.Row
                    conn.text_factory = factory
                    if not all(row[0] == 'ok' for row in conn.execute('PRAGMA quick_check')):
                        raise ArchiveError('读取副本完整性校验失败，未导入。')
                    if stamp(path) != version:
                        raise ArchiveError('读取副本在校验期间变化，未导入。')
                    views[rel] = (path, version, factory)
                    conn.execute('PRAGMA query_only=ON')
                    return conn
            except (OSError, sqlite3.DatabaseError, RuntimeError) as error:
                if attempt == 2:
                    if conn is not None:
                        conn.close()
                    reason = str(error) if isinstance(error, SnapshotRetry) else '来源不可读或校验失败。'
                    raise ArchiveError('来源分片无法建立稳定副本（已重试3次），未导入；'+reason) from None
            except Exception:
                if conn is not None:
                    conn.close()
                raise
            if conn is not None:
                conn.close()
            # Invalidate only this operation's local SDK stamp, never the source.
            local_stamp = Path(self.workdir) / (rel.replace(os.sep, '__') + '.stamp')
            if local_stamp.resolve().is_relative_to(Path(self.workdir).resolve()):
                local_stamp.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(.08)
        raise ArchiveError('来源在建立副本时持续变化，已重试3次；请稍后重新读取。')

    def _message_dbs(self):
        if '_read_message_files' not in self.__dict__:
            files = tuple(super()._message_dbs())
            if any(rel not in self._keys for rel in files):
                raise ArchiveError('消息分片未全部核验，未导入。')
            self._read_message_files = files
        return list(self._read_message_files)

    def check_read_views(self):
        for path, version, _ in self.__dict__.get('_read_views', {}).values():
            if stamp(path) != version or any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
                raise ArchiveError('本次读取副本发生变化或未封存，已停止。')
        if '_read_message_files' in self.__dict__:
            import re
            current = {rel for rel, _, _ in self._collect_db_files()
                       if re.fullmatch(r'message[/\\]message_\d+\.db', rel)}
            if current != set(self._read_message_files):
                raise ArchiveError('读取期间消息分片清单变化，请重新读取，避免遗漏。')
