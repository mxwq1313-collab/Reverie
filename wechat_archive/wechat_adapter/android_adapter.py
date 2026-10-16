from .base import UnsupportedWeChatSource, WeChatAdapter
from .detector import detect_source
from ..models.contracts import MessageKind, SourceCapabilities


class AndroidAdapter(WeChatAdapter):
    """登记 Schema 的离线明文 SQLite 接入，不处理加密。"""
    name = "android"
    capabilities = SourceCapabilities("android", ("enmicromsg-legacy-text-v1",), ("private",), (MessageKind.TEXT,),
                                      input_requirement="已解密、停止写入的登记SQLite快照与账号元信息")

    def detect(self, path):
        return detect_source(path).kind == "android-db"

    def load(self, path):
        from .android.parser import AndroidWeChatParser
        return AndroidWeChatParser(path).export_exchange()
