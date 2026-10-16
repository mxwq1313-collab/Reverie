"""仅识别 mock 契约或路径特征，不读取真实备份/数据库内容。"""

import json
from dataclasses import dataclass
from pathlib import Path

from ..importer.json_importer import _invalid_number, _unique_keys
from ..importer.validator import DocumentError

MOCK_FORMAT = "wechat-mock"
MOCK_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class SourceDetection:
    kind: str
    supported: bool
    reason: str
    input_file: str | None = None


def read_json(path):
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            return json.load(handle, object_pairs_hook=_unique_keys, parse_constant=_invalid_number)
    except json.JSONDecodeError as exc:
        raise DocumentError(f"微信模拟 JSON 第{exc.lineno}行第{exc.colno}列无法解析：{exc.msg}") from exc


def detect_source(path) -> SourceDetection:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return SourceDetection("missing", False, "输入路径不存在")
    if path.name.lower() == "enmicromsg.db":
        metadata = path.parent / "android_source.json"
        ready = metadata.is_file() and not metadata.is_symlink()
        return SourceDetection("android-db", ready, "Android 候选需校验明文快照、账号元信息和登记 Schema" if ready else "缺少 android_source.json，不读取或猜测数据库", str(path))
    if path.name.lower() == "backupfiles":
        return SourceDetection("pc-backup", False, "真实电脑版 BackupFiles 解析尚未实现，不读取备份内容")
    if path.is_dir() or path.name == "backup.attr":
        from .backup import find_devices
        try:
            devices = find_devices(path)
        except (DocumentError, OSError) as exc:
            return SourceDetection("invalid", False, str(exc))
        if devices:
            return SourceDetection("pc-backup", False, "发现 backup.attr 和 files；可检查 RMFH 结构，正文解密与映射尚未支持", str(path))
    candidate = path / "export.json" if path.is_dir() else path
    if not candidate.is_file() or candidate.suffix.lower() != ".json":
        from .android.detector import detect_android_source
        android = detect_android_source(path, probe_header=False)
        if android.database is not None:
            return SourceDetection("android-db", android.status == "candidate", android.reason, android.database)
        return SourceDetection("unknown", False, "只接受明确的模拟格式或带元信息的 Android 候选快照，未知来源拒绝")
    try:
        payload = read_json(candidate)
    except (DocumentError, OSError, UnicodeError) as exc:
        return SourceDetection("invalid", False, str(exc), str(candidate))
    if isinstance(payload,dict) and payload.get('format')=='wechat-external-export':
        return SourceDetection('external',payload.get('format_version')=='1.0','真实结构化导出候选；须核查来源身份、分片、时间和原始记录',str(candidate))
    if not isinstance(payload, dict) or payload.get("format") != MOCK_FORMAT:
        return SourceDetection("unknown", False, "缺少明确的 format=wechat-mock 标记；不会把普通 JSON 当作微信数据", str(candidate))
    if payload.get("format_version") != MOCK_VERSION:
        return SourceDetection("mock", False, "不支持的微信模拟格式版本，需要 format_version=1.0", str(candidate))
    if not isinstance(payload.get("account"), dict) or not isinstance(payload.get("contacts"), list) or not isinstance(payload.get("messages"), list):
        return SourceDetection("mock", False, "模拟格式需要 account 对象、contacts 数组和 messages 数组", str(candidate))
    return SourceDetection("mock", True, "识别到微信模拟契约 1.0；真实微信兼容性未实现", str(candidate))
