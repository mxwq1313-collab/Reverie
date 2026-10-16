"""Typed source/message/reference contracts; these do not enable storage types."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import re

from ..errors import ValidationError


class MessageKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    LOCATION = "location"
    SYSTEM = "system"


class ParseStatus(str, Enum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"


def _nonempty(value, field_name):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValidationError(f"{field_name}必须是非空文本")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _enum(value, enum_type, label):
    try:
        return enum_type(value)
    except (ValueError, TypeError) as error:
        raise ValidationError(f"未知{label}") from error


@dataclass(frozen=True, slots=True)
class SourceRef:
    namespace: str
    source_id: str | None = None
    account_id: str | None = None
    conversation_id: str | None = None
    shard: str | None = None
    id_kind: str = "opaque"
    snapshot_id: str | None = None

    def __post_init__(self):
        _nonempty(self.namespace, "来源命名空间")
        for name in ("source_id", "account_id", "conversation_id", "shard", "snapshot_id"):
            value = getattr(self, name)
            if value is not None:
                _nonempty(value, name)
        if self.id_kind not in {"opaque", "local", "server"}:
            raise ValidationError("未知来源ID作用域")
        if self.id_kind != "opaque" and any(getattr(self, name) is None for name in ("source_id", "account_id", "conversation_id", "shard")):
            raise ValidationError("登记来源身份缺少账号、会话、分片或消息ID")


@dataclass(frozen=True, slots=True)
class MediaRef:
    media_id: str
    kind: MessageKind
    relative_uri: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    availability: str = "missing"
    variant: str = "original"

    def __post_init__(self):
        _nonempty(self.media_id, "媒体ID")
        object.__setattr__(self, "kind", _enum(self.kind, MessageKind, "媒体类型"))
        if self.kind not in {MessageKind.IMAGE, MessageKind.VIDEO, MessageKind.AUDIO, MessageKind.FILE}:
            raise ValidationError("媒体引用类型不支持")
        if self.relative_uri is not None:
            _nonempty(self.relative_uri, "相对媒体路径")
            path = PurePosixPath(self.relative_uri)
            if not path.parts or path.is_absolute() or ".." in path.parts or ":" in self.relative_uri or "\\" in self.relative_uri or any(ord(char) < 32 for char in self.relative_uri):
                raise ValidationError("媒体路径须为资源根内的相对路径")
        if self.sha256 is not None and not re.fullmatch(r"[a-fA-F0-9]{64}", self.sha256):
            raise ValidationError("媒体摘要不是SHA-256")
        if self.size_bytes is not None and (type(self.size_bytes) is not int or self.size_bytes < 0):
            raise ValidationError("媒体字节数不合法")
        if self.availability not in {"missing", "pending", "ready", "unsupported"} or self.variant not in {"original", "compressed", "thumbnail"}:
            raise ValidationError("媒体状态或变体不合法")
        if self.availability == "ready" and any(getattr(self, name) is None for name in ("relative_uri", "sha256", "size_bytes")):
            raise ValidationError("可用资源必须具有路径、摘要和尺寸证据")


@dataclass(frozen=True, slots=True)
class MessageRecord:
    record_id: str
    chat_id: str
    sender_id: str | None
    receiver_id: str | None
    timestamp_utc: datetime
    kind: MessageKind
    original_text: str | None
    source_ref: SourceRef
    chat_kind: str = "private"
    media_refs: tuple[MediaRef, ...] = ()
    parse_status: ParseStatus = ParseStatus.ACCEPTED

    def __post_init__(self):
        _nonempty(self.record_id, "消息引用ID")
        _nonempty(self.chat_id, "会话ID")
        object.__setattr__(self, "kind", _enum(self.kind, MessageKind, "消息类型"))
        object.__setattr__(self, "parse_status", _enum(self.parse_status, ParseStatus, "解析状态"))
        if not isinstance(self.timestamp_utc, datetime) or self.timestamp_utc.tzinfo is None or self.timestamp_utc.utcoffset() is None:
            raise ValidationError("消息时间必须带时区")
        object.__setattr__(self, "timestamp_utc", self.timestamp_utc.astimezone(timezone.utc))
        if self.chat_kind not in {"private", "group"}:
            raise ValidationError("未知会话类型")
        if self.sender_id is None and self.kind != MessageKind.SYSTEM:
            raise ValidationError("非系统消息必须有稳定发送者")
        if self.sender_id is not None:
            _nonempty(self.sender_id, "发送者")
        if self.chat_kind == "private" and self.receiver_id is None:
            raise ValidationError("私聊必须有接收者")
        if self.chat_kind == "group" and self.receiver_id is not None:
            raise ValidationError("群消息使用会话ID，不使用单个接收者")
        if self.receiver_id is not None:
            _nonempty(self.receiver_id, "接收者")
        if self.kind == MessageKind.TEXT:
            _nonempty(self.original_text, "文本原文")
        elif self.original_text is not None and not isinstance(self.original_text, str):
            raise ValidationError("原文类型不合法")
        if not isinstance(self.source_ref, SourceRef) or not isinstance(self.media_refs, tuple) or not all(isinstance(media, MediaRef) for media in self.media_refs):
            raise ValidationError("来源或媒体引用类型不合法")


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    adapter: str
    profiles: tuple[str, ...] = ()
    chat_kinds: tuple[str, ...] = ()
    message_kinds: tuple[MessageKind, ...] = ()
    inspection: bool = False
    stable_source_identity: bool = False
    streaming: bool = False
    synthetic: bool = False
    input_requirement: str = "登记来源"

    def __post_init__(self):
        _nonempty(self.adapter, "适配器名称")
        _nonempty(self.input_requirement, "来源条件")
        if not isinstance(self.profiles, tuple) or not isinstance(self.chat_kinds, tuple) or not isinstance(self.message_kinds, tuple):
            raise ValidationError("来源能力列表须为不可变元组")
        for profile in self.profiles:
            _nonempty(profile, "来源投影")
        if any(kind not in {"private", "group"} for kind in self.chat_kinds):
            raise ValidationError("来源声明了未知会话类型")
        object.__setattr__(self, "message_kinds", tuple(_enum(kind, MessageKind, "能力消息类型") for kind in self.message_kinds))
        if any(type(getattr(self, flag)) is not bool for flag in ("inspection", "stable_source_identity", "streaming", "synthetic")):
            raise ValidationError("来源能力标记须为布尔值")
        if self.streaming and not self.stable_source_identity:
            raise ValidationError("流式来源需先提供经过登记的事件身份")

    def supports(self, record: MessageRecord) -> bool:
        return record.chat_kind in self.chat_kinds and record.kind in self.message_kinds and record.parse_status == ParseStatus.ACCEPTED

    def to_dict(self):
        result = asdict(self)
        result["message_kinds"] = [MessageKind(kind).value for kind in self.message_kinds]
        result["profiles"] = list(self.profiles)
        result["chat_kinds"] = list(self.chat_kinds)
        return result


@dataclass(frozen=True, slots=True)
class ImportBatch:
    snapshot_id: str
    batch_id: str
    records: tuple[MessageRecord, ...]
    capabilities: SourceCapabilities
    next_cursor: str | None = None
    is_final: bool = True

    def __post_init__(self):
        _nonempty(self.snapshot_id, "快照ID")
        _nonempty(self.batch_id, "批次ID")
        if type(self.is_final) is not bool or not isinstance(self.capabilities, SourceCapabilities):
            raise ValidationError("批次结束标记或能力类型不合法")
        if not isinstance(self.records, tuple) or not all(isinstance(record, MessageRecord) and self.capabilities.supports(record) for record in self.records):
            raise ValidationError("批次记录超出来源声明能力")
        if not self.capabilities.streaming and (not self.is_final or self.next_cursor is not None):
            raise ValidationError("来源未声明可靠流式能力")


@dataclass(frozen=True, slots=True)
class MessageRef:
    archive_identity: str
    message_id: int
    revision: str

    def __post_init__(self):
        if type(self.message_id) is not int or self.message_id <= 0:
            raise ValidationError("消息引用ID不合法")
        if not all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in (self.archive_identity, self.revision)):
            raise ValidationError("消息引用的归档身份或版本摘要不合法")

    @classmethod
    def from_row(cls, archive_identity, row):
        fields = ("id", "sender_id", "receiver_id", "chat_id", "create_time", "content", "msg_type", "source", "source_id", "revision")
        return cls(archive_identity, row["id"], _digest({field: row.get(field) for field in fields}))

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"archive_identity", "message_id", "revision"}:
            raise ValidationError("消息引用字段不符合契约")
        return cls(**value)

    def to_dict(self):
        return asdict(self)
