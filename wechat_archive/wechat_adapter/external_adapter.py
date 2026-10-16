from .base import WeChatAdapter
from ..wechat_source import ExternalExportParser,normalize_export
from ..models.contracts import MessageKind, SourceCapabilities


class ExternalExportAdapter(WeChatAdapter):
    name='external'
    capabilities = SourceCapabilities("external", ("wechat-external-export-1.0",), ("private",), (MessageKind.TEXT,), stable_source_identity=True,
                                      input_requirement="登记1.2.6.1工具结构化输出及原始记录证据")

    def detect(self,path):
        from .detector import detect_source
        return detect_source(path).kind=='external'

    def load(self,path):
        payload,provenance=ExternalExportParser().load(path)
        return normalize_export(payload,provenance)
