"""解析已声明的结构化导出，不打开微信数据库或获取密钥。"""

import hashlib
import json
import stat
from pathlib import Path

from ..importer.json_importer import _unique_keys,_invalid_number
from ..importer.validator import DocumentError


def checked_path(value):
    raw=str(value);path=Path(raw).expanduser()
    if not raw or '://' in raw or raw.startswith(('\\\\','//')) or '..' in path.parts or any(ord(c)<32 for c in raw):
        raise DocumentError('导出解析只接受明确的本机路径')
    for part in (path,*path.parents):
        if part.exists() or part.is_symlink():
            info=part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise DocumentError('导出来源不能是链接或目录联接')
    if not path.exists():raise DocumentError('导出来源不存在')
    return path.resolve()


def file_stamp(path):
    info=path.stat();return info.st_size,info.st_mtime_ns,info.st_ino

FORMAT="wechat-external-export"
VERSION="1.0"
PROVIDER="wechatauto-replica"
PROVIDER_VERSION="1.2.6.1"
API="WeChatDB.get_messages+get_message_row"


def exact_fields(row,required,allowed=None):
    if not isinstance(row,dict) or not set(required)<=set(row) or set(row)-set(allowed or required):
        raise DocumentError('真实导出结构字段缺失或含未知字段，不猜测格式')


def identity(value):
    if not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>256:
        raise DocumentError('缺少稳定来源身份，不能用昵称代替 wxid')
    return value


class ExternalExportParser:
    def load(self,path):
        path=checked_path(path)
        if not path.is_file() or path.suffix.lower()!='.json':
            raise DocumentError('ExternalExportSource 只读取明确的 JSON 导出文件')
        before=file_stamp(path)
        if before[0]>64*1024*1024:raise DocumentError('结构化导出超过 64 MiB 上限')
        data=path.read_bytes()
        if file_stamp(path)!=before:raise DocumentError('导出文件在读取期间变化')
        try:payload=json.loads(data.decode('utf-8-sig'),object_pairs_hook=_unique_keys,parse_constant=_invalid_number)
        except (ValueError,UnicodeError) as exc:raise DocumentError('真实导出 JSON 编码或语法错误') from exc
        self.validate_payload(payload)
        return payload,{'export_file':str(path),'export_sha256':hashlib.sha256(data).hexdigest(),'export_bytes':len(data)}

    @staticmethod
    def validate_payload(payload, *, allowed_apis=(API,)):
        exact_fields(payload,('format','format_version','source_platform','provider','account','conversation','timestamp_unit','capture','records'))
        if (payload['format'],payload['format_version'],payload['source_platform'])!=(FORMAT,VERSION,'wechat'):
            raise DocumentError('未知的真实导出格式或版本，需要 wechat-external-export 1.0')
        provider=payload['provider']
        exact_fields(provider,('name','version','api','distribution_sha256'))
        if (provider['name'],provider['version'])!=(PROVIDER,PROVIDER_VERSION) or provider['api'] not in allowed_apis:
            raise DocumentError('未登记的提取工具版本或接口，明确拒绝')
        if not isinstance(provider['distribution_sha256'],str) or len(provider['distribution_sha256'])!=64 or any(c not in '0123456789abcdef' for c in provider['distribution_sha256']):
            raise DocumentError('来源发行包摘要无效')
        account,chat=payload['account'],payload['conversation']
        exact_fields(account,('wxid','nickname','verification'))
        exact_fields(chat,('wxid','nickname','kind'))
        owner,peer=identity(account['wxid']),identity(chat['wxid'])
        if account['verification']!='contact_row':raise DocumentError('账号身份缺少联系人记录证据')
        if chat['kind']!='private' or peer.endswith('@chatroom') or owner==peer:
            raise DocumentError('真实 MVP 仅支持两个不同身份的私聊，群聊明确拒绝')
        for item in (account,chat):identity(item['nickname'])
        if payload['timestamp_unit']!='unix_seconds':raise DocumentError('来源时间单位未登记，不按数字大小猜测')
        exact_fields(payload['capture'],('origin','client_version','captured_at','validated_database_keys','key_cache_written'))
        if not isinstance(payload['records'],list) or len(payload['records'])>100000:
            raise DocumentError('导出 records 必须为最多 100000 条的数组')
        return payload
