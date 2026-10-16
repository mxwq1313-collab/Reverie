"""App-owned local conversation snapshots, independent of account authentication."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4
from ..errors import ValidationError


class ConversationHistory:
    def __init__(self,profile):self.directory=Path(profile)/'ai_history'
    def path(self,key):
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key):raise ValidationError('历史对话标识无效')
        path=self.directory/(key+'.json')
        if self.directory.is_symlink() or path.is_symlink():raise ValidationError('历史目录或文件不能是链接')
        return path
    def save(self,value):
        key=value.get('id') or uuid4().hex;target=self.path(key)
        data={**value,'id':key,'format':'sixu-ai-history-1','updated_at':datetime.now(timezone.utc).isoformat()}
        data.setdefault('created_at',data['updated_at'])
        encoded=json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
        if len(encoded)>16*1024*1024:raise ValidationError('历史快照超过16MiB，本次显示内容仍保留')
        self.directory.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix('.'+uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
        return data
    def read(self,key):
        path=self.path(key)
        if path.stat().st_size>16*1024*1024:raise ValidationError('历史文件超出读取预算')
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or not isinstance(value.get('title'),str) or value.get('format')!='sixu-ai-history-1' or value.get('id')!=key or not isinstance(value.get('messages'),list):raise ValidationError('历史文件结构不匹配')
        try:
            stamp=datetime.fromisoformat(value.get('updated_at',''))
            if stamp.tzinfo is None:raise ValueError('missing timezone')
        except (TypeError,ValueError):raise ValidationError('历史时间字段无效')
        for item in value['messages']:
            if not isinstance(item,dict) or not isinstance(item.get('role'),str) or not isinstance(item.get('text'),str):raise ValidationError('历史消息结构不匹配')
        return value
    def list(self,query=''):
        rows=[]
        if not self.directory.exists():return rows
        for path in self.directory.glob('*.json'):
            try:
                value=self.read(path.stem)
                if not query or query.casefold() in (value.get('title','')+' '+value.get('archive_name','')).casefold():
                    rows.append({k:v for k,v in value.items() if k!='messages'})
            except (OSError,ValueError,ValidationError):continue
        return sorted(rows,key=lambda x:x.get('updated_at',''),reverse=True)
