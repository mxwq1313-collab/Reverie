from pathlib import Path
import sys,os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules,copy_metadata
import importlib.metadata
import hashlib

project=Path(SPECPATH).parent.resolve()
sys.path.insert(0,str(project))
sdk=importlib.metadata.distribution('wechatauto-replica')
sdk_db=Path(sdk.locate_file('wechatauto/db.py'))
assert sdk.version=='1.2.6.1'
assert hashlib.sha256(sdk_db.read_bytes()).hexdigest()=='9d4eba69e868dea8000d8acdbaed723149cf8732c52e097f23fb3b07fa5ddc55'
sdk_media=Path(sdk.locate_file('wechatauto/media.py'))
assert hashlib.sha256(sdk_media.read_bytes()).hexdigest()=='ef2c2943e0b9f3a707900ee7eb08b58839a1d1e1d8eddf87a7942869bc4da221'
data=collect_data_files('imageio_ffmpeg')+copy_metadata('imageio-ffmpeg')+collect_data_files('wechat_archive')+[(str(sdk_media),'wechatauto')]+[(str(sdk_db),'wechatauto')]+copy_metadata('wechatauto-replica')
runtime=Path(os.environ['SIXU_CODEX_RUNTIME']) if os.environ.get('SIXU_CODEX_RUNTIME') else project/'build/codex_runtime'
if runtime.is_dir():
    for name in ('codex.exe','codex-code-mode-host.exe'):
        assert (runtime/name).is_file(),name
        data.append((str(runtime/name),'codex_runtime'))
    for name in ('LICENSE','runtime_manifest.json'):
        if (runtime/name).is_file():data.append((str(runtime/name),'codex_runtime'))
a=Analysis([str(project/'packaging/desktop_entry.py')],pathex=[str(project)],
           datas=data,hiddenimports=collect_submodules('wechat_archive')+collect_submodules('cryptography')+collect_submodules('PIL')+['imageio_ffmpeg','zstandard','ctypes.wintypes','unicodedata','winreg','glob','queue','hmac','xml.etree.ElementTree'],
           excludes=['pytest','pip','setuptools','wechatauto'],noarchive=False)
pyz=PYZ(a.pure)
from wechat_archive.ui.app_logo import windows_icon
icon_folder=project/'build/branding';icon_folder.mkdir(parents=True,exist_ok=True)
app_icon=windows_icon(icon_folder/'sixu.ico')
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='思绪',debug=False,icon=app_icon,
        strip=False,upx=False,console=False,version=str(project/'packaging/windows_version.txt'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Sixu')
