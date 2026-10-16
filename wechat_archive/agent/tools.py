"""只读、限定范围的应用工具；不接收路径或 SQL，不初始化归档。"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import threading
import hashlib
from types import SimpleNamespace

from ..database.db import APPLICATION_ID, MAX_READABLE_SCHEMA_VERSION
from ..errors import ArchiveError, ConflictError, NotFoundError, ValidationError
from ..exporter.readable import _local_path
from ..migration.manager import validate_schema
from ..services.browse_service import BrowseService
from ..services.chat_service import _id
from ..models.contracts import MessageRef

MAX_OUTPUT_CHARS = 48000
MAX_PAGE = 100
MAX_OFFSET = 1000000
ZONE = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ArchiveScope:
    path: Path
    user_id: int
    peer_id: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'path', _local_path(self.path))
        _id(self.user_id, 'user_id')
        if self.peer_id is not None:
            _id(abs(self.peer_id) if type(self.peer_id) is int else self.peer_id, 'peer_id')

    @property
    def key(self):
        return str(self.path), self.user_id, self.peer_id


class ReadOnlyArchive:
    def __init__(self, path):
        self.path = _local_path(path)
        if not self.path.is_file():
            raise NotFoundError('归档不存在；请先在软件中打开已归档数据。')
        with self.connection() as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            app_id = connection.execute('PRAGMA application_id').fetchone()[0]
            if app_id != APPLICATION_ID or not 1 <= version <= MAX_READABLE_SCHEMA_VERSION:
                raise ConflictError('仅支持本软件已有归档，不能打开微信原库或未知数据库。')
            validate_schema(connection, version)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.enable_load_extension(False)
        # 限制大库查询时间，不让模型调用无限占用软件。
        import time
        deadline = time.monotonic() + 5
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            yield connection
        finally:
            connection.close()


def _schema(properties, required=()):
    return {'type':'object', 'properties':properties, 'required':list(required), 'additionalProperties':False}


PAGE = {'limit':{'type':'integer','minimum':1,'maximum':MAX_PAGE},
        'offset':{'type':'integer','minimum':0,'maximum':MAX_OFFSET}}
FILTER = {'keyword':{'type':'string','minLength':1,'maxLength':200},
          'start_time':{'type':'string','description':'带时区的 ISO 8601，包含此时刻'},
          'end_time':{'type':'string','description':'带时区的 ISO 8601，不含此时刻'}}
SPECS = [
    {'type':'function','name':'archive_overview','description':'查看当前授权归档范围的消息数量及日期边界；覆盖所选会话已入库正文及附件元数据。','inputSchema':_schema({})},
    {'type':'function','name':'archive_users','description':'列出授权范围内的身份及联系人，返回稳定用户 ID。','inputSchema':_schema(PAGE)},
    {'type':'function','name':'archive_contacts','description':'列出所选身份的已归档会话，可用昵称或 wxid 关键词查找。当前会话模式仅返回已选对方。','inputSchema':_schema({**PAGE,'keyword':FILTER['keyword']})},
    {'type':'function','name':'archive_messages','description':'搜索或分页读取授权范围内原始文本，按 UTC 时间和消息 ID 升序；返回消息引用及 next_offset。peer_id 只能进一步缩小已授权范围。','inputSchema':_schema({**PAGE,**FILTER,'peer_id':{'type':'integer','minimum':-9223372036854775807}})},
    {'type':'function','name':'archive_message','description':'按消息 ID 获取原记录或长文本片段，核对引用；返回 sender/receiver、UTC 与北京时间。','inputSchema':_schema({'message_id':{'type':'integer','minimum':1},'content_offset':{'type':'integer','minimum':0},'content_limit':{'type':'integer','minimum':1,'maximum':8000}},('message_id',))},
]


class ArchiveTools:
    def __init__(self, scope: ArchiveScope):
        self.scope = scope
        self.database = ReadOnlyArchive(scope.path)
        self.archive_identity = self._archive_identity()
        self.browser = BrowseService(SimpleNamespace(database=self.database))
        self.lock = threading.Lock()
        with self.database.connection() as connection:
            self.rich = connection.execute('PRAGMA user_version').fetchone()[0] == 3
            for identity in (scope.user_id, scope.peer_id if scope.peer_id is None or scope.peer_id > 0 else None):
                if identity is not None and connection.execute('SELECT id FROM users WHERE id=?',(identity,)).fetchone() is None:
                    raise NotFoundError('所选身份或联系人不在当前归档内。')
            if scope.peer_id is not None and scope.peer_id < 0:
                if not self.rich or not connection.execute("SELECT 1 FROM chats c JOIN chat_members cm ON cm.chat_id=c.id WHERE c.id=? AND c.kind='group' AND cm.user_id=?",(-scope.peer_id,scope.user_id)).fetchone():
                    raise NotFoundError('所选身份不属于当前群聊。')

    @staticmethod
    def specs():
        # 不返回可被调用方修改的共享定义。
        return [{**item,'deferLoading':False} for item in json.loads(json.dumps(SPECS))]

    def _where(self):
        owner, peer = self.scope.user_id, self.scope.peer_id
        if peer is not None and peer < 0:
            return "m.chat_id=? AND EXISTS (SELECT 1 FROM chat_members cm JOIN chats c ON c.id=cm.chat_id WHERE cm.chat_id=m.chat_id AND cm.user_id=? AND c.kind='group')", (-peer,owner)
        if self.rich:
            from ..services.rich_reader import private_scope
            return private_scope(owner,peer)
        types = '' if self.rich else "m.msg_type='text' AND "
        if peer is None:
            return types+"m.receiver_id IS NOT NULL AND (m.sender_id=? OR m.receiver_id=?)", (owner, owner)
        return types+"m.receiver_id IS NOT NULL AND ((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))", (owner,peer,peer,owner)

    def execute(self, name, arguments):
        spec = next((item for item in SPECS if item['name'] == name), None)
        if spec is None:
            raise ValidationError('未登记的应用工具。')
        if not isinstance(arguments, dict):
            raise ValidationError('工具参数必须是对象。')
        schema = spec['inputSchema']
        if set(arguments) - set(schema['properties']):
            raise ValidationError('包含未登记的参数；不接受数据库路径、SQL 或其他身份。')
        if set(schema['required']) - set(arguments):
            raise ValidationError('缺少必需参数。')
        for key, value in arguments.items():
            rule = schema['properties'][key]
            if rule['type'] == 'integer':
                if type(value) is not int or value < rule.get('minimum',0) or value > rule.get('maximum',2**63-1):
                    raise ValidationError(f'{key} 超出允许范围。')
            elif not isinstance(value,str) or not value.strip() or '\x00' in value or len(value)>rule.get('maxLength',80):
                raise ValidationError(f'{key} 文本无效或超长。')
        with self.lock:
            result = getattr(self, name)(**arguments)
        result['scope'] = {'user_id':self.scope.user_id,'peer_id':self.scope.peer_id}
        result['evidence'] = '当前授权会话内已归档的消息正文与附件元数据；附件文件内容未上传。' if self.rich else '仅为当前归档的私聊文本；没有读取手机、群聊、媒体或未入库记录。'
        return result

    def archive_overview(self):
        where, params = self._where()
        with self.database.connection() as connection:
            row = connection.execute('SELECT COUNT(*) AS messages,MIN(create_time) AS first_time,MAX(create_time) AS last_time FROM messages m WHERE '+where,params).fetchone()
            return dict(row)

    def archive_users(self, limit=30, offset=0):
        where, params = self._where()
        # 仅返回授权范围涉及的身份，不暴露无关账号。
        sql = 'SELECT * FROM users WHERE id=? OR id IN (SELECT sender_id FROM messages m WHERE '+where+') OR id IN (SELECT receiver_id FROM messages m WHERE '+where+')'
        values = (self.scope.user_id,*params,*params)
        if self.scope.peer_id is not None and self.scope.peer_id > 0:
            sql += ' OR id=?'; values += (self.scope.peer_id,)
        with self.database.connection() as connection:
            connection.execute('BEGIN')
            total = connection.execute('SELECT COUNT(*) FROM ('+sql+')',values).fetchone()[0]
            rows = connection.execute(sql+' ORDER BY id LIMIT ? OFFSET ?',(*values,limit,offset)).fetchall()
        return self._page([dict(row) for row in rows],total,offset,limit)

    def archive_contacts(self, keyword=None, limit=30, offset=0):
        if self.rich:
            from ..services.rich_reader import RichReader
            rows=[x for x in RichReader(self.database).contacts(self.scope.user_id,keyword) if x['id']==self.scope.peer_id] if self.scope.peer_id is not None else [x for x in RichReader(self.database).contacts(self.scope.user_id,keyword) if x['id']>0]
            # Conversation summaries stay bounded; bodies and participants use their paged tools.
            fields=('id','wxid','nickname','kind','message_count','own_count','own_ratio','last_time')
            rows=[{key:row.get(key) for key in fields} for row in rows]
            return self._page(rows[offset:offset+limit],len(rows),offset,limit)
        where, params = self._where()
        owner = self.scope.user_id
        sql = ('SELECT u.id,u.wxid,u.nickname,COUNT(*) AS message_count,MAX(m.create_time) AS last_time '
               'FROM messages m JOIN users u ON u.id=CASE WHEN m.sender_id=? THEN m.receiver_id ELSE m.sender_id END WHERE '+where)
        values = (owner,*params)
        if keyword is not None:
            sql += ' AND (instr(u.nickname,?)>0 OR instr(u.wxid,?)>0)'; values += (keyword,keyword)
        sql += ' GROUP BY u.id'
        with self.database.connection() as connection:
            connection.execute('BEGIN')
            total = connection.execute('SELECT COUNT(*) FROM ('+sql+')',values).fetchone()[0]
            rows = connection.execute(sql+' ORDER BY last_time DESC,u.id LIMIT ? OFFSET ?',(*values,limit,offset)).fetchall()
        return self._page([dict(row) for row in rows],total,offset,limit)

    def archive_messages(self, peer_id=None, keyword=None, start_time=None, end_time=None, limit=30, offset=0):
        if peer_id is not None:_id(abs(peer_id),'peer_id')
        if self.scope.peer_id is not None and peer_id not in (None,self.scope.peer_id):
            raise ValidationError('查询不能超出当前会话范围。')
        if self.rich:
            from ..services.rich_reader import RichReader
            chosen=self.scope.peer_id if self.scope.peer_id is not None else peer_id
            if self.scope.peer_id is None and chosen is not None and chosen < 0:
                raise ValidationError('全部私聊范围不能扩大到群聊，请先选择该群。')
            if chosen is None:
                # The identity-wide mode explicitly authorizes private chats only.
                where,params=self._where()
                from ..services.chat_service import _time
                for key,value in (('keyword',keyword),('start',start_time),('end',end_time)):
                    if value is not None:
                        where+= ' AND instr(m.content,?)>0' if key=='keyword' else ' AND m.create_time'+('>=?' if key=='start' else '<?')
                        params+= (value if key=='keyword' else _time(value),)
                if start_time and end_time and _time(start_time)>=_time(end_time):raise ValidationError('开始时间必须早于结束时间')
                with self.database.connection() as conn:
                    conn.execute('BEGIN')
                    total=conn.execute('SELECT COUNT(*) FROM messages m WHERE '+where,params).fetchone()[0]
                    items=[dict(x) for x in conn.execute('SELECT m.*,s.nickname sender_name,r.nickname receiver_name FROM messages m LEFT JOIN users s ON s.id=m.sender_id LEFT JOIN users r ON r.id=m.receiver_id WHERE '+where+' ORDER BY m.create_time,m.id LIMIT ? OFFSET ?',(*params,limit,offset))]
                result={'items':items,'total':total}
            else:result=RichReader(self.database).messages(self.scope.user_id,chosen,keyword,start_time,end_time,limit,offset)
            return self._page([self._message(row,0,2000) for row in result['items']],result['total'],offset,limit)
        result = self.browser.messages(self.scope.user_id,peer_id=self.scope.peer_id if self.scope.peer_id is not None else peer_id,
                                       keyword=keyword,start_time=start_time,end_time=end_time,limit=limit,offset=offset)
        rows = [self._message(row,0,2000) for row in result['items']]
        return self._page(rows,result['total'],offset,limit)

    def archive_message(self, message_id, content_offset=0, content_limit=8000):
        where, params = self._where()
        with self.database.connection() as connection:
            row = connection.execute('SELECT m.*,s.nickname AS sender_name,r.nickname AS receiver_name FROM messages m LEFT JOIN users s ON s.id=m.sender_id LEFT JOIN users r ON r.id=m.receiver_id WHERE m.id=? AND '+where,(message_id,*params)).fetchone()
        if row is None:
            raise NotFoundError('当前授权范围内没有此消息。')
        row=dict(row)
        if self.rich:
            with self.database.connection() as connection:
                row['attachments']=[dict(x) for x in connection.execute('SELECT media.* FROM message_media mm JOIN media ON media.id=mm.media_id WHERE mm.message_id=?',(message_id,))]
        if content_offset > len(row['content'] or '['+row['msg_type']+']'):
            raise ValidationError('正文偏移超出消息长度。')
        return {'item':self._message(dict(row),content_offset,content_limit)}

    def _archive_identity(self):
        info = self.scope.path.stat()
        key = json.dumps([str(self.scope.path), info.st_dev, info.st_ino], ensure_ascii=False).encode('utf-8')
        return hashlib.sha256(key).hexdigest()

    def resolve_reference(self, reference):
        ref = MessageRef.from_dict(reference)
        if ref.archive_identity != self.archive_identity or self._archive_identity() != self.archive_identity:
            raise ConflictError('消息引用属于其他归档或文件已被替换，请重新查询。')
        item = self.archive_message(ref.message_id)['item']
        if item['reference']['revision'] != ref.revision:
            raise ConflictError('引用的消息已修改，请重新查询原记录。')
        return item

    def _message(self, row, offset, limit):
        row = dict(row)
        # Local file locations never leave the application through model tools.
        row['attachments']=[{k:x.get(k) for k in ('kind','availability','variant','size_bytes')} for x in row.get('attachments',[])]
        row['sender_name']=row.get('sender_name') or ('系统' if row.get('msg_type')=='system' and not (row.get('content') or '').startswith('[发送者未映射]') else '来源身份未映射')
        if self._archive_identity() != self.archive_identity:
            raise ConflictError('归档文件已被替换，请重新选择读取范围。')
        row['reference'] = MessageRef.from_row(self.archive_identity, row).to_dict()
        text = row['content'] or '['+row['msg_type']+']'; row['content'] = text[offset:offset+limit]
        row['content_length'] = len(text); row['content_offset'] = offset
        row['content_truncated'] = offset+len(row['content']) < len(text)
        row['next_content_offset'] = offset+len(row['content']) if row['content_truncated'] else None
        try:
            row['display_time'] = datetime.fromisoformat(row['create_time'].replace('Z','+00:00')).astimezone(ZONE).isoformat()
        except ValueError as error:
            raise ConflictError('归档时间损坏，不能猜测消息时间。') from error
        row['citation'] = f"[消息 #{row['id']}]"
        return row

    @staticmethod
    def _page(rows, total, offset, limit):
        bounded = []; size = 0
        for row in rows:
            count = len(json.dumps(row,ensure_ascii=False))
            if bounded and size+count > MAX_OUTPUT_CHARS:
                break
            bounded.append(row); size += count
        more = offset+len(bounded) < total
        return {'items':bounded,'total':total,'offset':offset,'limit':limit,'has_more':more,
                'next_offset':offset+len(bounded) if more else None,
                'ordering':'create_time ASC, id ASC' if rows and 'content' in rows[0] else '接口所声明的顺序',
                'pagination_note':'每页为独立只读快照；导入或编辑后请重新查询。'}

    def reply(self, name, arguments):
        try:
            result = self.execute(name, arguments)
            return {'success':True,'contentItems':[{'type':'inputText','text':json.dumps(result,ensure_ascii=False)}]}
        except (ArchiveError, sqlite3.Error, OSError) as error:
            return {'success':False,'contentItems':[{'type':'inputText','text':str(error)}]}
