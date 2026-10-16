"""从既有自建生成器恢复被 Git 排除的 Android 演示库，不覆盖任何文件。"""
import importlib.util
import json
from pathlib import Path
import sys


def main():
    root=Path(__file__).resolve().parents[1]
    target=root/'android_mock/MicroMsg/mock-account-001'
    database=target/'EnMicroMsg.db';metadata=target/'android_source.json'
    if database.exists() and metadata.exists():
        print('自建 Android 夹具已存在，保留原文件。');return 0
    if target.exists():
        print('夹具目录存在但不完整，未覆盖；请检查该目录。',file=sys.stderr);return 1
    script=root/'tests/android_fixture.py'
    spec=importlib.util.spec_from_file_location('synthetic_android_fixture',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.create_android_fixture(root/'android_mock')
    details=json.loads(result.with_name('android_source.json').read_text(encoding='utf-8'))
    assert details['simulation'] is True
    print('已从版本控制的自建生成器恢复 Android 演示夹具。');return 0


if __name__=='__main__':raise SystemExit(main())
