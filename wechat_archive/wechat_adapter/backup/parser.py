"""结构检查可运行；正文导入明确未完成，不生成空的 LoadedDocument。"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..base import UnsupportedWeChatSource, WeChatBackupParser
from .reader import checked_path, children, file_stamp, read_envelope


class BackupSourceError(UnsupportedWeChatSource):
    def __init__(self, code, message, report):
        self.code = code
        self.source_metadata = {"backup_inspection":report.to_dict()}
        super().__init__(message)


def find_devices(value):
    """只看有限层级的 backup.attr + files 形状，不读文件内容。"""
    path = checked_path(value)
    if path.is_file():
        if path.name != "backup.attr":
            return []
        path = path.parent
    def device(p):
        return (p / "backup.attr").is_file() and (p / "files").is_dir()
    for ancestor in (path, *list(path.parents)[:3]):
        if device(ancestor):
            checked_path(ancestor / "backup.attr")
            checked_path(ancestor / "files")
            return [ancestor]
    found = []
    level = [path]
    for _ in range(2):
        next_level = []
        for parent in level:
            for p in children(parent):
                if p.is_dir():
                    if device(p):
                        checked_path(p / "backup.attr")
                        checked_path(p / "files")
                        found.append(p)
                    else:
                        next_level.append(p)
        if len(next_level) > 2000:
            raise UnsupportedWeChatSource("备份目录层级过宽，无法可靠判断来源")
        level = next_level
    return found


@dataclass
class BackupInspection:
    source: str
    format: str = "unknown"
    inspection_status: str = "unsupported"
    import_supported: bool = False
    content_decoded: bool = False
    encryption_status: str = "not_verified"
    message_count: int | None = None
    device_directories: int = 0
    batch_directories: int = 0
    session_directories: int = 0
    files: int = 0
    bytes: int = 0
    chat_package_files: int = 0
    index_files: int = 0
    media_files: int = 0
    metadata_files: int = 0
    checked_envelopes: int = 0
    payload_bytes: int = 0
    source_stable: bool = False
    reason: str = "未识别 backup.attr / files / ChatPackage 结构，未知来源拒绝"
    required_conditions: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    report_path: str | None = None

    def to_dict(self):
        return asdict(self)

    def save(self, directory):
        directory = Path(directory).expanduser().resolve()
        source = Path(self.source)
        roots = [source.parent if source.is_file() else source, *[d.parent for d in find_devices(source)]]
        for root in roots:
            if directory == root or root in directory.parents:
                raise UnsupportedWeChatSource("检查报告不能保存在原备份内部")
        directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = directory / f"backup_check_{now}_{uuid4().hex}.json"
        self.report_path = str(target)
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            self.report_path = None
            raise
        return target


class RMFHBackupParser(WeChatBackupParser):
    def __init__(self, path):
        self.path = checked_path(path)

    @staticmethod
    def detect(path):
        return bool(find_devices(path))

    def inspect(self):
        report = BackupInspection(str(self.path))
        stamps = {self.path: file_stamp(self.path)}
        try:
            devices = find_devices(self.path)
            if not devices:
                return report
            report.device_directories = len(devices)
            seen_files = set()
            for device in devices:
                stamps[device / "backup.attr"] = file_stamp(device / "backup.attr")
                stamps[device.parent] = file_stamp(device.parent)
                read_envelope(device / "backup.attr")
                scope = self.path if self.path.is_dir() and (self.path == device / "files" or device / "files" in self.path.parents) else device
                roam = device.parent / "roam_device_info.dat"
                if scope == device and (self.path == device.parent or self.path in device.parent.parents) and roam.is_file() and roam not in seen_files:
                    checked_path(roam)
                    seen_files.add(roam)
                    stamps[roam] = file_stamp(roam)
                    report.files += 1
                    report.metadata_files += 1
                    report.bytes += stamps[roam][0]
                level = [(scope, 0)]
                while level:
                    directory, depth = level.pop()
                    if depth > 7:
                        raise UnsupportedWeChatSource("备份层级超出已识别结构，未知布局拒绝")
                    entries = children(directory)
                    stamps[directory] = file_stamp(directory)
                    if directory.parent.name == "files":
                        report.batch_directories += 1
                    if (directory / "ChatPackage").is_dir():
                        report.session_directories += 1
                    for p in entries:
                        if p.is_dir():
                            level.append((p, depth + 1))
                            continue
                        if not p.is_file() or p in seen_files:
                            continue
                        if p.name == "pkg.lock":
                            raise UnsupportedWeChatSource("备份内存在 pkg.lock，无法确认离线稳定状态，请等待备份结束")
                        seen_files.add(p)
                        stamps[p] = file_stamp(p)
                        report.files += 1
                        report.bytes += stamps[p][0]
                        if report.files > 200000:
                            raise UnsupportedWeChatSource("备份文件超过结构检查上限")
                        relative = p.relative_to(device).parts
                        category = next((name for name in ("ChatPackage", "Index", "Media") if name in relative), None)
                        if category == "ChatPackage":
                            report.chat_package_files += 1
                            try:
                                envelope = read_envelope(p)
                            except UnsupportedWeChatSource as exc:
                                raise UnsupportedWeChatSource(f"消息包 {p.name}：{exc}") from exc
                            report.checked_envelopes += 1
                            report.payload_bytes += envelope["payload_bytes"]
                        elif category == "Index":
                            report.index_files += 1
                        elif category == "Media":
                            report.media_files += 1
                        else:
                            report.metadata_files += 1
            if not report.chat_package_files:
                raise UnsupportedWeChatSource("没有 ChatPackage 消息包，不能确认可用备份")
            if any(file_stamp(p) != stamp for p, stamp in stamps.items()):
                raise UnsupportedWeChatSource("备份目录或文件在检查期间变化，请等待备份结束")
            report.source_stable = True
            report.format = "wechat-rmfh-backup"
            report.inspection_status = "recognized"
            report.reason = (f"已识别 RMFH 备份：{report.session_directories} 个会话目录、"
                             f"{report.chat_package_files} 个消息包。正文尚未解码，无法导入聊天；"
                             "需要适用的解密密钥、经过验证的解密方法和消息字段映射。")
            report.required_conditions = ["本备份适用的解密密钥或可读导出", "经过验证的 RMFH 认证解密方法", "经过验证的消息正文 Schema"]
            report.warnings = ["会话目录数和消息包数不是已解析的联系人/聊天消息数量。",
                               "只检查外壳、目录和文件大小；不认证备份完整性、微信版本或加密算法。"]
        except (UnsupportedWeChatSource, OSError) as exc:
            report.inspection_status = "invalid"
            report.reason = str(exc)
            report.issues.append({"code":"unsupported_backup_structure", "message":str(exc)})
        return report

    def _unavailable(self):
        report = self.inspect()
        code = "backup_content_unavailable" if report.inspection_status == "recognized" else "unsupported_backup_structure"
        raise BackupSourceError(code, report.reason, report)

    def extract_users(self):
        self._unavailable()

    def extract_messages(self):
        self._unavailable()

    def export_exchange(self):
        # 未验证的密文不能转换成 LoadedDocument，也不能以空文档冒充成功。
        self._unavailable()
