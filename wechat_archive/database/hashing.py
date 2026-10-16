"""不使用字符串直接拼接，保留时间精度、换行和内容空白。"""

import hashlib
import json
from urllib.parse import quote


def has_external_source_key(source, source_id, external_id) -> bool:
    """Recognize the registered composite identity without trusting a bare ID."""
    if not all(isinstance(value, str) for value in (source, source_id, external_id)):
        return False
    try:
        key = json.loads(source_id)
    except (ValueError, TypeError):
        return False
    if not isinstance(key, list) or len(key) != 5 or not all(isinstance(value, str) and value.strip() for value in key):
        return False
    owner, peer, shard, kind, message_id = key
    if kind not in {"local", "server"} or owner == peer or source != "wechat:" + quote(owner, safe=""):
        return False
    encoded = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return external_id == "external-msg:" + hashlib.sha256(encoded).hexdigest()


def message_hash(sender_id: int, receiver_id: int, timestamp: str, content: str) -> str:
    payload = json.dumps([sender_id, receiver_id, timestamp, content], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def private_chat_key(first_id: int, second_id: int) -> str:
    pair = sorted({first_id, second_id})
    return "private:" + ":".join(map(str, pair))


def ensure_private_chat(conn, first_id: int, second_id: int, title=None) -> tuple[int, bool]:
    key = private_chat_key(first_id, second_id)
    existing = conn.execute("SELECT id FROM chats WHERE chat_key = ?", (key,)).fetchone()
    if existing is not None:
        return existing[0], False
    cursor = conn.execute("INSERT INTO chats(chat_key, kind, title) VALUES (?, 'private', ?)", (key, title))
    chat_id = cursor.lastrowid
    conn.executemany("INSERT INTO chat_members(chat_id, user_id) VALUES (?, ?)", [(chat_id, member) for member in sorted({first_id, second_id})])
    return chat_id, True
