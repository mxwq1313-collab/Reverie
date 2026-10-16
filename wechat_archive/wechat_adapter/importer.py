"""来源适配与路径前置检查；写库、校验、哈希和报告沿用 BaseImporter。"""

from ..importer.base_importer import BaseImporter
from .android_adapter import AndroidAdapter
from .backup_adapter import BackupAdapter
from .base import UnsupportedWeChatSource
from .detector import detect_source
from .mock_adapter import MockWeChatAdapter
from .external_adapter import ExternalExportAdapter


ADAPTERS = {"mock": MockWeChatAdapter, "backup": BackupAdapter, "android": AndroidAdapter,'external':ExternalExportAdapter}


def select_adapter(path, choice="auto"):
    if choice == "auto":
        detection = detect_source(path)
        if detection.kind == "pc-backup":
            choice = "backup"  # 生成具体结构/缺失条件报告，仍不绕过正文拒绝边界。
        elif not detection.supported:
            raise UnsupportedWeChatSource(detection.reason)
        else:
            choice = "android" if detection.kind == "android-db" else detection.kind
    if choice not in ADAPTERS:
        raise UnsupportedWeChatSource("未知的微信适配器；请选择 auto、external、mock、backup 或 android")
    return ADAPTERS[choice]()


class WeChatImporter(BaseImporter):
    format_name = "wechat"

    def __init__(self, *args, adapter="auto", **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = adapter

    def load(self, path):
        selected = select_adapter(path, self.adapter)
        if selected.name=='external':
            from pathlib import Path
            if self.database.path==Path(path).resolve():raise UnsupportedWeChatSource('目标归档库不能是来源导出文件')
        if selected.name == "android":
            from pathlib import Path
            from .android.detector import detect_android_source
            detected = detect_android_source(path, probe_header=False)
            protected = [value for value in (detected.database, detected.metadata_file) if value]
            if any(self.database.path == Path(value).resolve() for value in protected):
                raise UnsupportedWeChatSource("目标归档库不能是 Android 来源数据库或元信息文件")
        if selected.name == "backup":
            from pathlib import Path
            source = Path(path).resolve()
            source = source.parent if source.is_file() else source
            if self.database.path == source or source in self.database.path.parents:
                raise UnsupportedWeChatSource("目标归档库不能放在原微信备份内部")
            if self.report_dir.resolve() == source or source in self.report_dir.resolve().parents:
                raise UnsupportedWeChatSource("导入报告不能保存在原微信备份内部")
        loaded=selected.load(path)
        loaded.capabilities = selected.describe_capabilities()
        if selected.name=='external' and self.strict and loaded.payload['source']['metadata']['external_parse']['quarantined_count']:
            from ..importer.validator import DocumentError
            error=DocumentError('严格模式发现被隔离的来源记录，整份导出未写入')
            error.source_metadata=loaded.payload['source'];error.code='strict_external_rejected'
            raise error
        return loaded

    def import_file(self, path):
        from pathlib import Path
        raw = str(path)
        if "://" in raw or raw.startswith(("\\\\", "//")) or any(ord(char) < 32 for char in raw) or ".." in Path(path).parts:
            raise UnsupportedWeChatSource("不接受 URI、控制字符或路径穿越，请使用明确的本机来源路径")
        # BaseImporter 会先创建日志目录，来源保护必须先于该步骤。
        source = Path(path).expanduser()
        protected = source.parent if source.is_file() else source
        if protected.is_dir() and source.exists():
            from .backup import find_devices
            devices = find_devices(source)
            if devices:
                for root in [protected.resolve(), *[d.parent for d in devices]]:
                    if self.report_dir.resolve() == root or root in self.report_dir.resolve().parents:
                        raise UnsupportedWeChatSource("导入报告不能保存在原微信备份内部")
                    if self.database.path == root or root in self.database.path.parents:
                        raise UnsupportedWeChatSource("目标归档库不能放在原微信备份内部")
        report=super().import_file(path)
        details=report.source_metadata.get('metadata',{}).get('external_parse',{})
        if details.get('quarantined_count'):
            from ..importer.import_report import ImportIssue
            from ..importer.base_importer import ReportWriteError
            report.warnings.append(ImportIssue('file',None,'external_records_retained',f"{details['quarantined_count']} 条未支持/无效来源记录已保存 raw_type、raw_payload 和解析状态，见 source_metadata.metadata.external_parse"))
            try:report.save(self.report_dir)
            except OSError as exc:raise ReportWriteError(report,exc) from exc
        return report
