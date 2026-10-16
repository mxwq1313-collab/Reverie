"""Pure legacy-document normalization, with no database or decryption access."""
from datetime import datetime
import hashlib
import json

from ..errors import ValidationError
from ..models.contracts import ImportBatch, MessageKind, MessageRecord, SourceRef


def normalize_document(document, capabilities, snapshot_id):
    records = []
    chats = {chat.id: chat for chat in document.chats}
    for message in document.messages:
        source = SourceRef(document.source["id"], source_id=message.source_id, snapshot_id=snapshot_id)
        if document.identity_strategy == "source-id-v1":
            try:
                owner, peer, shard, kind, message_id = json.loads(message.source_id)
                source = SourceRef(document.source["id"], message_id, owner, peer, shard, kind, snapshot_id)
            except (TypeError, ValueError) as error:
                raise ValidationError("已登记来源复合身份无法转换") from error
        records.append(MessageRecord(message.id, message.chat_id, message.sender_id, message.receiver_id,
                                     datetime.fromisoformat(message.timestamp.replace("Z", "+00:00")),
                                     MessageKind(message.type), message.content, source, chats[message.chat_id].type))
    return ImportBatch(snapshot_id, snapshot_id + ":0", tuple(records), capabilities)


def legacy_adapter_batch(adapter, path, *, cursor=None, max_messages=100000):
    """One explicit legacy batch, not a claim of bounded streaming or resume."""
    from ..importer.validator import validate_document
    if cursor is not None:
        raise ValidationError("此来源尚未提供经过验证的恢复游标")
    if type(max_messages) is not int or max_messages < 1:
        raise ValidationError("批次预算须为正整数")
    loaded = adapter.load(path)
    document = validate_document(loaded.payload, loaded.line_numbers)
    if document.issues:
        raise ValidationError("来源含校验失败记录，请使用原导入流程查看逐条报告")
    if len(document.messages) > max_messages:
        raise ValidationError("来源超过单批预算，未声明可靠流式能力")
    document.identity_strategy = loaded.identity_strategy
    encoded = json.dumps(loaded.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    snapshot = hashlib.sha256(encoded).hexdigest()
    return normalize_document(document, adapter.describe_capabilities(), snapshot)
