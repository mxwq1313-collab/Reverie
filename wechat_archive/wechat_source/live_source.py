"""桌面来源工作进程：固定已审查 SDK，账号明确选择，原库只读。"""

import contextlib
import sqlite3
from datetime import datetime,timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import shutil
import sys
from uuid import uuid4
import time

from ..errors import ArchiveError,ConflictError,ValidationError
from ..exporter.readable import _local_path
from .acquisition import _load_sdk,_client_version,_json_value,QuietSink,TOOL_VERSION,TOOL_WHEEL_SHA


class ReadWarnings(logging.Handler):
    def __init__(self):super().__init__(logging.WARNING);self.count=0
    def emit(self,record):self.count+=1


def discover_accounts(root=None,work=None):
    sdk=_load_sdk()
    source=str(_local_path(root)) if root else sdk.auto_detect_db_dir()
    if not source:raise ArchiveError('未找到电脑微信数据目录，请先登录微信，或在界面选择数据目录。')
    rows=sdk.list_accounts(source)
    if not rows:raise ArchiveError('该目录没有可识别的电脑微信账号，不是受支持的数据来源。')
    accounts=[]
    for row in rows:
        item={'account':row['account'],'wxid':row['wxid'],'nickname':row.get('self_nick') or '', 'weixin_id':'','identity_status':'unverified'}
        if work is not None:
            slot=hashlib.sha256(row['account'].encode('utf-8')).hexdigest()[:16]
            try:
                db,owner=open_account(source,row['account'],Path(work)/'decoded'/('identity_'+slot),contact_only=True)
                item.update(nickname=owner['nick_name'],weixin_id=self_alias(db),identity_status='verified')
            except (ArchiveError,OSError,RuntimeError,ValueError,sqlite3.Error):item['identity_status']='login_required'
        accounts.append(item)
    return {'root':str(Path(source).resolve()),'accounts':accounts,'client_version':_client_version()}


def self_alias(db):
    files=[rel for rel,path,_ in db._db_files if Path(path).name=='contact.db']
    if len(files)!=1:return ''
    connection=db._open(files[0])
    try:
        columns={row['name'] for row in connection.execute('PRAGMA table_info(contact)')}
        if not {'username','alias'}<=columns:return ''
        row=connection.execute('SELECT alias FROM contact WHERE username=? LIMIT 1',(db.wxid,)).fetchone()
        return row[0].strip() if row and isinstance(row[0],str) else ''
    finally:connection.close()



def open_account(root,account,work,*,contact_only=False):
    sdk=_load_sdk();root=_local_path(root);work=_local_path(work)
    if root==work or root in work.parents:raise ValidationError('工作副本不能位于微信原数据目录内。')
    available={row['account'] for row in sdk.list_accounts(str(root))}
    if account not in available:raise ArchiveError('所选账号已不存在，请重新检测账号。')
    from .snapshot_view import StableReadViews
    class ReadOnlyAccount(StableReadViews,sdk.WeChatDB):
        def _save_keys(self):pass
        def _stable_key_dirs(self):return [str(work/'unused_keys')]
        def _try_other_accounts(self):return False
        def _collect_db_files(self):
            rows=super()._collect_db_files()
            if any(Path(row[1]).name.lower()=='enmicromsg.db' for row in rows):raise ArchiveError('不读取 Android 数据库。')
            if contact_only:
                rows=[row for row in rows if Path(row[1]).name=='contact.db']
                if len(rows)!=1:raise ArchiveError('账号联系人身份来源不唯一，不能推断账号名称。')
            return rows
    db=ReadOnlyAccount(db_dir=str(root),account=account,workdir=str(work/'decoded'),keys_file=str(work/'no_keys.json'))
    owner=db.get_self_info()
    if owner.get('username')!=db.wxid or not owner.get('nick_name'):raise ArchiveError('账号身份无法核验，不能读取此来源。')
    if len(db._keys)<len(db._db_files):raise ArchiveError('部分数据库无法通过读取校验，请确认所选账号已登录；不导入不完整来源。')
    return db,owner


def source_stamp(db,include_all=False):
    result=[]
    for rel,path,_ in db._db_files:
        if not include_all and not Path(path).name.startswith('message_'):continue
        for candidate in (Path(path),Path(str(path)+'-wal')):
            if candidate.exists():
                info=candidate.stat();result.append((str(candidate),info.st_size,info.st_mtime_ns))
    return result


def read_contacts(db,keyword=None,peer=None):
    files=[(rel,path) for rel,path,_ in db._db_files if Path(path).name=='contact.db']
    if len(files)!=1:raise ArchiveError('未找到唯一的联系人数据库，未知来源明确拒绝。')
    connection=db._open(files[0][0])
    try:
        columns={row['name'] for row in connection.execute('PRAGMA table_info(contact)')}
        if not {'username','nick_name','remark'}<=columns:raise ArchiveError('联系人字段结构未登记，不能猜测身份。')
        clause=' WHERE username=?' if peer else ' WHERE instr(username,?)>0 OR instr(nick_name,?)>0 OR instr(remark,?)>0' if keyword else ''
        params=(peer,) if peer else (keyword,)*3 if keyword else ()
        rows=[dict(row) for row in connection.execute('SELECT username,nick_name,remark FROM contact'+clause+' ORDER BY username LIMIT 10001',params)]
        if len(rows)>10000:raise ArchiveError('联系人超过 10000 项，当前上限明确拒绝。')
        return rows
    finally:connection.close()


def extract_records(db,peer,limit=50,all_history=False):
    if type(limit) is not int or not 1<=limit<=100000:raise ValidationError('读取数量须为 1–100000。')
    if not isinstance(peer,str) or not peer or peer.endswith('@chatroom') or peer==db.wxid or peer.startswith('gh_'):
        raise ArchiveError('请选择真实私聊联系人；群聊及公众号当前不支持。')
    rows=[];offset=0;seen=set();page_size=100001 if all_history else limit
    before=source_stamp(db)
    while True:
        page=db.get_messages(peer,limit=page_size,offset=offset)
        if not page:break
        if len(page)>100000:raise ArchiveError('会话超过 100000 条来源记录，当前上限明确拒绝；未写入归档。')
        for native in page:
            identity=(native['shard'],native['local_id'])
            if identity in seen:raise ArchiveError('分页消息重复或来源正在变化，拒绝不完整读取，请稍后重试。')
            seen.add(identity)
            raw=db.get_message_row(peer,native['local_id'],shard=native['shard'])
            source_id=raw.get('server_id',0) if raw else 0
            rows.append({'local_id':native['local_id'],'source_database':native['shard'],'source_message_id':str(source_id if source_id>0 else native['local_id']),
                         'source_id_kind':'server' if source_id>0 else 'local','sender_wxid':native['sender_username'],'timestamp':native['create_time'],
                         'content':raw['content'] if raw and isinstance(raw.get('content'),str) and raw.get('local_type')==1 else native['content'],
                         'raw_type':raw.get('local_type') if raw else native['type'],'raw_payload':_json_value({'native':native,'database_row':raw})})
            if len(rows)>100000:raise ArchiveError('会话超过 100000 条来源记录，当前上限明确拒绝；未写入归档。')
        offset+=len(page)
        break  # SDK 单次合并窗口；避免动态分片分页造成重复窗口或漏项。
    after=source_stamp(db)
    if after!=before:
        old={row[0]:row[1:] for row in before};new={row[0]:row[1:] for row in after};changed=sorted({Path(key).name for key in old.keys()|new.keys() if old.get(key)!=new.get(key)})
        raise ArchiveError('微信消息分片在读取期间变化（'+', '.join(changed)+'），未导入；请稍后重试。')
    return rows


def publish_progress(work,text):
    try:
        temporary=work/'progress.tmp';temporary.write_text(json.dumps({'text':text},ensure_ascii=False),encoding='utf-8');temporary.replace(work/'progress.json')
    except OSError:pass  # A transient status-file lock must never abort source acquisition.


def perform(request):
    if request.get('action') not in {'accounts','contacts','capture','snapshot','rich_capture','avatars'}:raise ValidationError('未知的微信读取操作。')
    with contextlib.redirect_stdout(QuietSink()),contextlib.redirect_stderr(QuietSink()):
        if request['action']=='accounts':return discover_accounts(request.get('root'),request.get('workdir'))
        work=_local_path(request['workdir']);db,owner=open_account(request['root'],request['account'],work)
        warnings=ReadWarnings();logger=logging.getLogger('readonly_wechat_source');logger.addHandler(warnings)
        try:
            if request['action']=='avatars':
                from .avatar_source import read_avatars
                return read_avatars(db,request.get('peers'),work/'avatars')
            if request['action']=='contacts':
                candidates=read_contacts(db,request.get('keyword'))
                contacts=[{'username':row['username'],'name':row.get('remark') or row.get('nick_name') or row['username']} for row in candidates if row['username']!=db.wxid and not row['username'].endswith('@chatroom') and not row['username'].startswith('gh_')]
                if request.get('rich'):
                    from .rich_source import contacts_with_groups
                    contacts=contacts_with_groups(db,candidates,request.get('keyword'))
                if warnings.count:raise ArchiveError('联系人读取存在未支持结构或失败，拒绝显示不完整结果。')
                return {'owner':{'wxid':db.wxid,'nickname':owner['nick_name'],'weixin_id':self_alias(db)},'contacts':contacts,'keys_written':False,'client_version':_client_version()}
            peer=request['peer'];matches=read_contacts(db,peer=peer)
            if len(matches)!=1:raise ArchiveError('联系人身份无法精确核验，读取拒绝。')
            if request['action']=='rich_capture':
                from .rich_source import capture_rich
                before=source_stamp(db,include_all=True)
                def guard():
                    if warnings.count:raise ArchiveError('读取组件报告不可读分片或未合并日志，未导入；请稍后重试。')
                    if hasattr(db,'check_read_views'):db.check_read_views()
                    elif source_stamp(db,include_all=True)!=before:raise ArchiveError('来源在读取期间变化，未导入；请重新读取。')
                def progress(text):
                    publish_progress(work,text)
                return capture_rich(db,owner,matches[0],request['output'],all_history=request.get('all_history',False),limit=request.get('limit',50),guard=guard,allow_cdn=request.get('allow_cdn') is True,progress=progress,staging_parent=work/'rich_staging')
            if request['action']=='snapshot':
                from .snapshot import project_snapshot,SNAPSHOT_API
                if not isinstance(peer,str) or not peer or peer.endswith('@chatroom') or peer==db.wxid or peer.startswith('gh_'):
                    raise ArchiveError('快照仅支持明确选定的私聊，不扩展群聊/公众号。')
                output=_local_path(request['output']);root=_local_path(request['root'])
                if output==root or root in output.parents or output.exists():raise ConflictError('快照须为原微信目录之外的新目录。')
                contact=matches[0]
                header={'format':'wechat-external-export','format_version':'1.0','source_platform':'wechat',
                    'provider':{'name':'wechatauto-replica','version':TOOL_VERSION,'api':SNAPSHOT_API,'distribution_sha256':TOOL_WHEEL_SHA},
                    'account':{'wxid':db.wxid,'nickname':owner['nick_name'],'verification':'contact_row'},
                    'conversation':{'wxid':peer,'nickname':contact.get('remark') or contact.get('nick_name') or peer,'kind':'private'},
                    'timestamp_unit':'unix_seconds','capture':{'origin':'real_local_wechat','client_version':_client_version(),
                    'captured_at':datetime.now(timezone.utc).isoformat(),'validated_database_keys':len(db._keys),'key_cache_written':False}}
                before=source_stamp(db)
                def guard():
                    if warnings.count or source_stamp(db)!=before or len(db._keys)<len(db._db_files):
                        raise ArchiveError('选定来源在快照期间变化或有未核验分片，未交付快照。')
                def project(tables):
                    selected=[(connection,table,db._shard_label(connection)) for connection,table in tables]
                    return project_snapshot(selected,header,output,guard=guard,staging_parent=work/'snapshot_staging')
                result=db._run_msg_query(peer,project)
                if result is None:raise ArchiveError('未取得登记会话表，无法将未知情况当成空历史。')
                return {**result,'all_history':True}
            records=extract_records(db,peer,request.get('limit',50),request.get('all_history',False))
            if warnings.count:raise ArchiveError('消息读取工具报告部分来源不可读或未知结构，整批拒绝，未写入归档。')
            contact=matches[0]
            payload={'format':'wechat-external-export','format_version':'1.0','source_platform':'wechat',
                'provider':{'name':'wechatauto-replica','version':TOOL_VERSION,'api':'WeChatDB.get_messages+get_message_row','distribution_sha256':TOOL_WHEEL_SHA},
                'account':{'wxid':db.wxid,'nickname':owner['nick_name'],'verification':'contact_row'},
                'conversation':{'wxid':peer,'nickname':contact.get('remark') or contact.get('nick_name') or peer,'kind':'private'},'timestamp_unit':'unix_seconds',
                'capture':{'origin':'real_local_wechat','client_version':_client_version(),'captured_at':datetime.now(timezone.utc).isoformat(),'validated_database_keys':len(db._keys),'key_cache_written':False},'records':records}
            output=_local_path(request['output']);root=_local_path(request['root'])
            if output==root or root in output.parents or output.exists():raise ConflictError('来源导出必须是原微信目录之外的新文件。')
            encoded=json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
            if len(encoded)>64*1024*1024:raise ArchiveError('来源超过 64 MiB 上限，明确拒绝；未导入。')
            output.parent.mkdir(parents=True,exist_ok=True)
            with output.open('xb') as stream:stream.write(encoded)
            return {'output':str(output),'records':len(records),'source_sha256':hashlib.sha256(encoded).hexdigest(),'keys_written':False,'all_history':bool(request.get('all_history'))}
        finally:logger.removeHandler(warnings)


def worker_main(request_file,result_file):
    try:
        request=json.loads(Path(request_file).read_text(encoding='utf-8'));result={'status':'success','data':perform(request)};code=0
    except Exception as error:
        reason=str(error) if isinstance(error,ArchiveError) else '读取组件未完整打包：'+str(error) if isinstance(error,ImportError) else '微信读取失败，请确认客户端已登录、账号和格式受支持。'
        result={'status':'failed','error':reason,'error_type':type(error).__name__};code=1
    from .. import __version__
    result['app_version']=__version__;result['read_strategy']='stable-per-database-immutable'
    with Path(result_file).open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    return code


def run_source_job(action,data_dir,**options):
    cancel=options.pop('cancel_event',None)
    progress=options.pop('progress_callback',None);last_progress=None
    base=_local_path(data_dir)/'source_jobs';job=base/uuid4().hex;job.mkdir(parents=True)
    request={'action':action,'workdir':str(job),**options}
    input_file=job/'request.json';output_file=job/'result.json';input_file.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
    if getattr(sys,'frozen',False):args=[sys.executable,'--wechat-worker',str(input_file),'--worker-result',str(output_file)]
    else:args=[sys.executable,'-m','wechat_archive.wechat_source.live_source',str(input_file),str(output_file)]
    env=__import__('os').environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])+__import__('os').pathsep+env.get('PYTHONPATH','')
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    started=time.monotonic()
    try:
        while True:
            if progress:
                try:
                    update=json.loads((job/'progress.json').read_text(encoding='utf-8')).get('text')
                    if isinstance(update,str) and update!=last_progress:progress(update);last_progress=update
                except (OSError,ValueError):pass
            if cancel is not None and cancel.is_set():
                process.kill();process.communicate();raise ArchiveError('已取消微信读取，未开始导入。')
            try:process.communicate(timeout=0.2);break
            except subprocess.TimeoutExpired:
                if time.monotonic()-started>(24*60*60 if action in ('rich_capture','snapshot') else 900):
                    process.kill();process.communicate();raise ArchiveError('微信读取超时，未开始导入。')
    finally:
        for name in ('decoded','snapshot_staging','rich_staging'):
            private=job/name
            if private.is_dir() and private.resolve().parent==job.resolve():
                try:shutil.rmtree(private)
                except OSError:pass  # 句柄尚在时保留私有临时文件，不改变原库。
    if not output_file.is_file():raise ArchiveError('读取工作进程没有返回结果，请检查软件版本和读取组件。')
    result=json.loads(output_file.read_text(encoding='utf-8'))
    if result['status']!='success':raise ArchiveError(result['error'])
    return result['data']


if __name__=='__main__':raise SystemExit(worker_main(sys.argv[1],sys.argv[2]))
