"""标准格式的严格字段校验和引用校验，不执行数据库写入。"""

import re
import json
from datetime import datetime, timezone, timedelta

from ..errors import ValidationError
from ..services.chat_service import _time
from .import_report import ImportIssue
from .records import ExchangeChat, ExchangeMessage, ExchangeUser, ImportDocument

FORMAT = "chat-exchange"
FORMAT_VERSION = "1.0"
ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
FIELD_LABELS = {"id": "记录 ID", "external_id": "外部用户标识", "nickname": "昵称", "sender_id": "发送者", "receiver_id": "接收者", "chat_id": "会话", "timestamp": "时间", "type": "消息类型", "content": "内容", "participant_ids": "会话参与者"}


class DocumentError(ValidationError):
    """文件级错误：禁止整份导入。"""


class FieldError(ValidationError):
    def __init__(self, code, message, field=None):
        super().__init__(message)
        self.code, self.field = code, field


def text(value, field, *, strip=True):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FieldError("invalid_field", f"{FIELD_LABELS.get(field, field)}必须是非空文本", field)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise FieldError("invalid_unicode", "文本含有无效 Unicode 字符", field) from exc
    return value.strip() if strip else value


def fields(row, required, allowed):
    if not isinstance(row, dict):
        raise FieldError("invalid_record", "记录必须是 JSON 对象")
    for key in required:
        if key not in row:
            raise FieldError("missing_field", f"缺少{FIELD_LABELS.get(key, key)}（{key}）", key)
    unknown = set(row) - set(allowed)
    if unknown:
        raise FieldError("unknown_field", "未知字段：" + ", ".join(sorted(unknown)), sorted(unknown)[0])


def timestamp(value):
    raw = text(value, "timestamp")
    if not ISO_TIME.fullmatch(raw):
        raise FieldError("invalid_time", "时间必须使用带时区的 ISO 8601，例如 2026-01-01T12:00:00+08:00，最多 6 位小数", "timestamp")
    try:
        return _time(raw)
    except ValidationError as exc:
        raise FieldError("invalid_time", str(exc), "timestamp") from exc


def csv_timezone(value):
    if value == "Z":
        return timezone.utc
    if not isinstance(value, str) or not re.fullmatch(r"[+-]\d{2}:\d{2}", value):
        raise DocumentError("CSV 默认时区应为 Z 或固定偏移，例如 +08:00")
    hours, minutes = map(int, value[1:].split(":"))
    if hours > 23 or minutes > 59:
        raise DocumentError("CSV 默认时区偏移不合法")
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(delta if value[0] == "+" else -delta)


def csv_timestamp(raw, default_zone):
    if not isinstance(raw, str):
        return raw
    value = raw.strip()
    if ISO_TIME.fullmatch(value):
        return value
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=default_zone).isoformat(timespec="microseconds")
        except ValueError:
            continue
    return raw  # 保留到逐条校验，产生消息序号与物理行号。


def validate_document(payload, line_numbers=None):
    lines = line_numbers or {}
    try:
        fields(payload, ("format", "format_version", "source", "users", "chats", "messages"), ("format", "format_version", "source", "users", "chats", "messages", "media"))
        if payload["format"] != FORMAT or payload["format_version"] != FORMAT_VERSION:
            raise DocumentError("不支持的交换格式或版本；需要 chat-exchange / 1.0")
        source = payload["source"]
        fields(source, ("id",), ("id", "name", "account_id", "metadata"))
        normalized_source = dict(source)
        normalized_source["id"] = text(source["id"], "source.id")
        for key in ("name", "account_id"):
            if key in source:
                normalized_source[key] = text(source[key], "source." + key)
        if "metadata" in source and not isinstance(source["metadata"], dict):
            raise DocumentError("source.metadata 必须是对象")
        try:
            json.dumps(source.get("metadata", {}), ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise DocumentError("source.metadata 含非法数值或 Unicode") from exc
        for key in ("users", "chats", "messages", "media"):
            if not isinstance(payload.get(key, []), list):
                raise DocumentError(f"{key} 必须是数组")
        if payload.get("media"):
            raise DocumentError("media 已预留；v0.3.0 仅导入文字，media 必须为空数组")
    except FieldError as exc:
        raise DocumentError(str(exc)) from exc
    result = ImportDocument(normalized_source, users_total=len(payload["users"]), chats_total=len(payload["chats"]), messages_total=len(payload["messages"]))
    user_map, chat_map, user_external, message_ids = {}, {}, set(), set()

    def issue(entity, index, row, exc):
        name = {"user": "用户", "chat": "会话", "message": "消息"}[entity]
        ref = row.get("id") if isinstance(row, dict) and isinstance(row.get("id"), str) else None
        result.issues.append(ImportIssue(entity, index, exc.code, f"第{index}条{name}失败：{exc}", exc.field, ref, lines.get(index) if entity == "message" else None))

    for index, row in enumerate(payload["users"], 1):
        try:
            fields(row, ("id", "external_id", "nickname"), ("id", "external_id", "nickname", "avatar"))
            ref, external, name = text(row["id"], "id"), text(row["external_id"], "external_id"), text(row["nickname"], "nickname")
            if ref in user_map or external in user_external:
                raise FieldError("duplicate_user_id", "用户 id 或 external_id 在文件内重复", "id")
            avatar = row.get("avatar")
            if avatar is not None:
                avatar = text(avatar, "avatar", strip=False)
            user = ExchangeUser(ref, external, name, avatar)
            user_map[ref] = user
            user_external.add(external)
            result.users.append(user)
        except FieldError as exc:
            issue("user", index, row, exc)

    for index, row in enumerate(payload["chats"], 1):
        try:
            fields(row, ("id", "type", "participant_ids"), ("id", "external_id", "type", "participant_ids", "title"))
            ref = text(row["id"], "id")
            if ref in chat_map:
                raise FieldError("duplicate_chat_id", "会话 id 在文件内重复", "id")
            if row["type"] != "private":
                raise FieldError("unsupported_chat_type", "当前版本仅支持 private；群聊格式已预留", "type")
            participants = row["participant_ids"]
            if not isinstance(participants, list) or not 1 <= len(participants) <= 2:
                raise FieldError("invalid_participants", "私聊需要 1 或 2 位参与者", "participant_ids")
            participants = tuple(text(value, "participant_ids") for value in participants)
            if len(set(participants)) != len(participants) or any(value not in user_map for value in participants):
                raise FieldError("missing_user", "会话参与者重复或未在合法 users 中定义", "participant_ids")
            title = text(row["title"], "title") if row.get("title") is not None else None
            chat = ExchangeChat(ref, text(row.get("external_id", ref), "external_id"), participants, title=title, index=index)
            chat_map[ref] = chat
            result.chats.append(chat)
        except FieldError as exc:
            issue("chat", index, row, exc)

    for index, row in enumerate(payload["messages"], 1):
        try:
            fields(row, ("id", "sender_id", "receiver_id", "chat_id", "timestamp", "type", "content"), ("id", "sender_id", "receiver_id", "chat_id", "timestamp", "type", "content", "source_id", "source_hash", "media_ids"))
            ref = text(row["id"], "id")
            if ref in message_ids:
                raise FieldError("duplicate_message_id", "消息 id 在文件内重复", "id")
            message_ids.add(ref)
            sender, receiver, chat_id = (text(row[key], key) for key in ("sender_id", "receiver_id", "chat_id"))
            if sender not in user_map:
                raise FieldError("missing_sender", "发送者未在合法 users 中定义", "sender_id")
            if receiver not in user_map:
                raise FieldError("missing_receiver", "接收者未在合法 users 中定义", "receiver_id")
            if chat_id not in chat_map:
                raise FieldError("missing_chat", "会话未在合法 chats 中定义", "chat_id")
            if set((sender, receiver)) != set(chat_map[chat_id].participant_ids):
                raise FieldError("chat_membership", "发送者和接收者与私聊参与者不一致", "chat_id")
            if row["type"] != "text":
                raise FieldError("unsupported_message_type", "当前版本仅支持 text；图片、视频、语音等类型已预留", "type")
            media_ids = row.get("media_ids", [])
            if not isinstance(media_ids, list):
                raise FieldError("invalid_media_refs", "media_ids 必须是数组", "media_ids")
            if media_ids:
                raise FieldError("unsupported_media_refs", "媒体引用已预留，当前 media_ids 必须为空数组", "media_ids")
            stamp, content = timestamp(row["timestamp"]), text(row["content"], "content", strip=False)
            source_id = text(row["source_id"], "source_id") if row.get("source_id") is not None else None
            source_hash = row.get("source_hash")
            if source_hash is not None and (not isinstance(source_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", source_hash)):
                raise FieldError("invalid_source_hash", "source_hash 必须是 64 位十六进制 SHA-256", "source_hash")
            result.messages.append(ExchangeMessage(ref, sender, receiver, chat_id, stamp, content, source_id=source_id, source_hash=source_hash.lower() if source_hash else None, index=index, line=lines.get(index)))
        except FieldError as exc:
            issue("message", index, row, exc)
    return result
