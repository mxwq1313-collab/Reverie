"""Offline group/media export, retaining original text and verified opaque files."""
from html import escape
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import quote

from ..errors import ConflictError, ValidationError
from ..importer.rich_importer import media_root, ready_media, sha_file
from ..ui.import_controller import inspect_archive
from ..ui.application_controller import ReadOnlyArchive


def export_rich(database,output_dir,*,user_id=None,peer_id=None,formats=('html','txt'),display_timezone='+08:00'):
    from .readable import _head,_display_zone,_time,_publish_directory
    source=inspect_archive(database);target=Path(output_dir).expanduser().resolve()
    if target.exists():raise ConflictError('导出目录已存在，请选择新的目录')
    if peer_id is not None and user_id is None:raise ValidationError('请选择查看身份')
    if not formats or len(set(formats))!=len(formats) or any(x not in ('html','txt') for x in formats):raise ValidationError('导出格式无效')
    zone=_display_zone(display_timezone);target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.sixu-export-',dir=target.parent)).resolve()
    try:
        with ReadOnlyArchive(source).connection() as conn:
            conn.execute('BEGIN');people={r['id']:dict(r) for r in conn.execute('SELECT * FROM users')}
            if user_id is not None and user_id not in people:raise ValidationError('查看身份不存在')
            if peer_id is not None and peer_id>=0 and peer_id not in people:raise ValidationError('联系人不存在')
            if peer_id is not None and peer_id<0:
                clause='m.chat_id=? AND EXISTS(SELECT 1 FROM chat_members cm WHERE cm.chat_id=m.chat_id AND cm.user_id=?)';params=[-peer_id,user_id]
            elif peer_id is not None:
                clause='((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))';params=[user_id,peer_id,peer_id,user_id]
            elif user_id is not None:
                clause="((m.receiver_id IS NOT NULL AND (m.sender_id=? OR m.receiver_id=?)) OR m.chat_id IN (SELECT cm.chat_id FROM chat_members cm JOIN chats c ON c.id=cm.chat_id WHERE cm.user_id=? AND c.kind='group'))";params=[user_id,user_id,user_id]
            else:clause='1=1';params=[]
            groups=[dict(x) for x in conn.execute('SELECT m.chat_id,c.kind,c.title,COUNT(*) count FROM messages m JOIN chats c ON c.id=m.chat_id WHERE '+clause+' GROUP BY m.chat_id ORDER BY m.chat_id',params)]
            conversations=[];total=0
            for group in groups:
                title=group['title'] or '聊天会话';key='chat_'+str(group['chat_id']);html=[];text=[];members=[dict(x) for x in conn.execute('SELECT u.* FROM chat_members cm JOIN users u ON u.id=cm.user_id WHERE cm.chat_id=?',(group['chat_id'],))]
                names='、'.join(x['nickname'] for x in members)
                html.append(_head(title)+f'<header><h1>{escape(title)}</h1><p>{escape(names)} · {group["count"]} 条消息</p></header>')
                text.append(title+'\n参与者：'+names+'\n')
                for row in conn.execute('SELECT m.* FROM messages m WHERE ('+clause+') AND m.chat_id=? ORDER BY m.create_time,m.id',(*params,group['chat_id'])):
                    sender=people[row['sender_id']]['nickname'] if row['sender_id'] else '系统';stamp=_time(row['create_time'],zone,row['id']);body=row['content'] or '['+row['msg_type']+']'
                    html.append('<article><div class="sender">'+escape(sender)+' · '+escape(stamp)+'</div><p class="body">'+escape(body)+'</p>')
                    text.append('['+stamp+'] '+sender+'\n'+body+'\n')
                    for item in conn.execute('SELECT media.* FROM message_media mm JOIN media ON media.id=mm.media_id WHERE mm.message_id=? ORDER BY mm.ordinal',(row['id'],)):
                        if item['availability']=='ready':
                            original=ready_media(source,item);relative='attachments/'+item['relative_uri'];dest=staging/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                            if not dest.exists():shutil.copyfile(original,dest)
                            if sha_file(dest)!=item['sha256']:raise ConflictError('导出附件摘要校验失败')
                            url=quote(relative);name=Path(item['relative_uri']).name
                            if item['kind']=='image':html.append(f'<img src="{url}" alt="{escape(name,quote=True)}" style="max-width:100%;max-height:420px">')
                            elif item['kind'] in ('audio','video'):html.append(f'<{item["kind"]} controls preload="none" src="{url}" style="max-width:100%"></{item["kind"]}>')
                            html.append(f'<p><a href="{url}" download>{escape(name)}</a> · {item["size_bytes"]} bytes</p>');text.append('附件：'+relative+'\n')
                        else:html.append('<p>附件原文件缺失，保留消息记录。</p>');text.append('附件原文件缺失\n')
                    html.append('</article>');total+=1
                html.append('</main></body></html>')
                files=[]
                for kind in formats:
                    filename=key+'.'+kind;(staging/filename).write_text('\n'.join(html if kind=='html' else text),encoding='utf-8');files.append(filename)
                conversations.append({'chat_id':group['chat_id'],'kind':group['kind'],'title':title,'messages':group['count'],'files':files})
            if 'html' in formats:
                index=_head('思绪 · 离线归档')+'<header><h1>思绪 · 离线归档</h1></header><ul>'
                for item in conversations:index+=f'<li><a href="chat_{item["chat_id"]}.html">{escape(item["title"])}</a> · {item["messages"]} 条</li>'
                (staging/'index.html').write_text(index+'</ul></main></body></html>',encoding='utf-8')
            files=[{'name':p.relative_to(staging).as_posix(),'bytes':p.stat().st_size,'sha256':sha_file(p)} for p in staging.rglob('*') if p.is_file()]
            manifest={'format':'readable-chat-export','format_version':'2.0','database_schema':3,'messages':total,'conversations':conversations,'files':files,'scope':{'user_id':user_id,'peer_id':peer_id}}
            (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        _publish_directory(staging,target);staging=None
        return {'directory':str(target),'messages':total,'conversations':len(conversations),'formats':list(formats),'index':str(target/'index.html') if 'html' in formats else None,'manifest':str(target/'manifest.json'),'files':[str(target/x['name']) for x in files]}
    finally:
        if staging and staging.parent==target.parent and staging.name.startswith('.sixu-export-'):shutil.rmtree(staging)
