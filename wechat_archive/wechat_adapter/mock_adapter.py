from .base import UnsupportedWeChatSource, WeChatAdapter
from .detector import detect_source, read_json
from .mapper import map_mock_export
from ..models.contracts import MessageKind, SourceCapabilities


class MockWeChatAdapter(WeChatAdapter):
    name = "mock"
    capabilities = SourceCapabilities("mock", ("wechat-mock-1.0",), ("private",), (MessageKind.TEXT,), synthetic=True,
                                      input_requirement="自建模拟导出")

    def detect(self, path):
        result = detect_source(path)
        return result.supported and result.kind == "mock"

    def load(self, path):
        result = detect_source(path)
        if not result.supported or result.kind != "mock":
            raise UnsupportedWeChatSource(result.reason)
        return map_mock_export(read_json(result.input_file))
