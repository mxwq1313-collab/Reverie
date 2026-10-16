"""Independent SQLite vector index; exact cosine scan, transactional refresh."""

from contextlib import contextmanager
import heapq
import json
from pathlib import Path
import sqlite3
import struct
import time

from ..errors import ConflictError, NotFoundError, ValidationError
from ..exporter.readable import _local_path
from .providers import unit_vector
from .source import bounded_int, digest

APP_ID = 0x4B4E5831


class KnowledgeIndex:
    def __init__(self, path, source, provider):
        self.path = _local_path(path)
        self.source = source
        self.provider = provider
        if self.path == source.scope.path or (self.path.exists() and self.path.samefile(source.scope.path)):
            raise ValidationError("知识索引必须使用独立文件，不能选择原归档。")

    @contextmanager
    def _connection(self, create=False):
        new = False
        if not self.path.exists():
            if not create:
                raise NotFoundError("知识索引尚未创建，请先更新索引。")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open('xb'):
                    pass
                new = True
            except FileExistsError:
                pass
        connection = sqlite3.connect(self.path.as_uri()+("?mode=rw" if create else "?mode=ro"), uri=True, timeout=3)
        connection.row_factory = sqlite3.Row
        try:
            if new:
                connection.executescript(f"PRAGMA application_id={APP_ID}; PRAGMA user_version=1; "
                    "CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL); "
                    "CREATE TABLE chunks(id TEXT PRIMARY KEY,payload TEXT NOT NULL,vector BLOB NOT NULL);")
            if (connection.execute('PRAGMA application_id').fetchone()[0] != APP_ID
                    or connection.execute('PRAGMA user_version').fetchone()[0] != 1
                    or {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")} != {'metadata','chunks'}):
                raise ConflictError("所选文件不是本软件的知识索引；请选择新索引路径。")
            if connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]:
                raise ConflictError("知识索引含未知触发器或视图，请选择新索引路径。")
            for table, columns in (('metadata', ['key','value']), ('chunks',['id','payload','vector'])):
                if [r[1] for r in connection.execute('PRAGMA table_info('+table+')')] != columns:
                    raise ConflictError("知识索引结构不匹配，请选择新路径重建。")
            if create:
                connection.execute('PRAGMA secure_delete=ON')
            else:
                connection.execute('PRAGMA query_only=ON')
            yield connection
        except sqlite3.DatabaseError as error:
            raise ConflictError("知识索引损坏，请删除派生索引后重新创建。") from error
        finally:
            connection.close()

    @staticmethod
    def _meta(connection):
        try:
            rows = {r['key']: json.loads(r['value']) for r in connection.execute('SELECT * FROM metadata')}
            if rows and set(rows) != {'binding','source_revision','messages','chunks','updated_utc'}:
                raise ValueError()
            if rows and (not isinstance(rows['binding'],dict) or 'scope_id' not in rows['binding']):
                raise ValueError()
            return rows
        except (ValueError, TypeError) as error:
            raise ConflictError("知识索引元数据损坏，请重建。") from error

    def _binding(self):
        return {'scope_id': self.source.scope_id, 'processing': self.source.processing,
                'embedding': self.provider.descriptor(), 'index_version': 1, 'metric': 'cosine-exact'}

    def sync(self, cancel=None, progress=None, rebuild=False):
        start = time.perf_counter()
        binding = self._binding()
        embedded = reused = deleted = 0
        with self._connection(create=True) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                old = self._meta(connection)
                if old and old['binding']['scope_id'] != self.source.scope_id:
                    raise ConflictError("索引属于其他授权范围，请为当前范围选择独立索引。")
                compatible = old.get('binding') == binding and not rebuild
                if old and not compatible:
                    connection.execute('DELETE FROM chunks')
                connection.execute('CREATE TEMP TABLE seen(id TEXT PRIMARY KEY)')
                connection.execute('CREATE TEMP TABLE pending(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
                # Snapshot read is completed before slow model calls, avoiding long archive locks.
                with self.source.snapshot() as snap:
                    revision, messages = snap.revision, snap.messages
                    count = 0
                    for chunk in snap.chunks():
                        if cancel and cancel():
                            raise ConflictError("索引更新已取消，保留上次完整索引。")
                        key = chunk.reference.key
                        connection.execute('INSERT INTO seen VALUES(?)', (key,))
                        payload = json.dumps(chunk.to_dict(), ensure_ascii=False, separators=(',',':'))
                        exists = compatible and connection.execute('SELECT 1 FROM chunks WHERE id=?',(key,)).fetchone()
                        if exists:
                            # Names can change without affecting the MessageRef.
                            connection.execute('UPDATE chunks SET payload=? WHERE id=?',(payload,key))
                            reused += 1
                        else:
                            connection.execute('INSERT INTO pending VALUES(?,?)',(key,payload))
                        count += 1
                        if progress and count%128 == 0:
                            progress(f"读取原文片段 {count} 条")
                cursor = connection.execute('SELECT * FROM pending ORDER BY id')
                while True:
                    if cancel and cancel():
                        raise ConflictError("索引更新已取消，保留上次完整索引。")
                    batch = cursor.fetchmany(32)
                    if not batch:
                        break
                    vectors = self.provider.embed([json.loads(r['payload'])['text'] for r in batch])
                    if not isinstance(vectors, list) or len(vectors) != len(batch):
                        raise ValidationError("向量批次数量不一致，索引未提交。")
                    for row, values in zip(batch, vectors):
                        vector = unit_vector(values, binding['embedding']['dimensions'])
                        connection.execute('INSERT OR REPLACE INTO chunks VALUES(?,?,?)',
                            (row['id'],row['payload'],struct.pack('<'+'d'*len(vector),*vector)))
                        embedded += 1
                    if progress:
                        progress(f"计算向量 {embedded} 条，复用 {reused} 条")
                deleted = connection.execute('DELETE FROM chunks WHERE id NOT IN (SELECT id FROM seen)').rowcount
                with self.source.snapshot() as fresh:
                    if fresh.revision != revision:
                        raise ConflictError("原文在索引更新期间发生变化，请重试；本次未提交。")
                if self._binding() != binding:
                    raise ConflictError("模型版本变化，索引未提交。")
                for key,value in {'binding':binding,'source_revision':revision,'messages':messages,'chunks':count,
                                  'updated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}.items():
                    connection.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
                if cancel and cancel():
                    raise ConflictError("索引更新已取消，保留上次完整索引。")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return {'chunks':count,'messages':messages,'embedded':embedded,'reused':reused,'deleted':deleted,
                'source_revision':revision,'embedding':binding['embedding'],
                'elapsed_seconds':round(time.perf_counter()-start,3)}

    def status(self):
        with self._connection() as connection:
            meta = self._meta(connection)
        if not meta:
            return {'ready':False,'reason':'索引未完成'}
        with self.source.snapshot() as snap:
            current = snap.revision
        return {**meta,'ready':meta['binding']==self._binding() and meta['source_revision']==current,
                'reason':'当前范围、模型和原文版本均需匹配'}

    def search(self, query, limit=5, min_score=0.2):
        if not isinstance(query,str) or not query.strip() or len(query)>1000 or '\0' in query:
            raise ValidationError("检索内容须为 1–1000 字符。")
        bounded_int(limit,'limit',1,20)
        if type(min_score) not in (int,float) or not 0 <= min_score <= 1:
            raise ValidationError("检索阈值无效。")
        binding = self._binding()
        query_batch = self.provider.embed([query])
        if not isinstance(query_batch,list) or len(query_batch) != 1:
            raise ValidationError("查询向量批次无效。")
        query_vector = unit_vector(query_batch[0],binding['embedding']['dimensions'])
        best = []
        with self._connection() as connection:
            connection.execute('BEGIN')
            meta = self._meta(connection)
            if not meta or meta['binding'] != binding:
                raise ConflictError("范围、处理方式或模型与索引不一致，请更新索引。")
            with self.source.snapshot() as snap:
                if snap.revision != meta['source_revision']:
                    raise ConflictError("原文已变化，请更新索引后再检索。")
            for row in connection.execute('SELECT * FROM chunks'):
                dims = binding['embedding']['dimensions']
                if len(row['vector']) != dims*8:
                    raise ConflictError("索引向量维度损坏，请重建。")
                vector = unit_vector(list(struct.unpack('<'+'d'*dims,row['vector'])), dims)
                score = sum(a*b for a,b in zip(query_vector,vector))
                if score < min_score:
                    continue
                item = (score,row['id'],row['payload'])
                if len(best)<limit:
                    heapq.heappush(best,item)
                elif item>best[0]:
                    heapq.heapreplace(best,item)
        hits = []
        for score,_,payload in sorted(best,reverse=True):
            try:
                item = json.loads(payload)
                fresh = self.source.resolve(item['reference']).to_dict()
                if fresh != item:
                    raise ConflictError("索引片段与原文不一致，请重建。")
            except (ValueError, KeyError, TypeError) as error:
                raise ConflictError("索引片段损坏，请重建。") from error
            hits.append({'score':round(score,6),'chunk':fresh})
        with self.source.snapshot() as snap:
            if snap.revision != meta['source_revision']:
                raise ConflictError("检索期间原文变化，请更新索引。")
        if self._binding() != binding:
            raise ConflictError("检索期间模型变化，请更新索引。")
        return {'hits':hits,'source_revision':meta['source_revision'],'embedding':binding['embedding'],
                'scope_id':self.source.scope_id,'method':'cosine-exact','inference':False}
