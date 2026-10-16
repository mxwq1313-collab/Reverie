"""Small revision-bound caches for read-only browsing, shared by read snapshots."""
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import threading
from ..errors import ConflictError


def file_token(path):
    path=Path(path);stamps=[]
    for item in (path,Path(str(path)+'-wal')):
        stat=item.stat() if item.exists() else None
        stamps.append((stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns) if stat else None)
    return str(path),tuple(stamps)


class CancelledReader:
    def __init__(self,reader,cancel):self.reader=reader;self.path=reader.path;self.version=reader.version;self.cancel=cancel
    @contextmanager
    def connection(self):
        if self.cancel.is_set():raise InterruptedError('读取已替换')
        with self.reader.connection() as connection:
            connection.set_progress_handler(lambda:int(self.cancel.is_set()),1000)
            yield connection


class ReadCache:
    def __init__(self):self.lock=threading.RLock();self.readers={};self.values=OrderedDict()
    def reader(self,path,factory):
        token=file_token(path)
        with self.lock:
            if token not in self.readers:
                reader=factory(path)
                if token!=file_token(path):raise ConflictError('读取期间归档已变化，请重试')
                self.readers={token:reader}
            return self.readers[token]
    def value(self,path,kind,args,work,cancel=None):
        if cancel and cancel.is_set():raise InterruptedError('读取已替换')
        token=file_token(path);key=(token,kind,tuple((type(arg),arg) for arg in args))
        try:hash(key)
        except TypeError:return work()
        with self.lock:
            if key in self.values:self.values.move_to_end(key);return deepcopy(self.values[key])
        value=work()
        if token!=file_token(path):raise ConflictError('读取期间归档已变化，请重试')
        rows=value.get('items',[]) if isinstance(value,dict) else value if isinstance(value,list) else []
        size=sum(len(str(row.get('content','')))+len(str(row.get('last_message',''))) for row in rows)
        if len(rows)<=5000 and size<=1_000_000 and not (cancel and cancel.is_set()):
            with self.lock:
                self.values[key]=deepcopy(value)
                while len(self.values)>10:self.values.popitem(last=False)
        return value
