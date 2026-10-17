"""Versioned group/media exchange using the existing authoritative archive transaction."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from urllib.parse import quote,unquote
import shutil
import tempfile

from ..database.db import Database
from ..database.hashing import ensure_private_chat
from ..errors import ConflictError, ValidationError
from ..migration.manager import validate_schema
from ..services.chat_service import _time
from .import_report import ImportReport, ImportIssue, utc_now

FORMAT = 'sixu-chat-exchange'
KINDS = {'text','image','emoji','video','audio','file','location','system'}


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def media_root(database):
    path = Path(database)
    return path.parent / (path.stem + '.media')


def resource_path(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative or any(ord(c)<32 for c in relative):
        raise ValidationError('附件必须是资源目录中的相对路径')
    value = PurePosixPath(relative)
    if value.is_absolute() or '..' in value.parts:
        raise ValidationError('附件路径不能离开资源目录')
    root = Path(root)
    if root.is_symlink() or root.exists() and getattr(root.lstat(),'st_file_attributes',0)&0x400:
        raise ValidationError('附件资源根不能是链接或重解析点')
    root = root.resolve()
    path = root.joinpath(*value.parts)
    for part in (path, *path.parents):
        if part == root: break
        if part.is_symlink() or part.exists() and getattr(part.lstat(),'st_file_attributes',0)&0x400:
            raise ValidationError('附件不接受链接或重解析点')
    if not path.resolve().is_relative_to(root):
        raise ValidationError('附件路径越界')
    return path


def ready_media(database, row):
    path = resource_path(media_root(database), row['relative_uri'])
    if row['availability'] != 'ready' or not path.is_file() or path.stat().st_size != row['size_bytes'] or sha_file(path) != row['sha256']:
        raise ConflictError('附件缺失或摘要已变化，请重新导入原始附件')
    return path


def create_rich_archive(path):
    from ..services import ChatService
    from ..migration.copy_upgrade import upgrade_archive_copy
    target = Path(path).resolve()
    if target.exists(): raise ConflictError('新建归档不能覆盖已有文件')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.sixu-new-',dir=target.parent) as temporary:
        source = Path(temporary)/'base.db'
        assert source.parent.resolve().parent == target.parent
        ChatService(source)
        return upgrade_archive_copy(source, target)


class RichImporter:
    def __init__(self,database,*,report_dir=None,strict=False):
        self.database=Path(database);self.report_dir=report_dir;self.strict=strict

    def load_payload(self,path):
        path=Path(path)
        if path.stat().st_size>64*1024*1024:raise ValidationError('交换文件超过64 MiB，请使用分片导入')
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value,dict) or value.get('format')!=FORMAT or value.get('format_version')!='2.0':
            raise ValidationError('请选择思绪聊天交换2.0文件，未知格式不能猜测解析')
        if not isinstance(value.get('namespace'),str) or not value['namespace'].strip():raise ValidationError('交换文件缺少来源命名空间')
        for name in ('users','chats','messages'):
            if not isinstance(value.get(name),list) or len(value[name])>100000:raise ValidationError('交换文件列表或条数不合法')
        users={};chats={}
        for row in value['users']:
            if not isinstance(row,dict) or not all(isinstance(row.get(k),str) and row[k].strip() for k in ('id','nickname')) or row['id'] in users:
                raise ValidationError('参与者ID或姓名无效、重复')
            users[row['id']]=row
        for row in value['chats']:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row['id'] in chats or row.get('kind') not in ('private','group'):
                raise ValidationError('会话ID或类型无效、重复')
            members=row.get('members')
            if not isinstance(members,list) or not members or len(set(members))!=len(members) or any(x not in users for x in members):raise ValidationError('会话成员未登记或重复')
            if row['kind']=='private' and len(members)>2:raise ValidationError('私聊不能包含两人以上')
            chats[row['id']]=row
        seen=set()
        for row in value['messages']:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row.get('chat_id') not in chats:raise ValidationError('消息缺少稳定ID或会话')
            identity=(row['chat_id'],row['id'])
            if identity in seen:raise ValidationError('交换文件包含重复来源消息ID')
            seen.add(identity);chat=chats[row['chat_id']]
            if row.get('sender_id') not in chat['members'] and not (row.get('kind')=='system' and row.get('sender_id') is None):raise ValidationError('消息发送者不属于登记会话')
            if chat['kind']=='private' and row.get('receiver_id') not in chat['members']:raise ValidationError('私聊接收者未登记')
            if not isinstance(row.get('create_time'),str) or not row['create_time']:raise ValidationError('消息缺少明确的带时区时间')
            _time(row['create_time'])
            if row.get('content') is not None and not isinstance(row['content'],str):raise ValidationError('正文必须为文本或空值')
            if row.get('content') and len(row['content'].encode('utf-8'))>16*1024*1024:raise ValidationError('单条消息超过16MiB预算')
            if row.get('kind')=='text' and not (row.get('content') or '').strip():raise ValidationError('文本消息缺少正文')
            if not isinstance(row.get('attachments',[]),list):raise ValidationError('附件列表无效')
            for item in row.get('attachments',[]):
                if not isinstance(item,dict) or item.get('kind','file') not in ('image','video','audio','file'):raise ValidationError('附件类型无效')
                if item.get('variant','original') not in ('original','compressed','thumbnail'):raise ValidationError('附件变体无效')
                if item.get('path'):resource_path(path.parent,item['path'])
        return value

    def preview(self,path):
        value=self.load_payload(path)
        return {'kind':'rich','users':len(value['users']),'chats':len(value['chats']),'messages':len(value['messages']),
                'groups':sum(x['kind']=='group' for x in value['chats']),'attachments':sum(len(x.get('attachments',[])) for x in value['messages']),
                'issues':[],'source':str(path),'requires_schema':3}

    @staticmethod
    def bind_media(conn,message_id,attachments):
        for ordinal,item in enumerate(attachments):
            old=conn.execute('SELECT media.* FROM message_media mm JOIN media ON media.id=mm.media_id WHERE mm.message_id=? AND mm.ordinal=?',(message_id,ordinal)).fetchone()
            if old and old['availability']=='ready':
                if item['availability']!='ready':continue
                if old['sha256']!=item['sha256'] or old['kind']!=item['kind']:raise ConflictError('同一来源附件内容冲突，已保留原归档')
                continue
            conn.execute('INSERT OR IGNORE INTO media(id,kind,relative_uri,sha256,size_bytes,availability,variant) VALUES (:id,:kind,:relative_uri,:sha256,:size_bytes,:availability,:variant)',item)
            if old:conn.execute('DELETE FROM message_media WHERE message_id=? AND ordinal=?',(message_id,ordinal))
            conn.execute('INSERT OR IGNORE INTO message_media(message_id,media_id,ordinal) VALUES (?,?,?)',(message_id,item['id'],ordinal))

    def import_file(self,path):
        path=Path(path).resolve();before=(path.stat().st_size,path.stat().st_mtime_ns,sha_file(path));value=self.load_payload(path)
        report=ImportReport(source=str(path),format=FORMAT+'-2.0',database=str(self.database),strict=self.strict)
        report.users=len(value['users']);report.chats=len(value['chats']);report.messages=len(value['messages']);report.identity_strategy='scoped-source-id'
        created=[]
        try:
            db=Database(self.database)
            with db.connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute('PRAGMA user_version').fetchone()[0]!=3:raise ValidationError('群聊和附件需要扩展归档；请先创建升级副本，原库保留')
                validate_schema(conn,3);users={};chats={};definitions={x['id']:x for x in value['chats']}
                for user in value['users']:
                    external=user.get('external_id') or (value['namespace']+':'+quote(user['id'],safe='') if value['namespace'].startswith('wechat:') else user['id'])
                    row=conn.execute('SELECT id FROM users WHERE wxid=?',(external,)).fetchone()
                    if row:users[user['id']]=row[0];report.users_reused_count+=1
                    else:
                        users[user['id']]=conn.execute('INSERT INTO users(wxid,nickname) VALUES (?,?)',(external,user['nickname'])).lastrowid;report.users_created_count+=1
                for chat in value['chats']:
                    member_ids=[users[x] for x in chat['members']]
                    if chat['kind']=='private':
                        cid,new=ensure_private_chat(conn,member_ids[0],member_ids[-1],chat.get('title'));chats[chat['id']]=cid
                    else:
                        key='group:'+hashlib.sha256((value['namespace']+'\0'+chat['id']).encode()).hexdigest()
                        row=conn.execute('SELECT id FROM chats WHERE chat_key=?',(key,)).fetchone();new=row is None
                        cid=conn.execute("INSERT INTO chats(chat_key,kind,title) VALUES (?,'group',?)",(key,chat.get('title') or chat['id'])).lastrowid if new else row[0]
                        chats[chat['id']]=cid
                        conn.executemany('INSERT OR IGNORE INTO chat_members(chat_id,user_id) VALUES (?,?)',[(cid,x) for x in member_ids])
                    if new:report.chats_created_count+=1
                    else:report.chats_reused_count+=1
                for index,row in enumerate(value['messages']):
                    if row.get('kind') not in KINDS:
                        report.failed_count+=1;report.issues.append(ImportIssue('message',index,'unsupported','未知消息类型保留在原始来源文件中',record_id=row['id']))
                        if self.strict:raise ValidationError('严格导入包含未支持消息')
                        continue
                    attachments=[]
                    for item in row.get('attachments',[]):
                        file=resource_path(path.parent,item['path']) if item.get('path') else None
                        name=Path(item.get('name') or item.get('path') or '附件').name
                        name=''.join(c if c not in '/\\:*?"<>|' and ord(c)>=32 else '_' for c in name)[:160] or '附件'
                        if file and file.is_file():
                            stamp=(file.stat().st_size,file.stat().st_mtime_ns);digest=sha_file(file)
                            if item.get('sha256') and item['sha256']!=digest:raise ConflictError('来源附件摘要不匹配')
                            relative=digest+'/'+name;target=resource_path(media_root(self.database),relative);target.parent.mkdir(parents=True,exist_ok=True)
                            if not target.exists():
                                with file.open('rb') as source,target.open('xb') as sink:shutil.copyfileobj(source,sink)
                                created.append(target)
                            if sha_file(target)!=digest or stamp!=(file.stat().st_size,file.stat().st_mtime_ns):raise ConflictError('附件复制期间发生变化')
                            attachment={'kind':item.get('kind','file'),'relative_uri':relative,'sha256':digest,'size_bytes':stamp[0],'availability':'ready','variant':item.get('variant','original')}
                        else:
                            attachment={'kind':item.get('kind','file'),'relative_uri':None,'sha256':None,'size_bytes':None,'availability':'missing','variant':item.get('variant','original')}
                        attachment['id']=hashlib.sha256(json.dumps([attachment,name],sort_keys=True).encode()).hexdigest();attachments.append(attachment)
                    canonical={k:v for k,v in row.items() if k!='attachments'};content_hash=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    source_key=json.dumps([row['chat_id'],row['id']],ensure_ascii=False,separators=(',',':'))
                    external_id=row['id']
                    if value['namespace'].startswith('wechat:'):
                        try:
                            parts=json.loads(row['id'])
                            if isinstance(parts,list) and len(parts)==3 and all(isinstance(x,str) and x for x in parts) and parts[1] in ('local','server'):
                                source_key=json.dumps([unquote(value['namespace'][7:]),row['chat_id'],*parts],ensure_ascii=False,separators=(',',':'))
                                external_id='external-msg:'+hashlib.sha256(source_key.encode('utf-8')).hexdigest()
                        except (ValueError,TypeError):pass
                    old=conn.execute('SELECT source_hash,message_id,identity_strategy FROM message_sources WHERE namespace=? AND source_key=?',(value['namespace'],source_key)).fetchall()
                    if old:
                        if len(old)!=1:raise ConflictError('来源消息ID存在歧义，整批回滚')
                        if old[0]['identity_strategy']=='scoped-source-id':
                            matches=old[0]['source_hash']==content_hash
                            if not matches:
                                from ..identity import alias_only_source_change
                                matches=alias_only_source_change(conn,value['namespace'],row,old[0]['message_id'],old[0]['source_hash'])
                        else:
                            existing=conn.execute('SELECT sender_id,receiver_id,create_time,content,msg_type,chat_id FROM messages WHERE id=?',(old[0]['message_id'],)).fetchone()
                            expected=(users.get(row['sender_id']),users[row['receiver_id']] if definitions[row['chat_id']]['kind']=='private' else None,_time(row['create_time']),row.get('content'),'image' if row['kind']=='emoji' else row['kind'],chats[row['chat_id']])
                            matches=tuple(existing)==expected
                        if not matches:raise ConflictError('相同来源消息ID的内容发生冲突，整批回滚')
                        self.bind_media(conn,old[0]['message_id'],attachments)
                        report.duplicated_count+=1;continue
                    kind='image' if row['kind']=='emoji' else row['kind'];chat=definitions[row['chat_id']]
                    body=row.get('content') or ('[表情]' if row['kind']=='emoji' else '['+row['kind']+']')
                    receiver=users[row['receiver_id']] if chat['kind']=='private' else None
                    mid=conn.execute('INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,chat_id,source,source_id,source_hash,external_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (users.get(row['sender_id']),receiver,_time(row['create_time']),body,kind,chats[row['chat_id']],value['namespace'],source_key,content_hash,external_id)).lastrowid
                    conn.execute('INSERT INTO message_sources(message_id,namespace,source_key,source_hash,identity_strategy) VALUES (?,?,?,?,?)',(mid,value['namespace'],source_key,content_hash,'scoped-source-id'))
                    self.bind_media(conn,mid,attachments)
                    report.success_count+=1
                if before!=(path.stat().st_size,path.stat().st_mtime_ns,sha_file(path)):raise ConflictError('来源文件在导入期间发生变化')
            report.status='partial' if report.failed_count else 'success';report.finished_at=utc_now()
            report.source_metadata={'groups':sum(x['kind']=='group' for x in value['chats']),'attachment_count':sum(len(x.get('attachments',[])) for x in value['messages']),'quarantined_count':report.failed_count}
        except Exception:
            for file in created:
                if file.resolve().is_relative_to(media_root(self.database).resolve()):file.unlink(missing_ok=True)
            raise
        if self.report_dir:report.save(self.report_dir)
        return report
