from urllib.parse import quote

from ...importer.validator import FieldError, text
from ..mapper import map_timestamp
from .errors import AndroidSourceError


def map_users(rows, account, profile):
    owner = account["wxid"]
    namespace = "wechat-android:" + quote(owner, safe="")
    users = {owner: {"id":owner, "external_id":namespace + ":" + quote(owner, safe=""), "nickname":account["nickname"], "avatar":None}}
    seen = set()
    for index, row in enumerate(rows, 1):
        try:
            username = text(row["id"], "username")
            if username in seen:
                raise AndroidSourceError("duplicate_contact", "rcontact 出现重复 username，不能猜测联系人身份")
            seen.add(username)
            if username.endswith(profile["group_suffix"]) or username == owner:
                continue
            nickname = row.get("remark") or row.get("nickname") or username
            users[username] = {"id":username, "external_id":namespace + ":" + quote(username, safe=""), "nickname":text(nickname, "nickname"), "avatar":None}
        except (FieldError, AndroidSourceError) as exc:
            raise AndroidSourceError("invalid_contact", f"第{index}条联系人无效：{exc}") from exc
    return users, namespace


def map_text_message(row, index, owner, users, profile):
    try:
        if type(row["id"]) is not int or row["id"] <= 0:
            raise AndroidSourceError("invalid_id", "msgId 必须是正整数")
        talker = text(row["talker"], "talker")
        if talker not in users:
            raise AndroidSourceError("missing_contact", "talker 不在已定义联系人中，不自动猜测身份")
        if type(row["is_send"]) is not int or row["is_send"] not in (0, 1):
            raise AndroidSourceError("invalid_direction", "isSend 必须是 0 或 1")
        stamp = row["timestamp"]
        if type(stamp) is not int or not profile["minimum_timestamp"] <= stamp < profile["maximum_timestamp"]:
            raise AndroidSourceError("invalid_time", "createTime 超出登记范围或不是毫秒整数，请检查时间单位")
        content = text(row["content"], "content", strip=False)
        sender, receiver = (owner, talker) if row["is_send"] == 1 else (talker, owner)
        server = row.get("server_id")
        if server is not None and type(server) is not int:
            raise AndroidSourceError("invalid_server_id", "msgSvrId 必须是整数或 null")
        ref = "android-msg:" + str(row["id"])
        source_id = "server:" + str(server) if server is not None and server > 0 else "local:" + str(row["id"])
        chat_id = "private:" + quote(talker, safe="")
        chat = {"id":chat_id, "external_id":chat_id, "type":"private", "participant_ids":sorted({owner,talker})}
        message = {"id":ref, "sender_id":sender, "receiver_id":receiver, "chat_id":chat_id, "timestamp":map_timestamp(stamp, profile["time_unit"]), "type":"text", "content":content, "source_id":source_id}
        return message, chat
    except (FieldError, AndroidSourceError) as exc:
        raise AndroidSourceError(getattr(exc, "code", "invalid_message"), f"第{index}条文本消息（msgId={row.get('id')}）无效：{exc}") from exc
