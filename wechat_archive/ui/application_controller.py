"""整合已有服务的桌面操作层；归档浏览使用只读连接。"""

from contextlib import contextmanager,closing
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sqlite3
import threading
import queue
from copy import copy
from types import SimpleNamespace
from uuid import uuid4

from ..database.db import default_data_dir
from ..errors import ArchiveError,ConflictError,NotFoundError,ValidationError
from ..services.chat_service import _id
from ..exporter import export_readable
from ..exporter.readable import _local_path
from ..services import ChatService
from ..services.browse_service import BrowseService
from ..wechat_source.live_source import run_source_job
from .import_controller import ImportController,inspect_archive
from .read_cache import ReadCache,CancelledReader


class ReadOnlyArchive:
    def __init__(self,path):
        self.path=inspect_archive(path)
        with self.connection() as connection:self.version=connection.execute('PRAGMA user_version').fetchone()[0]
    @contextmanager
    def connection(self):
        connection=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        connection.row_factory=sqlite3.Row
        try:
            from ..identity import install_identity_views
            self.identity_aliases=install_identity_views(connection);connection.commit()
            connection.execute('PRAGMA query_only=ON')
            yield connection
        finally:connection.close()


class ApplicationController:
    def __init__(self,data_dir=None,source_runner=None):
        self.profile_dir=Path(data_dir) if data_dir is not None else default_data_dir()
        self.data_dir=self.profile_dir
        from .user_preferences import normalized
        selected=normalized(self.settings())['storage_root']
        if selected:
            try:self.data_dir=_local_path(selected)
            except (ArchiveError,ValueError,OSError):pass
        self.imports=ImportController(report_dir=self.data_dir/'import_logs')
        self.source_runner=source_runner or run_source_job
        self.database=None
        self.cancel_event=threading.Event();self.writing=False
        self.streaming=False
        self._read_cache=ReadCache();self._read_session=False;self._read_cancel=None
        self.operation_progress=queue.SimpleQueue()

    def open_archive(self,path):
        self.database=self._read_cache.reader(_local_path(path),ReadOnlyArchive).path
        settings=self.settings();settings['last_archive']=str(self.database);self.save_settings(settings)
        return self.overview()

    def settings(self):
        try:
            value=json.loads((self.profile_dir/'desktop_settings.json').read_text(encoding='utf-8'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

    def save_settings(self,value):
        if self._read_session:return
        self.profile_dir.mkdir(parents=True,exist_ok=True)
        target=self.profile_dir/'desktop_settings.json';temporary=self.profile_dir/('settings_'+uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()

    def user_preferences(self):
        from .user_preferences import normalized
        return normalized(self.settings())

    def save_user_preferences(self,values):
        from .user_preferences import validate
        result=validate(values);settings=self.settings();old=settings.get('ui',{})
        settings['ui']={**(old if isinstance(old,dict) else {}),**result}
        settings['copilot_layout']={**self.copilot_layout(),'expanded':result['show_ai']}
        self.save_settings(settings)
        self.data_dir=_local_path(result['storage_root']) if result['storage_root'] else self.profile_dir
        self.imports.report_dir=self.data_dir/'import_logs'
        return result

    def view_state(self):
        views=self.settings().get('views',{})
        value=views.get(str(self.database),{}) if isinstance(views,dict) else {}
        if not isinstance(value,dict):return {}
        value=dict(value)
        if self.database:
            aliases=getattr(self.readonly(),'identity_aliases',{})
            if 'owner_id' in value:value['owner_id']=aliases.get(value['owner_id'],value['owner_id'])
            if type(value.get('peer_id')) is int and value['peer_id']>0:value['peer_id']=aliases.get(value['peer_id'],value['peer_id'])
        return value

    def save_view(self,owner,peer):
        _id(owner,'owner_id')
        if peer is not None:_id(abs(peer) if type(peer) is int else peer,'peer_id')
        settings=self.settings();views=settings.get('views',{})
        if not isinstance(views,dict):views={}
        views[str(self.require_archive())]={'owner_id':owner,'peer_id':peer}
        settings['views']=dict(list(views.items())[-30:]);self.save_settings(settings)

    def preferences(self):
        value=self.settings().get('ui',{})
        if not isinstance(value,dict):value={}
        size=value.get('text_size',15)
        return {'text_size':size if type(size) is int and 14<=size<=18 else 15,'compact_nav':bool(value.get('compact_nav',False))}

    def save_preferences(self,text_size,compact_nav):
        if type(text_size) is not int or not 14<=text_size<=18:raise ValidationError('正文字号为 14–18 逻辑像素。')
        settings=self.settings();old=settings.get('ui',{});settings['ui']={**(old if isinstance(old,dict) else {}),'text_size':text_size,'compact_nav':bool(compact_nav)};self.save_settings(settings)

    def copilot_layout(self):
        value=self.settings().get('copilot_layout',{})
        if not isinstance(value,dict):value={}
        width=value.get('width',360);expanded=value.get('expanded',True)
        return {'width':width if type(width) is int and 300<=width<=4096 else 360,
                'expanded':expanded if type(expanded) is bool else True}

    def save_copilot_layout(self,expanded,width):
        if type(expanded) is not bool or type(width) is not int or not 300<=width<=4096:
            raise ValidationError('助手布局宽度为300–4096逻辑像素。')
        settings=self.settings();settings['copilot_layout']={'expanded':expanded,'width':width};self.save_settings(settings)

    def browser_layout(self):
        value=self.settings().get('browser_layout',{});value=value if isinstance(value,dict) else {}
        width=value.get('width',270)
        return {'width':width if type(width) is int and 140<=width<=2048 else 270}
    def save_browser_layout(self,width):
        if type(width) is not int or not 140<=width<=2048:raise ValidationError('会话列表宽度为140–2048逻辑像素。')
        settings=self.settings();settings['browser_layout']={'width':width};self.save_settings(settings)

    def restore_archive(self):
        saved=self.settings().get('last_archive');candidates=[]
        if isinstance(saved,str):candidates.append(Path(saved))
        candidates.append(self.data_dir/'chat.db')
        for candidate in candidates:
            if candidate.is_file():
                try:return self.open_archive(candidate)
                except (ArchiveError,sqlite3.Error,OSError):continue
        return None

    def new_archive(self,path,rich=False):
        path=_local_path(path)
        if path.exists():raise ConflictError('新建归档不能覆盖已有文件，请使用“打开归档”。')
        if rich:
            from ..importer.rich_importer import create_rich_archive
            create_rich_archive(path)
        else:ChatService(path)
        return self.open_archive(path)

    def require_archive(self):
        if self.database is None:raise ValidationError('请先新建或打开归档库。')
        return self.database

    @staticmethod
    def is_archive_copy(source):
        try:
            from ..database.db import APPLICATION_ID
            path=_local_path(source)
            if not path.is_file() or path.suffix.lower() not in ('.db','.sqlite','.sqlite3'):return False
            with ReadOnlyArchive(path).connection() as conn:
                return conn.execute('PRAGMA application_id').fetchone()[0]==APPLICATION_ID
        except (ArchiveError,sqlite3.Error,OSError,ValueError):return False

    def import_archive_copy(self,source):
        """Import a validated project copy, preserving source and verified attachments."""
        import shutil,tempfile
        from ..importer.rich_importer import media_root,resource_path,ready_media
        source=inspect_archive(source)
        folder=self.data_dir/'archives';folder.mkdir(parents=True,exist_ok=True)
        target=folder/(source.stem+'-'+uuid4().hex[:8]+'.db')
        with ReadOnlyArchive(source).connection() as conn:version=conn.execute('PRAGMA user_version').fetchone()[0]
        if version<3:
            from ..migration.copy_upgrade import upgrade_archive_copy
            upgrade_archive_copy(source,target);self.open_archive(target);return self.overview()
        with tempfile.TemporaryDirectory(prefix='.sixu-import-',dir=folder) as temporary:
            staging=Path(temporary)/target.name
            with ReadOnlyArchive(source).connection() as conn:
                version=conn.execute('PRAGMA user_version').fetchone()[0]
                with closing(sqlite3.connect(staging)) as sink:conn.backup(sink)
                if version==3:
                    for row in conn.execute("SELECT * FROM media WHERE availability='ready'"):
                        original=ready_media(source,dict(row));copied=resource_path(media_root(staging),row['relative_uri'])
                        copied.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,copied)
                        ready_media(staging,dict(row))
            inspect_archive(staging)
            # Publish the complete independent copy only after validation.
            if media_root(staging).exists():media_root(staging).rename(media_root(target))
            try:
                import os
                os.link(staging,target)
            except Exception:
                if media_root(target).exists() and media_root(target).resolve().parent==folder.resolve():shutil.rmtree(media_root(target))
                raise
        self.open_archive(target)
        self.ensure_extended_archive()
        return self.overview()

    def ensure_extended_archive(self):
        """Prepare a compatible working file automatically; the opened original is retained."""
        if self.rich_reader():return self.require_archive()
        folder=self.data_dir/'archives';folder.mkdir(parents=True,exist_ok=True)
        target=folder/(self.require_archive().stem+'-'+uuid4().hex[:8]+'.db')
        self.upgrade_copy(target)
        return self.require_archive()

    def read_snapshot(self,cancel):
        result=copy(self);result._read_session=True;result._read_cancel=cancel;return result

    def readonly(self):
        reader=self._read_cache.reader(self.require_archive(),ReadOnlyArchive)
        return CancelledReader(reader,self._read_cancel) if self._read_cancel else reader

    def cached_read(self,kind,args,work):
        return self._read_cache.value(self.require_archive(),kind,args,work,self._read_cancel)

    def browser(self):return BrowseService(SimpleNamespace(database=self.readonly()))

    def source_capabilities(self):
        """Describe the selected archive's existing acquisition path without migrating it."""
        if not self.database:
            return {'streaming':False,'can_upgrade':False,'description':'请先打开或创建归档；读取能力按所选归档显示。'}
        with self.readonly().connection() as connection:
            version=connection.execute('PRAGMA user_version').fetchone()[0]
        if version>=3:
            return {'streaming':True,'can_upgrade':False,'description':'扩展归档：全部电脑本地记录使用封存快照、分批保存，可停止后续批次并恢复；未知原记录保留。真实来源完整性以结果报告为准。'}
        return {'streaming':False,'can_upgrade':True,'description':'基础归档：单次最多 100000 条来源记录、64 MiB，超限或来源变化时拒绝。创建升级副本后，全部范围可使用快照分批路径；原归档保留。'}

    def archive_view_token(self):
        path=self.require_archive()
        stamps=[]
        for item in (path,Path(str(path)+'-wal')):
            stat=item.stat() if item.exists() else None
            stamps.append((stat.st_ino,stat.st_size,stat.st_mtime_ns) if stat else None)
        return (str(path),tuple(stamps))

    def overview(self):
        return self.cached_read('overview',(),self._overview)

    def _overview(self):
        with self.readonly().connection() as connection:
            users=connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            messages=connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        return {'database':str(self.database),'users':users,'messages':messages}

    def users(self):
        return self.cached_read('users',(),self._users)

    def _users(self):
        browser=self.browser();rows=[]
        while True:
            page=browser.users(limit=1000,offset=len(rows));rows.extend(page['items'])
            if not page['has_more']:return rows
    def rich_reader(self):
        archive=self.readonly();version=archive.version
        if version==3:
            from ..services.rich_reader import RichReader
            return RichReader(archive)
        return None

    def contacts(self,owner,keyword=None):
        rows=self.cached_read('contacts',(owner,),lambda:self._contacts(owner))
        if keyword:rows=[row for row in rows if keyword in row['nickname'] or keyword in row['wxid'] or any(keyword in member['nickname'] for member in row.get('members',[]))]
        from ..services.avatar_cache import AvatarCache
        return AvatarCache(self.data_dir).decorate(rows)

    def _contacts(self,owner):
        rich=self.rich_reader()
        if rich:return rich.contacts(owner)
        browser=self.browser();rows=[]
        while True:
            page=browser.contacts(owner,limit=1000,offset=len(rows));rows.extend(page['items'])
            if not page['has_more']:return rows

    def messages(self,owner,peer=None,keyword=None,start=None,end=None,offset=0):
        return self.cached_read('messages',(owner,peer,keyword,start,end,offset),lambda:self._messages(owner,peer,keyword,start,end,offset))

    def _messages(self,owner,peer=None,keyword=None,start=None,end=None,offset=0):
        zone=timezone(timedelta(hours=8))
        try:
            first=datetime.strptime(start,'%Y-%m-%d').replace(tzinfo=zone).isoformat() if start else None
            last=(datetime.strptime(end,'%Y-%m-%d').replace(tzinfo=zone)+timedelta(days=1)).isoformat() if end else None
        except ValueError as error:raise ValidationError('日期应为 YYYY-MM-DD，例如 2026-01-01。') from error
        rich=self.rich_reader()
        if rich:return rich.messages(owner,peer,keyword or None,first,last,100,offset)
        return self.browser().messages(owner,peer_id=peer,keyword=keyword or None,start_time=first,end_time=last,limit=100,offset=offset)

    def message_context(self,owner,message_id):
        """最小只读扩展：定位授权身份的一条消息所在私聊页，不改网页接口。"""
        _id(owner,'owner_id');_id(message_id,'message_id')
        rich=self.rich_reader()
        if rich:
            with self.readonly().connection() as connection:
                row=connection.execute("SELECT m.*,c.kind FROM messages m JOIN chats c ON c.id=m.chat_id WHERE m.id=?",(message_id,)).fetchone()
                if row and row['kind']=='group':
                    peer=-row['chat_id']
                    if not connection.execute('SELECT 1 FROM chat_members WHERE chat_id=? AND user_id=?',(row['chat_id'],owner)).fetchone():raise NotFoundError('当前身份无权查看此群聊')
                    rank=connection.execute('SELECT COUNT(*) FROM messages WHERE chat_id=? AND (create_time<? OR (create_time=? AND id<?))',(row['chat_id'],row['create_time'],row['create_time'],message_id)).fetchone()[0]
                    return {**rich.messages(owner,peer,limit=100,offset=max(0,rank-30)),'peer_id':peer,'target_id':message_id}

        with self.readonly().connection() as connection:
            connection.execute('BEGIN')
            row=connection.execute('SELECT * FROM messages WHERE id=? AND (sender_id=? OR receiver_id=?)',(message_id,owner,owner)).fetchone()
            if row is None or (not rich and row['msg_type']!='text') or row['receiver_id'] is None:raise NotFoundError('当前查看身份没有可展开的私聊文本消息。')
            peer=row['receiver_id'] if row['sender_id']==owner else row['sender_id']
            rank=connection.execute('SELECT COUNT(*) FROM messages WHERE ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)) AND (create_time<? OR (create_time=? AND id<?))',
                (owner,peer,peer,owner,row['create_time'],row['create_time'],message_id)).fetchone()[0]
        offset=max(0,rank-30)
        result=rich.messages(owner,peer,limit=100,offset=offset) if rich else self.browser().messages(owner,peer_id=peer,limit=100,offset=offset)
        return {**result,'peer_id':peer,'target_id':message_id}

    def import_file(self,source,chosen='auto',strict=False,namespace='default',csv_timezone='+08:00'):
        from .import_controller import resolve_format,source_path
        if resolve_format(source_path(source),chosen) in ('rich','rich_snapshot'):self.ensure_extended_archive()
        path,database,importer=self.imports.prepare(source,self.require_archive(),chosen,strict=strict,namespace=namespace,timezone=csv_timezone)
        from ..importer.snapshot_importer import SnapshotImporter
        from ..importer.rich_snapshot import RichSnapshotImporter
        self.writing=True;self.streaming=isinstance(importer,(SnapshotImporter,RichSnapshotImporter))
        try:
            return importer.import_snapshot(path,cancel_event=self.cancel_event) if self.streaming else importer.import_file(path)
        finally:self.writing=False;self.streaming=False

    def export(self,parent,user_id=None,peer_id=None,formats=('html','txt'),display_timezone='+08:00'):
        stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        target=_local_path(parent)/('聊天导出_'+stamp+'_'+uuid4().hex[:8])
        return export_readable(self.require_archive(),target,user_id=user_id,peer_id=peer_id,formats=formats,display_timezone=display_timezone)

    def discover(self,root=None):
        result=self.source_runner('accounts',self.data_dir,root=root,cancel_event=self.cancel_event)
        if self.database:
            from ..services.avatar_cache import user_identity
            known={}
            try:
                with self.readonly().connection() as conn:
                    for person in conn.execute('SELECT wxid,nickname FROM users'):
                        identity=user_identity(person['wxid'])
                        if identity and identity[0]==identity[1] and person['nickname']:
                            known.setdefault(identity[0],set()).add(person['nickname'])
                for row in result['accounts']:
                    names=known.get(row['wxid'],set())
                    if not row.get('nickname') and len(names)==1:
                        row.update(nickname=next(iter(names)),identity_status='archive_label')
            except (ArchiveError,OSError,ValueError):pass
        return result
    def source_contacts(self,root,account,keyword=None,rich=False):return self.source_runner('contacts',self.data_dir,root=root,account=account,keyword=keyword,**({'rich':True} if rich else {}),cancel_event=self.cancel_event)
    def sync_avatars(self,owner,root=None,account=None):
        from ..services.avatar_cache import AvatarCache,targets
        native,mapping=targets(self.readonly(),owner)
        if not account:
            detected=self.discover(root)
            choices=[x for x in detected['accounts'] if x['wxid']==native]
            if len(choices)!=1:raise ValidationError('没有找到当前归档身份对应的微信账号，请到添加记录检查账号。')
            root=detected['root'];account=choices[0]['account']
        found=self.source_runner('avatars',self.data_dir,root=root,account=account,peers=list(set(mapping.values())),cancel_event=self.cancel_event)
        if found['owner']!=native:raise ValidationError('微信账号与当前归档身份不一致，头像未保存。')
        return AvatarCache(self.data_dir).store(mapping,found['images'],self.data_dir/'source_jobs')

    def acquire_import(self,root,account,peer,limit=50,all_history=False,rich=False,allow_cdn=False):
        self.require_archive()
        if rich:self.ensure_extended_archive()
        with ReadOnlyArchive(self.require_archive()).connection() as connection:
            extended=connection.execute('PRAGMA user_version').fetchone()[0]>=3
        if extended and rich:
            source=self.data_dir/'sources'/('wechat_rich_'+uuid4().hex)
            captured=self.source_runner('rich_capture',self.data_dir,root=root,account=account,peer=peer,limit=limit,all_history=all_history,output=str(source),cancel_event=self.cancel_event,allow_cdn=allow_cdn,progress_callback=self.operation_progress.put)
            if self.cancel_event.is_set():raise ValidationError('读取已取消，未导入')
            from ..importer.rich_snapshot import RichSnapshotImporter
            self.writing=True;self.streaming=True
            try:report=RichSnapshotImporter(self.require_archive(),report_dir=self.data_dir/'import_logs').import_snapshot(captured['output'],cancel_event=self.cancel_event,progress=self.operation_progress.put)
            finally:self.writing=False;self.streaming=False
            # Avatar acquisition is optional presentation data, never an import success gate.
            try:
                from ..services.avatar_cache import user_identity
                owner=next(x['id'] for x in self.users() if (value:=user_identity(x['wxid'])) and value[0]==value[1] and value[0]==account.rsplit('_',1)[0])
                captured['avatars']=self.sync_avatars(owner,root,account)
            except Exception as error:captured['avatars']={'unavailable':type(error).__name__}
            return {'capture':captured,'report':report}
        streaming=bool(all_history and extended)
        source=self.data_dir/'sources'/('wechat_'+uuid4().hex+('' if streaming else '.json'))
        captured=self.source_runner('snapshot' if streaming else 'capture',self.data_dir,root=root,account=account,peer=peer,limit=limit,all_history=all_history,output=str(source),cancel_event=self.cancel_event)
        if self.cancel_event.is_set():raise ValidationError('读取已取消，未导入。')
        self.writing=True
        self.streaming=streaming
        try:
            if streaming:
                from ..importer.snapshot_importer import SnapshotImporter
                report=SnapshotImporter(self.require_archive(),report_dir=self.data_dir/'import_logs').import_snapshot(captured['output'],cancel_event=self.cancel_event)
            else:report=self.import_file(captured['output'],'external')
        finally:self.writing=False;self.streaming=False
        return {'capture':captured,'report':report}

    def repair_emojis(self,allow_cdn=False):
        from ..services.emoji_repair import repair_emojis
        self.writing=True;self.streaming=True
        try:return repair_emojis(self.require_archive(),allow_cdn=allow_cdn,cancel_event=self.cancel_event,progress=self.operation_progress.put)
        finally:self.writing=False;self.streaming=False

    def manage_user(self,action,user_id=None,**fields):
        service=ChatService(self.require_archive())
        if action=='create':return service.create_user(**fields)
        if action=='update':return service.update_user(user_id,**fields)
        if action=='delete':return service.delete_user(user_id)
        raise ValidationError('未知的联系人操作。')

    def upgrade_copy(self,target):
        from ..migration.copy_upgrade import upgrade_archive_copy
        result=upgrade_archive_copy(self.require_archive(),target)
        self.open_archive(result['target'])
        return result

    def manage_message(self,action,message_id=None,**fields):
        service=ChatService(self.require_archive())
        if action=='create':return service.create_message(**fields)
        if action=='update':return service.update_message(message_id,**fields)
        if action=='delete':return service.delete_message(message_id)
        raise ValidationError('未知的消息操作。')

    def report_files(self):
        folder=self.data_dir/'import_logs'
        return sorted(folder.glob('*.json'),key=lambda path:path.stat().st_mtime,reverse=True) if folder.is_dir() else []

    def read_report(self,path):
        path=_local_path(path)
        if path.parent!=self.data_dir.resolve()/'import_logs':raise ValidationError('请选择本软件报告目录内的文件。')
        if path.stat().st_size>64*1024*1024:raise ValidationError('报告超出读取上限。')
        return json.loads(path.read_text(encoding='utf-8'))
