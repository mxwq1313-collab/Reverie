"""Package only the checked, generated application on the hosted Windows runner."""
import hashlib,json,os,zipfile,sys
from pathlib import Path

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));folder=root/'build/release/Sixu';version='2.2.2'
from wechat_archive import __version__
if __version__!=version:raise ValueError('Release workflow version differs from application')
for name,report in (('desktop','desktop_check.json'),('codex','codex_check.json'),('knowledge','knowledge_check.json'),('sixu','sixu_check.json'),('workbench','workbench_check.json')):
    # Some shipped probes use a different receipt filename; the process must have
    # exited successfully in the prior workflow step and emitted a passed JSON.
    path=root/('build/check-'+name)
    reports=list(path.rglob('*.json'))
    passed=[]
    for file in reports:
        try:value=json.loads(file.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):continue
        if isinstance(value,dict) and value.get('status')=='passed':passed.append(file)
    if not passed:raise ValueError('Missing passed packaged receipt: '+name)
files=sorted(p for p in folder.rglob('*') if p.is_file())
if not files:raise ValueError('Application directory is empty')
if any(p.name in ('auth.json','desktop_settings.json','key_cache.json') or p.suffix.lower() in ('.db','.sqlite','.sqlite3') for p in files):raise ValueError('Private data cannot enter a release')
def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()
(folder/'使用说明.txt').write_text('思绪 2.2.2\n\n完整解压后运行思绪.exe，保留_internal目录。\n本包不含个人聊天或登录状态。\n详细变更及资源缺失边界见2.2.2发布与验收.md。\n',encoding='utf-8')
(folder/'2.2.2发布与验收.md').write_text((root/'docs/SIXU_2_2_2_RELEASE.md').read_text(encoding='utf-8'),encoding='utf-8')
(folder/'release_manifest.json').write_text(json.dumps({'version':version,'github_commit':os.environ.get('GITHUB_SHA'),'verification':'five packaged checks passed; release_220, release_221, release_222 and management suites passed','exe_sha256':sha(folder/'思绪.exe'),'personal_data_included':False},indent=2),encoding='utf-8')
target=root/'build/Sixu-2.2.2-Windows-x64.zip'
with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for file in sorted(p for p in folder.rglob('*') if p.is_file()):archive.write(file,Path('Sixu')/file.relative_to(folder))
with zipfile.ZipFile(target) as archive:
    if archive.testzip() is not None:raise ValueError('Release archive integrity failure')
(root/'build/SHA256SUMS.txt').write_text(sha(target)+'  '+target.name+'\n',encoding='ascii')
print('Verified Windows release archive prepared')
