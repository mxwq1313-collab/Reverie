"""窗口与导入引擎之间的薄层，不提供新的数据库写入实现。"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..database.db import APPLICATION_ID, MAX_READABLE_SCHEMA_VERSION, default_data_dir
from ..errors import ConflictError, NotFoundError, ValidationError
from ..migration.manager import validate_schema
from ..importer import CSVImporter, JSONImporter
from ..importer.validator import validate_document
from ..wechat_adapter import WeChatImporter

FORMAT_LABELS = {
    "auto": "自动识别",
    "rich": "思绪2.0交换（群聊、表情与附件）",
    "rich_snapshot": "思绪群聊媒体快照（分批导入）",
    "json": "标准 JSON",
    "csv": "CSV 聊天文件",
    "mock": "微信模拟 JSON",
    "android": "Android 明文快照",
    "backup": "微信 RMFH 备份（结构检查）",
    'external':'Windows 微信结构化导出',
    'snapshot':'封存私聊历史快照（逐批提交）',
}


def inspect_archive(path):
    from ..exporter.readable import _local_path
    path = _local_path(path)
    if not path.is_file():
        raise NotFoundError('请选择已存在的项目归档库')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as connection:
        connection.row_factory=sqlite3.Row
        version=connection.execute('PRAGMA user_version').fetchone()[0]
        if connection.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or not 1<=version<=MAX_READABLE_SCHEMA_VERSION:
            raise ConflictError('这不是受支持的项目归档库，原文件未修改')
        validate_schema(connection,version)
    return path


def project_root():
    root = Path(__file__).resolve().parents[2]
    return root if (root / "pyproject.toml").is_file() else Path.cwd()


def source_path(value):
    raw = str(value).strip().strip('"')
    if not raw or "://" in raw or raw.startswith(("\\\\", "//")) or any(ord(char) < 32 for char in raw):
        raise ValidationError("请选择本机数据文件或文件夹")
    path = Path(raw).expanduser()
    if ".." in path.parts:
        raise ValidationError("请使用完整来源路径，不能包含 ..")
    if not path.is_absolute():
        path = project_root() / path
    if not path.exists():
        raise ValidationError("来源路径不存在，请通过“选择文件”或“选择文件夹”重新选择")
    if path.is_symlink():
        raise ValidationError("请选择实际来源路径，不接受符号链接")
    return path


def target_path(value, source):
    raw = str(value).strip().strip('"')
    if not raw or "://" in raw or raw.startswith(("\\\\", "//")) or any(ord(char) < 32 for char in raw):
        raise ValidationError("请选择目标归档库")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    path = path.resolve()
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"} or path.is_dir():
        raise ValidationError("目标应为 SQLite 归档文件，例如 data/chat.db")
    if source.is_file() and path == source.resolve():
        raise ValidationError("目标归档库不能是来源文件，请选择独立的归档库")
    if source.is_dir() and source.resolve() in path.parents:
        raise ValidationError("目标归档库不能放在来源文件夹内部，请选择独立位置")
    return path


def resolve_format(source, chosen):
    if chosen not in FORMAT_LABELS:
        raise ValidationError("请选择支持的数据类型")
    if chosen != "auto":
        return chosen
    if source.is_dir() or source.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        if source.is_dir() and (source/'rich_snapshot.json').is_file():return 'rich_snapshot'
        if source.is_dir() and (source/'snapshot.json').is_file():return 'snapshot'
        return "wechat"
    if source.suffix.lower() == ".csv":
        return "csv"
    if source.suffix.lower() == ".json":
        try:
            with source.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            marker = payload.get("format") if isinstance(payload, dict) else None
            if marker == "wechat-mock":
                return "mock"
            if marker=='sixu-chat-exchange':return 'rich'
            if marker=='wechat-external-export':return 'external'
            if marker == "android-wechat-source":
                raise ValidationError("这是 Android 元信息文件，请选择同目录数据库或账号文件夹")
        except (json.JSONDecodeError, UnicodeError):
            pass  # 交给原 JSONImporter 生成正式失败报告。
        return "json"
    if source.name == "backup.attr":
        return "backup"
    raise ValidationError("无法自动识别，请选择 JSON、CSV、微信模拟文件、Android 快照或微信备份目录")


class ImportController:
    def __init__(self, *, report_dir=None):
        self.report_dir = report_dir

    def prepare(self, source, target, chosen="auto", *, strict=False, namespace="default", timezone="+08:00"):
        path = source_path(source)
        database = target_path(target, path)
        kind = resolve_format(path, chosen)
        options = dict(report_dir=self.report_dir, strict=strict)
        if kind == "rich_snapshot":
            from ..importer.rich_snapshot import RichSnapshotImporter
            importer=RichSnapshotImporter(database,**options)
        elif kind == "rich":
            from ..importer.rich_importer import RichImporter
            importer=RichImporter(database,**options)
        elif kind == "csv":
            importer = CSVImporter(database, namespace=namespace, timezone=timezone, **options)
        elif kind == 'snapshot':
            from ..importer.snapshot_importer import SnapshotImporter
            importer = SnapshotImporter(database, **options)
        elif kind == "json":
            importer = JSONImporter(database, **options)
        else:
            adapter = kind if kind in {"android", "mock", "backup",'external'} else "auto"
            importer = WeChatImporter(database, adapter=adapter, **options)
        return path, database, importer

    def preview(self, source, target, chosen="auto", **options):
        path, database, importer = self.prepare(source, target, chosen, **options)
        from ..importer.snapshot_importer import SnapshotImporter
        from ..importer.rich_importer import RichImporter
        from ..importer.rich_snapshot import RichSnapshotImporter
        if isinstance(importer,(SnapshotImporter,RichImporter,RichSnapshotImporter)):return importer.preview(path)
        if isinstance(importer, WeChatImporter):
            from ..wechat_adapter import detect_source, BackupAdapter
            if chosen == "backup" or detect_source(path).kind == "pc-backup":
                report = BackupAdapter().inspect(path)
                from ..importer.base_importer import default_report_dir
                report.save(self.report_dir if self.report_dir is not None else default_report_dir())
                return {"kind":"backup", "database":str(database), "backup_inspection":report.to_dict()}
        loaded = importer.load(path)
        validated = validate_document(loaded.payload, loaded.line_numbers)
        parsing = validated.source.get("metadata", {}).get("parse_report", {})
        external = validated.source.get("metadata", {}).get("external_parse", {})
        retained = external.get("quarantined_count", 0)
        issues = [issue.message for issue in validated.issues]
        return {"database":str(database), "users":validated.users_total, "chats":validated.chats_total, "messages":validated.messages_total, "issues":issues, "skipped":parsing.get("skipped_unsupported_count", 0), "retained":retained}

    def import_data(self, source, target, chosen="auto", **options):
        path, database, importer = self.prepare(source, target, chosen, **options)
        return importer.import_file(path), database

    def analyze_backup(self, source):
        from ..wechat_adapter.backup import RMFHFormatAnalyzer
        from ..importer.base_importer import default_report_dir
        result = RMFHFormatAnalyzer(source_path(source)).analyze()
        result.save(self.report_dir if self.report_dir is not None else default_report_dir())
        return result.overview()

    def study_payload(self,source):
        from ..wechat_adapter.backup import RMFHPayloadStudy
        from ..importer.base_importer import default_report_dir
        result=RMFHPayloadStudy(source_path(source)).analyze()
        result.save(self.report_dir if self.report_dir is not None else default_report_dir())
        return result.overview()


def default_target():
    return default_data_dir() / "chat.db"
