"""检查 Git 索引中的路径和实际 blob；只报告路径/类别，不回显敏感值。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

FORBIDDEN_ROOTS={'data','import_logs','sources','backups','backup','exports','readable_exports','outputs','reports','evidence','validation','private','codex_plugin','android_mock','.venv','venv','build','dist','releases','.codex','.ssh','.secrets','secrets','keys','credentials','__pycache__'}
FORBIDDEN_PARTS={'micromsg','db_storage','xwechat_files','backupfiles','chatpackage','media','index'}
FORBIDDEN_NAMES={'auth.json','credentials.json','token.json','tokens.json','keys.json','key_cache.json','decryption_keys.json','.env'}
FORBIDDEN_SUFFIXES={'.db','.sqlite','.sqlite3','.bak','.backup','.bkp','.pem','.key','.pfx','.p12','.keystore','.exe','.dll','.msi','.zip','.7z','.rar','.tar','.tgz','.whl','.pyc','.pyo','.log','.tmp'}
SECRET_PATTERNS={
    'API 密钥':re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}'),
    '登录令牌':re.compile(rb'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    '私钥':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'URL 内凭据':re.compile(rb'https?://[^\s:@/]+:[^\s@/]+@'),
}
WXID=re.compile(rb'\bwxid_[A-Za-z0-9]{10,}\b')
CREDENTIAL_ASSIGNMENT=re.compile(rb'(?i)["\x27]?(?:OPENAI_API_KEY|MODEL_API_KEY|access_token|refresh_token|client_secret|password|api_key|secret_key)["\x27]?\s*[:=]\s*["\x27]([^"\x27\r\n]+)["\x27]')
SAFE_VALUE_MARKERS=('example','placeholder','dummy','mock','unit','test','your_','your-','<','changeme')


def git(root,*args):
    result=subprocess.run(['git','-C',str(root),*args],capture_output=True)
    if result.returncode:raise RuntimeError('Git 索引读取失败，检查仓库/索引权限。')
    return result.stdout


def path_problem(name,approved=False):
    path=Path(name);parts=[part.lower() for part in path.parts];base=parts[-1]
    if any(part=='ai_history' or part.endswith('.media') for part in parts):return '聊天历史或附件目录'
    if parts[0] in FORBIDDEN_ROOTS or parts[0].startswith(('private_','real_')):return '私有数据/生成目录'
    if any(part in FORBIDDEN_PARTS for part in parts) and not approved or any(part.endswith('.egg-info') for part in parts):return '来源/缓存目录'
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or re.search(r'\.(db|sqlite3?)-',base):return '数据库、密钥或产物'
    if base in FORBIDDEN_NAMES or base.startswith('.env.') and name!='.env.example':return '凭据文件'
    if name.startswith('docs/BACKUP_INSPECTION_') or name in ('docs/REAL_WECHAT_MVP_ACCEPTANCE.md','docs/REAL_SOURCE_FINAL_REPORT.md'):return '私有验收资料'
    return None


def content_problems(name,data,approved=False):
    issues=[]
    for label,pattern in SECRET_PATTERNS.items():
        if pattern.search(data):issues.append(label)
    for match in WXID.finditer(data):
        suffix=match.group()[5:].lower()
        if len(set(suffix))>1:issues.append('疑似真实微信标识');break
    for match in CREDENTIAL_ASSIGNMENT.finditer(data):
        value=match.group(1).decode('utf-8',errors='replace').lower()
        if len(value)>=8 and not any(marker in value for marker in SAFE_VALUE_MARKERS):issues.append('疑似凭据赋值');break
    if b'\x00' in data and not approved:issues.append('未经审查的二进制内容')
    if len(data)>2*1024*1024 and not approved:issues.append('未经审查的大文件')
    if name.endswith('.json'):
        try:
            value=json.loads(data)
            if isinstance(value,dict):
                known=value.get('format') in ('chat-exchange','wechat-mock-export','wechat-external-export','android-wechat-source')
                payload=isinstance(value.get('messages'),list) or isinstance(value.get('records'),list) and 'account' in value
                if (known or payload) and not approved:issues.append('未登记的聊天/来源样例')
        except (UnicodeError,ValueError):pass
    return sorted(set(issues))


def scan(root,staged=False):
    entries=git(root,'ls-files','--stage','-z').split(b'\0');results=[];count=0
    parsed=[entry.split(b'\t',1) for entry in entries if entry]
    policy_entry=next((header for header,name in parsed if name==b'tools/privacy_fixtures.json'),None)
    allowed={}
    if policy_entry:
        oid=policy_entry.split()[1].decode('ascii')
        allowed=json.loads(git(root,'cat-file','blob',oid)).get('synthetic_files',{})
    for entry in entries:
        if not entry:continue
        header,name_bytes=entry.split(b'\t',1);mode,oid,stage=header.split();name=name_bytes.decode('utf-8');count+=1
        if stage!=b'0':results.append({'path':name,'reason':'未解决的合并冲突'});continue
        if mode in (b'120000',b'160000'):results.append({'path':name,'reason':'未审查的链接/嵌套仓库'});continue
        data=git(root,'cat-file','blob',oid.decode('ascii'))
        approved=name.startswith(('examples/','wechat_mock/')) and allowed.get(name)==hashlib.sha256(data).hexdigest()
        problem=path_problem(name,approved)
        if problem:results.append({'path':name,'reason':problem})
        for problem in content_problems(name,data,approved):results.append({'path':name,'reason':problem})
    return {'checked_index_files':count,'findings':results,'scope':'实际 Git 索引 blob（包括此前已跟踪的文件）'}


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--staged',action='store_true')
    options=parser.parse_args(argv)
    try:result=scan(options.repo,options.staged)
    except (RuntimeError,OSError,ValueError) as error:print(str(error),file=sys.stderr);return 2
    if result['findings']:
        print('提交已阻止：索引中有需要审查的内容。',file=sys.stderr)
        for issue in result['findings']:print(issue['path']+'：'+issue['reason'],file=sys.stderr)
        return 1
    print(f"Git 隐私检查通过：{result['checked_index_files']} 个索引文件；没有检测到受限路径或已知敏感模式。")
    return 0


if __name__=='__main__':raise SystemExit(main())
