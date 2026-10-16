"""mock 字段映射。该契约不宣称是真实微信备份格式。"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ..importer.records import LoadedDocument
from ..importer.validator import DocumentError, FieldError, FORMAT, FORMAT_VERSION, fields, text
from .detector import MOCK_FORMAT, MOCK_VERSION


def map_identifier(value, field):
    if type(value) is int:
        value = str(value)
    return text(value, field)


def map_timestamp(value, unit="seconds"):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        number = int(value)
    else:
        raise DocumentError("createTime 必须为 Unix 整数时间戳或整数字符串，不接受布尔值或浮点数")
    if unit not in {"seconds", "milliseconds"}:
        raise DocumentError("timeUnit 必须明确为 seconds 或 milliseconds，不自动猜测单位")
    seconds, micros = (number, 0) if unit == "seconds" else (number // 1000, number % 1000 * 1000)
    try:
        stamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds, microseconds=micros)
    except (ValueError, OverflowError) as exc:
        raise DocumentError("createTime 超出支持的日期范围，请检查 timeUnit") from exc
    return stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")


def map_message_type(value):
    if type(value) is int:
        return "text" if value == 1 else f"unsupported-mock-type-{value}"
    if isinstance(value, str):
        return text(value, "type")
    raise DocumentError("type 必须是 mock 数字类型或文字类型，不能是布尔值")


def map_mock_export(payload) -> LoadedDocument:
    try:
        fields(payload, ("format", "format_version", "account", "contacts", "messages"), ("format", "format_version", "account", "contacts", "messages", "timeUnit", "metadata"))
        if payload["format"] != MOCK_FORMAT or payload["format_version"] != MOCK_VERSION:
            raise DocumentError("只接受明确标记的 wechat-mock / 1.0，真实格式未实现")
        unit = payload.get("timeUnit", "seconds")
        if not isinstance(unit, str) or unit not in {"seconds", "milliseconds"}:
            raise DocumentError("timeUnit 必须为 seconds 或 milliseconds")
        if not isinstance(payload["contacts"], list) or not isinstance(payload["messages"], list):
            raise DocumentError("contacts 和 messages 必须是数组")
        if not isinstance(payload.get("metadata", {}), dict):
            raise DocumentError("metadata 必须是对象")
        account = payload["account"]
        fields(account, ("wxid", "nickname"), ("wxid", "nickname", "avatar"))
        owner = text(account["wxid"], "wxid")
        namespace = "wechat-mock:" + quote(owner, safe="")
        users, known = [], set()
        for index, raw in enumerate([account, *payload["contacts"]]):
            fields(raw, ("wxid", "nickname"), ("wxid", "nickname", "avatar"))
            wxid = text(raw["wxid"], "wxid")
            if wxid in known:
                raise DocumentError(f"第{index}条联系人 wxid 重复或与当前账号重复")
            known.add(wxid)
            users.append({"id": wxid, "external_id": namespace + ":" + quote(wxid, safe=""), "nickname": text(raw["nickname"], "nickname"), "avatar": raw.get("avatar")})
        chats, messages = {}, []
        for index, raw in enumerate(payload["messages"], 1):
            try:
                fields(raw, ("msgId", "talker", "isSend", "createTime", "type", "content"), ("msgId", "talker", "isSend", "createTime", "type", "content"))
                ref, talker = map_identifier(raw["msgId"], "msgId"), text(raw["talker"], "talker")
                if talker not in known:
                    raise DocumentError("talker 未在 account 或 contacts 中定义")
                if type(raw["isSend"]) is not int or raw["isSend"] not in (0, 1):
                    raise DocumentError("isSend 必须是整数 0 或 1，不能猜测消息方向")
                chat_ref = "chat:" + quote(talker, safe="")
                if talker not in chats:
                    chats[talker] = {"id": chat_ref, "external_id": "private:" + quote(talker, safe=""), "type": "private", "participant_ids": sorted({owner, talker})}
                sender, receiver = (owner, talker) if raw["isSend"] == 1 else (talker, owner)
                messages.append({"id": ref, "source_id": ref, "sender_id": sender, "receiver_id": receiver, "chat_id": chat_ref, "timestamp": map_timestamp(raw["createTime"], unit), "type": map_message_type(raw["type"]), "content": raw["content"]})
            except (FieldError, DocumentError) as exc:
                raise DocumentError(f"第{index}条微信模拟消息映射失败：{exc}") from exc
        exchange = {"format": FORMAT, "format_version": FORMAT_VERSION, "source": {"id": namespace, "name": "微信模拟导出", "account_id": owner, "metadata": {"adapter": "wechat-mock", "mock_version": MOCK_VERSION, "time_unit": unit, "original_metadata": payload.get("metadata", {})}}, "users": users, "chats": list(chats.values()), "messages": messages, "media": []}
        return LoadedDocument(exchange)
    except FieldError as exc:
        raise DocumentError(f"微信模拟输入字段错误：{exc}") from exc
