"""Importer 的统一中间模型，交换文件 ID 与 SQLite ID 分离。"""

from dataclasses import dataclass, field
from ..models.contracts import SourceCapabilities


@dataclass(frozen=True, slots=True)
class ExchangeUser:
    id: str
    external_id: str
    nickname: str
    avatar: str | None = None


@dataclass(frozen=True, slots=True)
class ExchangeChat:
    id: str
    external_id: str
    participant_ids: tuple[str, ...]
    type: str = "private"
    title: str | None = None
    index: int = 0


@dataclass(frozen=True, slots=True)
class ExchangeMessage:
    id: str
    sender_id: str
    receiver_id: str
    chat_id: str
    timestamp: str
    content: str
    type: str = "text"
    source_id: str | None = None
    source_hash: str | None = None
    media_ids: tuple[str, ...] = ()
    index: int = 0
    line: int | None = None


@dataclass(slots=True)
class ImportDocument:
    source: dict
    users: list[ExchangeUser] = field(default_factory=list)
    chats: list[ExchangeChat] = field(default_factory=list)
    messages: list[ExchangeMessage] = field(default_factory=list)
    users_total: int = 0
    chats_total: int = 0
    messages_total: int = 0
    issues: list = field(default_factory=list)
    identity_strategy: str = "legacy-content"


@dataclass(slots=True)
class LoadedDocument:
    payload: dict
    line_numbers: dict[int, int] = field(default_factory=dict)
    # Host-side capability, never enabled by untrusted exchange JSON metadata.
    identity_strategy: str = "legacy-content"
    capabilities: SourceCapabilities | None = None
