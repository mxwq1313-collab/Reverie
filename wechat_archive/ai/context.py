"""Bounded immutable UI metadata. No message body is implicitly sent to a model."""
from dataclasses import dataclass,field,replace
import hashlib
import json
from pathlib import Path

from ..errors import ConflictError,NotFoundError


def archive_token(path):
    path=Path(path).resolve();stamps=[]
    for item in (path,Path(str(path)+'-wal')):
        stat=item.stat() if item.exists() else None
        stamps.append((stat.st_ino,stat.st_size,stat.st_mtime_ns) if stat else None)
    return (str(path),tuple(stamps))


@dataclass(frozen=True)
class AIContext:
    archive_id:str
    conversation_id:str|None
    user_id:int
    peer_id:int|None
    archive_name:str
    user_name:str
    peer_name:str|None
    page:str
    search_query:str=''
    date_filter:tuple[str,str]=('','')
    selected_messages:tuple[int,...]=()
    visible_messages:tuple[int,...]=()
    current_position:int|None=None
    metadata:tuple[tuple[str,str],...]=()
    source_token:tuple=field(default=(),repr=False)

    @property
    def scope_key(self):return self.source_token[0],self.user_id,self.peer_id

    def to_payload(self):
        return {'version':'1.0','archive_id':self.archive_id,'archive_name':self.archive_name,
            'conversation_id':self.conversation_id,'user_id':self.user_id,'peer_id':self.peer_id,
            'user_name':self.user_name,'peer_name':self.peer_name,'page':self.page,
            'search_query':self.search_query,'date_filter':{'start':self.date_filter[0],'end':self.date_filter[1]},
            'selected_messages':list(self.selected_messages),'visible_messages':list(self.visible_messages),
            'current_position':self.current_position,'metadata':dict(self.metadata)}

    def validate(self,scope):
        if self.scope_key!=scope.key or self.source_token!=archive_token(scope.path):
            raise ConflictError('归档或读取范围已变化，请重新提问。')


class ContextProvider:
    """Capture on the UI thread, then validate immutable identity on a worker thread."""
    def __init__(self,app):self.app=app

    def capture(self,scope):
        return self.resolve(self.capture_ui(scope),scope)

    def capture_ui(self,scope):
        """Freeze Python UI state only; no SQLite work on the UI thread."""
        token=archive_token(scope.path)
        if not self.is_current_scope(scope):raise ConflictError('当前会话已变化，请重新提问。')
        panel=getattr(self.app,'agent_panel',None)
        names=panel.scope_labels if panel is not None and panel.scope_labels_key==(scope.key,token) else {}
        query=getattr(self.app,'loaded_query',None)
        word,start,end='','','';search_scope='none'
        if query and query[0]==scope.user_id:
            word=str(query[2] or '')[:256];start=str(query[3] or '')[:10];end=str(query[4] or '')[:10]
            search_scope='all_conversations' if query[1] is None else 'conversation'
        context=AIContext(
            archive_id=hashlib.sha256(json.dumps(token,ensure_ascii=False).encode('utf-8')).hexdigest(),
            conversation_id=f"{'group' if scope.peer_id is not None and scope.peer_id<0 else 'private'}:{scope.user_id}:{scope.peer_id}" if scope.peer_id is not None else None,
            user_id=scope.user_id,peer_id=scope.peer_id,archive_name=scope.path.name[:80],
            user_name=names.get(scope.user_id,'')[:80],peer_name=names.get(scope.peer_id,'')[:80] if scope.peer_id is not None else None,
            page=str(getattr(self.app,'current_subpage','聊天归档'))[:40],search_query=word,date_filter=(start,end),
            metadata=(('context_level','conversation-v1'),('authorized_range','conversation' if scope.peer_id is not None else 'identity_private_chats'),
                ('browser_search_scope',search_scope),('display_timezone','+08:00'),('evidence','read_only_tools_on_demand'),('message_selection','not_captured_in_phase1')),
            source_token=token)
        context.validate(scope)
        if len(json.dumps(context.to_payload(),ensure_ascii=False))>4096:raise ConflictError('界面上下文超出预算。')
        return context

    def resolve(self,context,scope):
        """Validate the archive and resolve two participant names on a worker thread."""
        from ..agent.tools import ReadOnlyArchive
        context.validate(scope)
        if not self.is_current_scope(scope):raise ConflictError('当前会话已变化，请重新提问。')
        with ReadOnlyArchive(scope.path).connection() as connection:
            names={r['id']:r['nickname'] for r in connection.execute('SELECT id,nickname FROM users WHERE id IN (?,?)',
                (scope.user_id,scope.peer_id or scope.user_id))}
        if scope.peer_id is not None and scope.peer_id<0:
            from ..agent.tools import ArchiveTools
            ArchiveTools(scope)
            with ReadOnlyArchive(scope.path).connection() as connection:
                names[scope.peer_id]=connection.execute('SELECT title FROM chats WHERE id=?',(-scope.peer_id,)).fetchone()[0] or '群聊'
        if scope.user_id not in names or scope.peer_id is not None and scope.peer_id not in names:
            raise NotFoundError('当前身份或联系人已不存在。')
        resolved=replace(context,user_name=names[scope.user_id][:80],peer_name=names.get(scope.peer_id,'')[:80] if scope.peer_id is not None else None)
        resolved.validate(scope)
        return resolved

    def is_current_scope(self,scope):
        path=self.app.controller.database
        return path is not None and str(path)==str(scope.path) and self.app.owner_id==scope.user_id and (
            scope.peer_id is None or self.app.peer_id==scope.peer_id)
