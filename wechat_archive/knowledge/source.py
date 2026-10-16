"""原文切片；Unicode 字符偏移、范围、文件身份及消息版本均绑定引用。"""

import base64
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time

from ..agent.tools import ArchiveTools
from ..errors import ConflictError, ValidationError
from ..models.contracts import MessageRef


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def bounded_int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{name} 超出允许范围。")
    return value


@dataclass(frozen=True, slots=True)
class ChunkRef:
    message: MessageRef
    scope_id: str
    start: int
    end: int
    text_sha256: str
    version: int = 1

    def __post_init__(self):
        if not isinstance(self.message, MessageRef) or type(self.version) is not int or self.version != 1:
            raise ValidationError("不支持的知识引用版本。")
        bounded_int(self.start, "start", 0, 2**63-1)
        bounded_int(self.end, "end", self.start+1, self.start+2048)
        for value in (self.scope_id, self.text_sha256):
            if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValidationError("知识引用摘要无效。")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"message", "scope_id", "start", "end", "text_sha256", "version"}:
            raise ValidationError("知识引用字段不符合契约。")
        return cls(**{**value, "message": MessageRef.from_dict(value["message"])})

    @property
    def key(self):
        return digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    text: str
    reference: ChunkRef
    timestamp_utc: str
    sender_id: int
    receiver_id: int
    source: str | None
    source_id: str | None
    sender_name: str
    receiver_name: str

    def to_dict(self):
        return {**asdict(self), "kind": "original_fragment", "offset_unit": "Unicode code points",
                "chunk_id": self.reference.key}


class KnowledgeSnapshot:
    def __init__(self, source, connection):
        self.source = source
        self.connection = connection
        self.messages = 0
        state = hashlib.sha256(source.scope_id.encode("ascii"))
        for row in self._rows():
            state.update(MessageRef.from_row(source.tools.archive_identity, row).revision.encode("ascii"))
            # Names also belong to the provenance shown to the user.
            state.update(digest([row["sender_name"], row["receiver_name"]]).encode("ascii"))
            self.messages += 1
        self.revision = state.hexdigest()

    def _rows(self, after_id=0):
        where, params = self.source.tools._where()
        deadline = [time.monotonic()+5]
        self.connection.set_progress_handler(lambda: int(time.monotonic() > deadline[0]), 1000)
        cursor = self.connection.execute(
            "SELECT m.*,s.nickname AS sender_name,r.nickname AS receiver_name FROM messages m "
            "JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.receiver_id "
            "WHERE m.id>=? AND "+where+" ORDER BY m.id", (after_id, *params))
        while True:
            deadline[0] = time.monotonic()+5
            rows = cursor.fetchmany(128)
            if not rows:
                break
            for row in rows:
                yield dict(row)

    def chunks(self, after_id=0, after_end=0):
        source = self.source
        for row in self._rows(after_id):
            message = MessageRef.from_row(source.tools.archive_identity, row)
            text = row["content"]
            for start in range(0, len(text), source.chunk_size-source.overlap):
                end = min(len(text), start+source.chunk_size)
                if row["id"] == after_id and end <= after_end:
                    continue
                fragment = text[start:end]
                ref = ChunkRef(message, source.scope_id, start, end,
                               hashlib.sha256(fragment.encode("utf-8")).hexdigest())
                yield KnowledgeChunk(fragment, ref, row["create_time"], row["sender_id"],
                                     row["receiver_id"], row.get("source"), row.get("source_id"),
                                     row["sender_name"], row["receiver_name"])
                if end == len(text):
                    break


class KnowledgeSource:
    """No database creation, migration, writes, model calls or path disclosure."""

    def __init__(self, scope, chunk_size=600, overlap=80):
        self.tools = ArchiveTools(scope)
        self.scope = scope
        self.chunk_size = bounded_int(chunk_size, "片段长度", 32, 2048)
        self.overlap = bounded_int(overlap, "重叠长度", 0, chunk_size-1)
        self.scope_id = digest([self.tools.archive_identity, scope.user_id, scope.peer_id])

    @property
    def processing(self):
        return {"version": 1, "size": self.chunk_size, "overlap": self.overlap,
                "offset_unit": "Unicode code points", "normalization": "none"}

    def _check_identity(self):
        if self.tools._archive_identity() != self.tools.archive_identity:
            raise ConflictError("归档已替换，请重新选择知识范围。")

    @contextmanager
    def snapshot(self):
        self._check_identity()
        with self.tools.database.connection() as connection:
            connection.execute("BEGIN")
            snapshot = KnowledgeSnapshot(self, connection)
            yield snapshot
            self._check_identity()

    def page(self, limit=30, cursor=None):
        bounded_int(limit, "limit", 1, 100)
        after_id = after_end = 0
        token = None
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or len(cursor)>1024:
                    raise ValueError()
                token = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if set(token) != {"scope", "revision", "processing", "id", "end"}:
                    raise ValueError()
                after_id = bounded_int(token["id"], "cursor id", 1, 2**63-1)
                after_end = bounded_int(token["end"], "cursor end", 1, 2**63-1)
            except (ValueError, TypeError, KeyError) as error:
                raise ValidationError("知识分页游标无效。") from error
        with self.snapshot() as snap:
            if token and (token["scope"] != self.scope_id or token["revision"] != snap.revision or token["processing"] != self.processing):
                raise ConflictError("范围或原文已变化，请从第一页重新读取。")
            items = []
            more = False
            size = 0
            for chunk in snap.chunks(after_id, after_end):
                item = chunk.to_dict()
                count = len(json.dumps(item, ensure_ascii=False))
                if len(items) == limit or (items and size+count > 48000):
                    more = True
                    break
                items.append(item)
                size += count
            next_cursor = None
            if more:
                last = items[-1]["reference"]
                next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": self.scope_id,
                    "revision": snap.revision, "processing": self.processing,
                    "id": last["message"]["message_id"], "end": last["end"]},
                    separators=(",", ":")).encode()).decode()
            return {"items": items, "next_cursor": next_cursor, "has_more": more,
                    "messages": snap.messages, "source_revision": snap.revision,
                    "scope_id": self.scope_id, "processing": self.processing,
                    "coverage": "当前范围已归档的私聊文本", "ordering": "message id, character offset"}

    def resolve(self, reference):
        ref = ChunkRef.from_dict(reference)
        if ref.scope_id != self.scope_id:
            raise ConflictError("知识引用不属于当前授权范围。")
        self.tools.resolve_reference(ref.message.to_dict())
        row = self.tools.archive_message(ref.message.message_id, ref.start, ref.end-ref.start)["item"]
        if (row["reference"] != ref.message.to_dict() or len(row["content"]) != ref.end-ref.start
                or hashlib.sha256(row["content"].encode("utf-8")).hexdigest() != ref.text_sha256):
            raise ConflictError("引用片段已失效，请重新检索。")
        return KnowledgeChunk(row["content"], ref, row["create_time"], row["sender_id"], row["receiver_id"],
                              row.get("source"), row.get("source_id"), row["sender_name"], row["receiver_name"])
