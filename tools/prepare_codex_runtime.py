"""Download the fixed official Windows runtime and verify every executable."""
import base64,hashlib,io,json,tarfile
from pathlib import Path
from urllib.request import urlopen

URL='https://registry.npmjs.org/@openai/codex/-/codex-0.162.1-win32-x64.tgz'
INTEGRITY='dfl4MhHuEi0ARKyNmrTxk+RQmsWNCQAoVLUtrYq+yrW1C8P2sg5ziwgHUUACHjYLKuACV7ARH5Nq5pnCz3GlaQ=='
LICENSE_FILE=Path(__file__).resolve().parents[1]/'packaging/CODEX_APACHE_LICENSE.txt'
LICENSE_SHA256='d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc'
EXPECTED={'codex.exe':'dd13bdb162a184fa04039488b234a8258ef9b76f84e926c505d5742b19249a6a','codex-code-mode-host.exe':'9f865a748c984492ca9b69aac75680e4954f31311c43ec33ddbdae0ed77bd4bd'}

def prepare(target):
    target=Path(target)
    if target.exists():raise ValueError('Runtime output must be a new directory')
    with urlopen(URL,timeout=120) as response:data=response.read(256*1024*1024+1)
    if len(data)>256*1024*1024 or hashlib.sha512(data).digest()!=base64.b64decode(INTEGRITY):raise ValueError('Official runtime archive integrity mismatch')
    outputs={}
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        for member in archive:
            name=Path(member.name).name
            if not member.isfile() or name not in (*EXPECTED,'LICENSE'):continue
            if name in outputs:raise ValueError('Duplicate runtime file')
            if member.size>512*1024*1024:raise ValueError('Runtime member exceeds budget')
            outputs[name]=archive.extractfile(member).read()
    for name,digest in EXPECTED.items():
        if name not in outputs or hashlib.sha256(outputs[name]).hexdigest()!=digest:raise ValueError('Fixed runtime executable mismatch: '+name)
    if 'LICENSE' not in outputs:
        if not LICENSE_FILE.is_file():raise ValueError('Official runtime license missing')
        license_data=LICENSE_FILE.read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(license_data).hexdigest()!=LICENSE_SHA256:raise ValueError('Official license integrity mismatch')
        outputs['LICENSE']=license_data
    target.mkdir(parents=True)
    for name,content in outputs.items():(target/name).write_bytes(content)
    manifest={'version':'0.162.1','package':{'version':'0.162.1-win32-x64','resolved':URL,'integrity':'sha512-'+INTEGRITY},'license':'Apache-2.0','files':[{'name':name,'sha256':digest,'size_bytes':len(outputs[name])} for name,digest in EXPECTED.items()]}
    (target/'runtime_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Fixed official Codex runtime verified')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('target',type=Path);prepare(parser.parse_args().target)
