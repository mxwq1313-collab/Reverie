"""Registered SDK projection for group members, counts and typed local messages."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from xml.etree import ElementTree

from ..errors import ArchiveError,ConflictError,ValidationError
from ..importer.rich_importer import FORMAT,sha_file,resource_path
from .snapshot import SOURCE_COLUMNS
from .acquisition import _json_value


def decoded_text(value):
    if not isinstance(value,bytes):return value if isinstance(value,str) else ''
    try:
        if value.startswith(b'\x28\xb5\x2f\xfd'):
            import io,zstandard
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(value)) as reader:value=reader.read(16*1024*1024+1)
            if len(value)>16*1024*1024:return ''
        return value.decode('utf-8')
    except Exception:return ''


def source_sender(peer,row,known=()):
    sender=row.get('sender_username')
    if sender:return sender
    if peer.endswith('@chatroom'):
        # Registered WeChat group transport prefix; never infer a sender from a nickname.
        match=re.match(r'^([A-Za-z0-9_@.\-]{1,256}):\r?\n',decoded_text(row.get('message_content')))
        if match and (match[1] in known or re.fullmatch(r'wxid_[A-Za-z0-9_]+',match[1])):return match[1]
    return None


def source_stats(db,peer):
    def query(tables):
        total=own=system=0;senders={}
        for conn,table in tables:
            if not re.fullmatch(r'Msg_[0-9a-fA-F]{32}',table):raise ArchiveError('来源消息表名未登记')
            columns={x['name'] for x in conn.execute(f'PRAGMA table_info("{table}")')}
            if not set(SOURCE_COLUMNS)<=columns:raise ArchiveError('来源消息字段不匹配')
            for row in conn.execute(f'SELECT n.user_name,COUNT(*) count FROM "{table}" m LEFT JOIN Name2Id n ON n.rowid=m.real_sender_id GROUP BY n.user_name'):
                total+=row['count'];senders[row['user_name']]=senders.get(row['user_name'],0)+row['count']
                if row['user_name']==db.wxid:own+=row['count']
            if senders.get(None,0) or senders.get('',0):
                known={x['username'] for x in db.get_group_members(peer)} if peer.endswith('@chatroom') else ()
                for row in conn.execute(f'SELECT m.local_type,m.message_content,n.user_name sender_username FROM "{table}" m LEFT JOIN Name2Id n ON n.rowid=m.real_sender_id WHERE n.user_name IS NULL OR n.user_name=\'\''):
                    if type(row['local_type']) is int and row['local_type'] & 0xffffffff in (10000,10002):
                        senders[row['sender_username']]-=1;system+=1;continue
                    sender=source_sender(peer,dict(row),known)
                    if sender:
                        key=row['sender_username'];senders[key]-=1;senders[sender]=senders.get(sender,0)+1
                        if sender==db.wxid:own+=1
        return {'message_count':total,'own_count':own,'own_ratio':own/total if total else 0,'sender_counts':senders,'system_count':system,'unresolved_count':senders.get(None,0)+senders.get('',0)}
    value=db._run_msg_query(peer,query)
    return value or {'message_count':0,'own_count':0,'own_ratio':0,'sender_counts':{}}


def contacts_with_groups(db,candidates,keyword=None):
    rows=[]
    for row in candidates:
        peer=row['username']
        if peer==db.wxid or peer.startswith('gh_'):continue
        stats=source_stats(db,peer);group=peer.endswith('@chatroom')
        if not stats['message_count']:continue
        item={'username':peer,'name':row.get('remark') or row.get('nick_name') or peer,'kind':'group' if group else 'private',**{k:v for k,v in stats.items() if k!='sender_counts'}}
        if group:
            members=db.get_group_members(peer)
            if len(members)>100000:raise ArchiveError('群成员超过显示预算，请缩小来源范围')
            item['members']=[{'username':x['username'],'name':x.get('remark') or x.get('nick_name') or x['username'],'message_count':stats['sender_counts'].get(x['username'],0),
                              'ratio':stats['sender_counts'].get(x['username'],0)/stats['message_count'] if stats['message_count'] else 0} for x in members]
        rows.append(item)
        if sum(len(x.get('members',[])) for x in rows)>100000:raise ArchiveError('群成员总数超过显示预算，请按群名搜索')
    return rows


def normalize_row(db,peer,row,users):
    sender=source_sender(peer,row,users);code=row['local_type'];base=code & 0xffffffff if type(code) is int else -1
    text=row['message_content']
    if base==1 and isinstance(text,bytes):
        try:
            if text.startswith(b'\x28\xb5\x2f\xfd'):
                import io,zstandard
                with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(text)) as reader:text=reader.read(16*1024*1024+1)
                if len(text)>16*1024*1024:raise ValueError('text budget')
            text=text.decode('utf-8')
        except Exception:text=None
    elif isinstance(text,bytes):text=db._friendly_content(text,db._msg_type_name(code))
    text=text if isinstance(text,str) else ''
    kinds={1:'text',3:'image',34:'audio',43:'video',47:'emoji',48:'location',10000:'system',10002:'system',11000:'emoji'}
    kind=kinds.get(base,'unsupported')
    if base==1 and not text.strip():kind='unsupported';text='[未解析文本，原始字节保留在来源中]'
    if base==49:
        try:
            xml=ElementTree.fromstring(text) if len(text)<2*1024*1024 else None
            kind='file' if xml is not None and xml.findtext('.//appmsg/type')=='6' else 'system'
        except ElementTree.ParseError:kind='unsupported'
    if kind=='unsupported':kind='system';text=f'[来源消息类型 {code}]\n'+(text or '[原始字节保留在来源快照中]')
    source_kind=kind
    registered_system=base in (10000,10002)
    if not sender or sender not in users:
        sender=None;kind='system'
        if not registered_system:text='[发送者未映射]\n'+text
    server=row['server_id'] if type(row['server_id']) is int and row['server_id']>0 else None
    result={'id':json.dumps([row['shard'],'server' if server is not None else 'local',str(server if server is not None else row['local_id'])],separators=(',',':')),
            'chat_id':peer,'sender_id':sender,'receiver_id':None if peer.endswith('@chatroom') else (peer if sender==db.wxid else db.wxid),
            'create_time':datetime.fromtimestamp(row['create_time'],timezone.utc).isoformat(),'kind':kind,'content':text or ('[表情]' if kind=='emoji' else '['+kind+']'),'attachments':[]}
    if sender is None and not registered_system:result['unmapped_kind']=source_kind
    return result


def capture_rich(db,owner,contact,output,*,all_history=False,limit=50,guard=None,allow_cdn=False,progress=None,staging_parent=None):
    peer=contact['username'];target=Path(output).resolve()
    source_root=Path(db.account_dir).resolve()
    if target.exists() or target.is_relative_to(source_root):raise ConflictError('来源快照必须写入原微信目录之外的新目录')
    if not all_history and (type(limit)is not int or not 1<=limit<=1000000):raise ValidationError('读取数量须为1–1000000；更多记录请选择全部。')
    staging_home=Path(staging_parent).resolve() if staging_parent else target.parent
    if staging_home.is_relative_to(source_root):raise ConflictError('临时快照不能位于微信原目录内')
    target.parent.mkdir(parents=True,exist_ok=True);staging_home.mkdir(parents=True,exist_ok=True);staging=Path(tempfile.mkdtemp(prefix='.sixu-capture-',dir=staging_home)).resolve()
    users={db.wxid:{'id':db.wxid,'nickname':owner['nick_name']}}
    if peer.endswith('@chatroom'):
        for user in db.get_group_members(peer):users[user['username']]={'id':user['username'],'nickname':user.get('remark') or user.get('nick_name') or user['username']}
    else:users[peer]={'id':peer,'nickname':contact.get('remark') or contact.get('nick_name') or peer}
    shards=[];records=0;unknown=0;retained_unmapped=0;attachments=0;media_failures=0;media_missing=0
    media_reader=None;media_error=None
    from .emoji_cache import EmojiCache
    emoji_cache=EmojiCache(source_root,allow_cdn=allow_cdn,db=db)
    media_status_counts={}
    def note_media(status):media_status_counts[status]=media_status_counts.get(status,0)+1
    try:
        from .media_acquisition import local_media_reader
        try:media_reader=local_media_reader(db,staging/'assets')
        except (ArchiveError,ImportError,OSError) as error:media_error=type(error).__name__
        def project(tables):
            nonlocal records,unknown,retained_unmapped,attachments,media_failures,media_missing
            if not tables:raise ArchiveError('未取得登记的会话消息表')
            source_total=sum(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for connection,table in tables if re.fullmatch(r'Msg_[0-9a-fA-F]{32}',table))
            expected=source_total if all_history else min(source_total,limit)
            for connection,table in tables:
                if not re.fullmatch(r'Msg_[0-9a-fA-F]{32}',table):raise ArchiveError('来源消息表名未登记')
                columns={x['name'] for x in connection.execute(f'PRAGMA table_info("{table}")')}
                if not set(SOURCE_COLUMNS)<=columns:raise ArchiveError('来源字段未登记')
            batch=[];batch_chars=0;raw_file=(staging/'raw_records.jsonl').open('x',encoding='utf-8')
            def flush():
                nonlocal batch,batch_chars
                if not batch:return
                chat={'id':peer,'kind':'group' if peer.endswith('@chatroom') else 'private','title':contact.get('remark') or contact.get('nick_name') or peer,'members':list(users)}
                payload={'format':FORMAT,'format_version':'2.0','namespace':'wechat:'+db.wxid,'users':list(users.values()),'chats':[chat],'messages':batch}
                path=staging/('batch_'+str(len(shards)).zfill(6)+'.json');path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
                if path.stat().st_size>64*1024*1024:raise ArchiveError('单批超过64MiB预算，未交付来源')
                shards.append({'file':path.name,'sha256':sha_file(path),'records':len(batch)});batch=[];batch_chars=0
                if guard:guard()
            try:
                import heapq,itertools
                streams=[]
                for connection,table in tables:
                    label=db._shard_label(connection)
                    sql=f'SELECT m.*,n.user_name AS sender_username,? AS shard FROM "{table}" m LEFT JOIN Name2Id n ON n.rowid=m.real_sender_id ORDER BY m.create_time DESC,m.sort_seq DESC,m.local_id DESC'
                    params=[label]
                    if not all_history:sql+=' LIMIT ?';params.append(limit)
                    streams.append(connection.execute(sql,params))
                merged=heapq.merge(*streams,key=lambda r:(r['create_time'],r['sort_seq'],r['shard'],r['local_id']),reverse=True)
                selected=merged if all_history else itertools.islice(merged,limit)
                for raw in selected:
                    row=dict(raw);records+=1;encoded=json.dumps(_json_value(row),ensure_ascii=False)
                    if progress and (records%100==0 or records==1 or records==expected):progress(f'正在读取聊天记录：{records} / {expected}；已取得 {attachments-media_missing} 个附件')
                    if len(encoded.encode('utf-8'))>16*1024*1024:raise ArchiveError('单条来源记录超过16MiB，未交付快照')
                    raw_file.write(encoded+'\n')
                    sender=source_sender(peer,row,users)
                    if sender and sender not in users:
                        users[sender]={'id':sender,'nickname':db.get_nickname(sender) or sender}
                    normalized=normalize_row(db,peer,row,users)
                    if normalized is None:unknown+=1;continue
                    if 'unmapped_kind' in normalized:retained_unmapped+=1
                    media_kind=normalized.get('unmapped_kind',normalized['kind'])
                    if media_kind in ('image','audio','video','emoji','file'):
                        kind='image' if media_kind=='emoji' else media_kind;file=None;variant='original'
                        if media_kind=='emoji':
                            directory=staging/'assets'/f'{records:08x}'
                            try:
                                file=emoji_cache.acquire(row,directory);variant=emoji_cache.last_variant;note_media(emoji_cache.last_status)
                            except Exception:
                                media_failures+=1;note_media('emoji_processing_failed')
                        elif media_reader and kind in ('image','audio','video'):
                            from .media_acquisition import acquire_media
                            try:
                                directory=staging/'assets'/f'{records:08x}'
                                file=acquire_media(media_reader,peer,row,directory);note_media(getattr(media_reader,'last_status','local_extracted' if file else 'cache_not_found'))
                                if kind=='image' and file:variant='thumbnail' if '_thumb.' in file.name else 'original' if '_h.' in file.name else 'compressed'
                            except Exception:
                                file=None;media_failures+=1;note_media(getattr(media_reader,'last_status','media_processing_failed'))
                        elif kind=='file':
                            try:
                                xml=ElementTree.fromstring(normalized['content'].split('\n',1)[1] if normalized['sender_id'] is None else normalized['content']);name=xml.findtext('.//appmsg/title') or ''
                                if name and Path(name).name==name and not any(c in name for c in '/\\:'):
                                    month=datetime.fromtimestamp(row['create_time'],timezone.utc).strftime('%Y-%m')
                                    original=resource_path(source_root,'msg/file/'+month+'/'+name)
                                    if original.is_file():
                                        file=staging/'assets'/f'{records:08x}'/name;file.parent.mkdir(parents=True,exist_ok=True)
                                        before=(original.stat().st_size,original.stat().st_mtime_ns,sha_file(original));shutil.copyfile(original,file)
                                        if before!=(original.stat().st_size,original.stat().st_mtime_ns,sha_file(file)):raise ConflictError('来源附件在复制时变化')
                            except (ElementTree.ParseError,ValidationError,OSError):file=None
                        if file is None:media_missing+=1
                        normalized['attachments']=[{'kind':kind,'path':file.relative_to(staging).as_posix() if file else None,'name':file.name if file else normalized['content'][:100],
                                                    'sha256':sha_file(file) if file else None,'variant':variant}];attachments+=1
                        if file and file.suffix=='.jpg' and file.with_suffix('.wxgf').is_file():
                            original=file.with_suffix('.wxgf');normalized['attachments'][0]['variant']='thumbnail'
                            normalized['attachments'].append({'kind':'file','path':original.relative_to(staging).as_posix(),'name':original.name,'sha256':sha_file(original),'variant':'original'});attachments+=1
                    if normalized['kind']=='system':
                        from ..message_content import forwarded_document
                        document=forwarded_document(normalized['content'])
                        if document:
                            from ..services.forward_resources import LocalForwardImages
                            if not hasattr(emoji_cache,'forward_images'):emoji_cache.forward_images=LocalForwardImages(source_root)
                            for index,item in enumerate(document['items']):
                                if not item.get('media') or not item['media']['images']:continue
                                directory=staging/'assets'/f'{records:08x}'/('forward_'+str(index))
                                try:file,variant=emoji_cache.forward_images.acquire(item['media'],directory,media_reader)
                                except Exception:file=None;variant=None;media_failures+=1
                                if file is None:media_missing+=1
                                normalized['attachments'].append({'kind':'image','path':file.relative_to(staging).as_posix() if file else None,'name':file.name if file else 'forward-'+str(index)+'.missing','sha256':sha_file(file) if file else None,'variant':variant or 'original'})
                                attachments+=1;note_media('forward_local_verified' if file else 'forward_local_unavailable')
                    batch.append(normalized)
                    batch_chars+=len(normalized.get('content',''))
                    if len(batch)>=2000 or batch_chars>8*1024*1024:flush()
                flush()
                if records!=expected:raise ConflictError('来源消息计数与投影数量不一致，未交付快照')
            finally:raw_file.close()
        result=db._run_msg_query(peer,project)
        # SDK callbacks can legitimately return None; source tables were validated in project.
        if not (staging/'raw_records.jsonl').exists():raise ArchiveError('未取得所选来源表')
        if guard:guard()
        manifest={'format':'sixu-source-snapshot','format_version':'1.0','records':records,'typed_records':sum(x['records'] for x in shards),'unresolved_senders':unknown,'attachments':attachments,
                  'retained_unmapped_senders':retained_unmapped,'media_failures':media_failures,'media_missing':media_missing,'batches':shards,'raw_file':'raw_records.jsonl','raw_sha256':sha_file(staging/'raw_records.jsonl'),'media_component':media_error or ('pinned-local-and-verified-cdn' if allow_cdn else 'pinned-local-only'),'media_status_counts':media_status_counts,'allow_cdn':allow_cdn}
        (staging/'rich_snapshot.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        if target.exists():raise ConflictError('来源输出已存在')
        staging.rename(target);staging=None
        return {'output':str(target),'records':records,'all_history':all_history,'attachments':attachments,'unresolved_senders':unknown,'keys_written':False,'media_local_only':not allow_cdn,'media_available':attachments-media_missing,'media_missing':media_missing,'media_failures':media_failures,'media_component':media_error or ('pinned-local-and-verified-cdn' if allow_cdn else 'pinned-local-only'),'media_status_counts':media_status_counts,'allow_cdn':allow_cdn}
    finally:
        if staging and staging.parent==staging_home and staging.name.startswith('.sixu-capture-'):shutil.rmtree(staging)
