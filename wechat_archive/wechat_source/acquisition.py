"""Layer 1：隔离调用成熟提取工具的 DB API，不实现底层解密。"""

import base64
import contextlib
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

from ..errors import ArchiveError

TOOL_VERSION='1.2.6.1'
TOOL_WHEEL_SHA='5400c6e2155f157fac2caa3c0786f1035a81d3e1246427ab52771a3c992a81fc'
SDK_DB_SHA='9d4eba69e868dea8000d8acdbaed723149cf8732c52e097f23fb3b07fa5ddc55'


class QuietSink:
    def write(self,value):return len(value)
    def flush(self):pass


def _json_value(value):
    if isinstance(value,bytes):return {'encoding':'base64','data':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict):return {str(k):_json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_json_value(v) for v in value]
    return value


def _load_sdk():
    distribution=importlib.metadata.distribution('wechatauto-replica')
    if distribution.version!=TOOL_VERSION:raise ArchiveError('未审查的提取工具版本，拒绝获取')
    path=Path(distribution.locate_file('wechatauto/db.py'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=SDK_DB_SHA:
        raise ArchiveError('提取工具 DB 模块与已审查发行包不一致')
    package=types.ModuleType('wechatauto');package.__path__=[str(path.parent)]
    logger=types.ModuleType('wechatauto.logger')
    logger.wxlog=logging.getLogger('readonly_wechat_source');logger.wxlog.addHandler(logging.NullHandler());logger.wxlog.propagate=False
    # 包门面会导入 UI/OCR 模块；此隔离工作进程只加载未修改的 DB API。
    sys.modules['wechatauto']=package;sys.modules['wechatauto.logger']=logger
    spec=importlib.util.spec_from_file_location('wechatauto.db',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def _client_version():
    script="(Get-Process -Name Weixin -ErrorAction SilentlyContinue | Select-Object -First 1).Path | ForEach-Object { (Get-Item -LiteralPath $_).VersionInfo.FileVersion }"
    system=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(system),'-NoProfile','-Command',script],capture_output=True,text=True,timeout=15,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return result.stdout.strip() or 'unknown'


def capture_private(path,*,peer=None,limit=50,workdir=None):
    if sys.platform!='win32':raise ArchiveError('本阶段来源获取只支持 Windows 微信')
    raw=str(path)
    if '://' in raw or raw.startswith(('\\\\','//')) or '..' in Path(raw).parts or any(ord(c)<32 for c in raw):
        raise ArchiveError('获取输出必须是明确的本机路径')
    path=Path(path).expanduser().resolve()
    if path.exists() or path.suffix.lower()!='.json':raise ArchiveError('获取输出必须是新的 .json 文件，不能覆盖既有文件')
    if type(limit) is not int or not 2<=limit<=500:raise ArchiveError('私聊读取数量须为 2–500')
    private=Path(workdir).resolve() if workdir else Path(tempfile.mkdtemp(prefix='wechat-source-'))
    with contextlib.redirect_stdout(QuietSink()),contextlib.redirect_stderr(QuietSink()):
        sdk=_load_sdk()
        source=sdk.auto_detect_db_dir();accounts=sdk.list_accounts(source)
        if not source or not accounts:raise ArchiveError('未找到 Windows 微信数据目录，请登录并确认数据位置')
        root=Path(source).resolve()
        if path==root or root in path.parents or private==root or root in private.parents:
            raise ArchiveError('导出和工作副本不能写入微信原数据目录')
        class EphemeralDB(sdk.WeChatDB):
            def _save_keys(self):pass
            def _stable_key_dirs(self):return [str(private/'unused_keys')]
            def _try_other_accounts(self):return False
            def _collect_db_files(self):
                files=super()._collect_db_files()
                if any(Path(item[1]).name.lower()=='enmicromsg.db' for item in files):
                    raise ArchiveError('来源包含未登记的 Android 数据库，拒绝获取')
                return files
        db=EphemeralDB(db_dir=source,account=accounts[0]['account'],workdir=str(private/'decoded'),keys_file=str(private/'no_keys.json'))
        owner=db.get_self_info()
        if owner.get('username')!=db.wxid or not owner.get('nick_name'):
            raise ArchiveError('未取得可核验的账号联系人身份')
        peers=[peer] if peer else [s['username'] for s in db.get_sessions(limit=50) if s['username'].startswith('wxid_') and s['username']!=db.wxid and not s['username'].endswith('@chatroom')]
        selection=None
        for username in peers:
            if not isinstance(username,str) or username.endswith('@chatroom') or username==db.wxid:continue
            contacts=[c for c in db.search_contact(username) if c.get('username')==username]
            if len(contacts)!=1:continue
            records=[]
            for native in db.get_messages(username,limit=limit):
                raw=db.get_message_row(username,native['local_id'],shard=native['shard'])
                source_id=raw.get('server_id',0) if raw else 0
                records.append({'local_id':native['local_id'],'source_database':native['shard'],
                                'source_message_id':str(source_id) if source_id>0 else str(native['local_id']),
                                'source_id_kind':'server' if source_id>0 else 'local','sender_wxid':native['sender_username'],
                                'timestamp':native['create_time'],'content':raw['content'] if raw and isinstance(raw.get('content'),str) and raw.get('local_type')==1 else native['content'],
                                'raw_type':raw.get('local_type') if raw else native['type'],
                                'raw_payload':_json_value({'native':native,'database_row':raw})})
            texts=[r for r in records if r['raw_type']==1 and r['sender_wxid'] in {db.wxid,username} and isinstance(r['content'],str) and r['content'].strip() and isinstance(r['raw_payload'].get('database_row',{}).get('content'),str)]
            if {r['sender_wxid'] for r in texts}!={db.wxid,username}:continue
            selection=(username,contacts[0],records,texts);break
        if selection is None:raise ArchiveError('未找到可核验的双向私聊文本；请指定稳定 wxid 或提高读取数量')
        username,contact,records,texts=selection
        payload={'format':'wechat-external-export','format_version':'1.0','source_platform':'wechat',
                 'provider':{'name':'wechatauto-replica','version':TOOL_VERSION,'api':'WeChatDB.get_messages+get_message_row','distribution_sha256':TOOL_WHEEL_SHA},
                 'account':{'wxid':db.wxid,'nickname':owner['nick_name'],'verification':'contact_row'},
                 'conversation':{'wxid':username,'nickname':contact.get('remark') or contact.get('nick_name') or username,'kind':'private'},
                 'timestamp_unit':'unix_seconds','capture':{'origin':'real_local_wechat','client_version':_client_version(),
                 'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'validated_database_keys':len(db._keys),'key_cache_written':False},'records':records}
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='\n') as handle:json.dump(payload,handle,ensure_ascii=False,indent=2,allow_nan=False)
    return {'status':'captured','provider_version':TOOL_VERSION,'output':str(path),'records':len(records),'text_candidates':len(texts),
            'outgoing':sum(r['sender_wxid']==db.wxid for r in texts),'incoming':sum(r['sender_wxid']==username for r in texts),
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'keys_written':False,'ui_or_send_used':False}


def run_worker(tool_python,path,*,peer=None,limit=50,workdir=None):
    python=Path(tool_python).expanduser().resolve()
    if not python.is_file():raise ArchiveError('提取工具 Python 不存在；使用已安装指定工具的独立环境')
    package_root=Path(__file__).resolve().parents[2]
    args=[str(python),'-m','wechat_archive.wechat_source.acquisition','--worker','--output',str(Path(path).resolve()),'--limit',str(limit)]
    if peer:args += ['--peer',peer]
    if workdir:args += ['--workdir',str(Path(workdir).resolve())]
    env=os.environ.copy();env['PYTHONPATH']=str(package_root)+os.pathsep+env.get('PYTHONPATH','')
    result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',env=env,timeout=240,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:report=json.loads(result.stdout)
    except ValueError as exc:raise ArchiveError('提取工作进程未返回有效报告；原始输出未向外暴露') from exc
    if result.returncode:raise ArchiveError(report.get('error','真实来源获取失败'))
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');parser.add_argument('--output',required=True)
    parser.add_argument('--peer');parser.add_argument('--limit',type=int,default=50);parser.add_argument('--workdir')
    options=parser.parse_args()
    try:report=capture_private(options.output,peer=options.peer,limit=options.limit,workdir=options.workdir)
    except Exception as exc:
        # SDK 可能在异常中带内部路径/密钥；仅公开自身 ArchiveError 或类型。
        report={'status':'failed','error':str(exc) if isinstance(exc,ArchiveError) else '第三方来源读取失败，未生成导出文件','error_type':type(exc).__name__}
        print(json.dumps(report,ensure_ascii=True));return 1
    print(json.dumps(report,ensure_ascii=True));return 0


if __name__=='__main__':raise SystemExit(main())
