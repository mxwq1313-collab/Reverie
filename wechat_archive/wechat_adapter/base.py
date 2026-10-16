"""微信接入边界；适配器只产出交换文档，不写数据库。"""

from abc import ABC, abstractmethod
from pathlib import Path

from ..importer.records import LoadedDocument
from ..importer.validator import DocumentError
from ..models.contracts import SourceCapabilities


class UnsupportedWeChatSource(DocumentError):
    pass


class WeChatAdapter(ABC):
    name = "base"
    capabilities = None

    def describe_capabilities(self) -> SourceCapabilities:
        return self.capabilities or SourceCapabilities(self.name)

    def iter_batches(self, path, *, cursor=None, max_messages=100000):
        from ..normalization import legacy_adapter_batch
        yield legacy_adapter_batch(self, path, cursor=cursor, max_messages=max_messages)

    @abstractmethod
    def detect(self, path) -> bool:
        """判断是否属于该适配器的来源形状，不代表解析已经实现。"""

    @abstractmethod
    def load(self, path) -> LoadedDocument:
        """返回 chat-exchange 1.0，写库由 Import Engine 负责。"""

    def export_exchange(self, path) -> LoadedDocument:
        return self.load(path)


class WeChatBackupParser(ABC):
    """未来真实备份解析器接口；当前没有具体实现。"""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    @staticmethod
    @abstractmethod
    def detect(path) -> bool:
        pass

    @abstractmethod
    def extract_users(self) -> list[dict]:
        pass

    @abstractmethod
    def extract_messages(self) -> list[dict]:
        pass

    @abstractmethod
    def export_exchange(self) -> LoadedDocument:
        pass
