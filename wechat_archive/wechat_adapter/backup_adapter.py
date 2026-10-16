from .base import UnsupportedWeChatSource, WeChatAdapter, WeChatBackupParser
from .detector import detect_source
from ..models.contracts import SourceCapabilities


class BackupAdapter(WeChatAdapter):
    """识别并检查 RMFH 备份；正文解密/映射未验证时明确失败。"""
    name = "backup"
    capabilities = SourceCapabilities("backup", ("rmfh-container",), inspection=True,
                                      input_requirement="仅结构检查；正文认证解密与消息映射尚未验证")

    def detect(self, path):
        return detect_source(path).kind == "pc-backup"

    def load(self, path):
        from .backup import RMFHBackupParser
        if not RMFHBackupParser.detect(path):
            raise UnsupportedWeChatSource("来源不符合 RMFH 备份结构；旧版 BackupFiles 和未知格式正文解析尚未实现")
        return RMFHBackupParser(path).export_exchange()

    def inspect(self, path):
        from .backup import RMFHBackupParser
        return RMFHBackupParser(path).inspect()

    def analyze(self, path):
        from .backup import RMFHFormatAnalyzer
        return RMFHFormatAnalyzer(path).analyze()


__all__ = ["BackupAdapter", "WeChatBackupParser"]
