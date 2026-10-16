"""Python CRUD 接口。SQL 参数化，时间统一为 UTC，消息查询支持双向会话。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..database import Database
from ..database.hashing import ensure_private_chat, message_hash
from ..errors import ConflictError, NotFoundError, ValidationError
from ..models import Message, User

_UNSET = object()
_SQLITE_MAX_INT = 2**63 - 1


def _id(value: int, field: str = "id") -> int:
    if type(value) is not int or not 1 <= value <= _SQLITE_MAX_INT:
        raise ValidationError(f"{field} 必须是有效的正整数")
    return value


def _text(value: str, field: str, *, strip: bool = True) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValidationError(f"{field} 必须是非空文本，且不能包含空字符")
    return value.strip() if strip else value


def _avatar(value: str | None) -> str | None:
    if value is not None and (not isinstance(value, str) or "\x00" in value):
        raise ValidationError("avatar 必须是文本或 None")
    return value


def _time(value: datetime | str | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("时间应使用带时区的 ISO 8601 格式，例如 2026-01-01T12:00:00+08:00") from exc
    else:
        raise ValidationError("时间必须是 datetime 或 ISO 8601 文本")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("时间必须包含时区，例如 +08:00 或 Z")
    try:
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (OverflowError, ValueError) as exc:
        raise ValidationError("时间超出了支持的日期范围") from exc


def _page(limit: int, offset: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValidationError("limit 必须是 1 到 1000 的整数")
    if type(offset) is not int or not 0 <= offset <= _SQLITE_MAX_INT:
        raise ValidationError("offset 必须是有效的非负整数")


def _user(row: sqlite3.Row) -> User:
    return User(**dict(row))


def _message(row: sqlite3.Row) -> Message:
    if row["msg_type"] != "text" or row["receiver_id"] is None:
        raise ValidationError("旧文本接口不展开群聊或非文本记录，请使用已支持的消息入口")
    values = {key: value for key, value in dict(row).items() if key in Message.__dataclass_fields__}
    values["create_time"] = datetime.fromisoformat(values["create_time"].replace("Z", "+00:00"))
    return Message(**values)


def _require_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (_id(user_id, "user_id"),)).fetchone()
    if row is None:
        raise NotFoundError(f"联系人 {user_id} 不存在")
    return row


def _require_message(conn: sqlite3.Connection, message_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (_id(message_id, "message_id"),)).fetchone()
    if row is None:
        raise NotFoundError(f"消息 {message_id} 不存在")
    return row


class ChatService:
    def __init__(self, database: Database | str | Path | None = None):
        self.database = database if isinstance(database, Database) else Database(database)
        self.database.initialize()

    def create_user(self, wxid: str, nickname: str, avatar: str | None = None) -> User:
        values = (_text(wxid, "wxid"), _text(nickname, "nickname"), _avatar(avatar))
        with self.database.connection() as conn:
            try:
                cursor = conn.execute("INSERT INTO users(wxid, nickname, avatar) VALUES (?, ?, ?)", values)
            except sqlite3.IntegrityError as exc:
                raise ConflictError(f"wxid {values[0]!r} 已存在") from exc
            return _user(_require_user(conn, cursor.lastrowid))

    def get_user(self, user_id: int) -> User:
        with self.database.connection() as conn:
            return _user(_require_user(conn, user_id))

    def get_user_by_wxid(self, wxid: str) -> User:
        with self.database.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE wxid = ?", (_text(wxid, "wxid"),)).fetchone()
            if row is None:
                raise NotFoundError(f"wxid {wxid!r} 不存在")
            return _user(row)

    def list_users(self, *, limit: int = 100, offset: int = 0) -> list[User]:
        _page(limit, offset)
        with self.database.connection() as conn:
            return [_user(row) for row in conn.execute("SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?", (limit, offset))]

    def update_user(
        self, user_id: int, *, wxid: str | None = None,
        nickname: str | None = None, avatar: str | None | object = _UNSET,
    ) -> User:
        updates = {}
        if wxid is not None:
            updates["wxid"] = _text(wxid, "wxid")
        if nickname is not None:
            updates["nickname"] = _text(nickname, "nickname")
        if avatar is not _UNSET:
            updates["avatar"] = _avatar(avatar)
        if not updates:
            raise ValidationError("请至少指定一个要修改的联系人字段")
        with self.database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _require_user(conn, user_id)
            fields = ", ".join(f"{field} = ?" for field in updates)
            try:
                conn.execute(f"UPDATE users SET {fields} WHERE id = ?", (*updates.values(), user_id))
            except sqlite3.IntegrityError as exc:
                raise ConflictError("wxid 已被其他联系人使用") from exc
            return _user(_require_user(conn, user_id))

    def delete_user(self, user_id: int) -> None:
        with self.database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _require_user(conn, user_id)
            conn.execute("DELETE FROM chats WHERE id IN (SELECT chat_id FROM chat_members WHERE user_id=?) AND NOT EXISTS (SELECT 1 FROM messages WHERE messages.chat_id=chats.id)", (user_id,))
            try:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            except sqlite3.IntegrityError as exc:
                raise ConflictError("该联系人仍有关联消息；请先明确删除对应消息，再删除联系人") from exc

    def create_message(
        self, sender_id: int, receiver_id: int, content: str, *,
        create_time: datetime | str | None = None, msg_type: str = "text",
    ) -> Message:
        sender_id, receiver_id = _id(sender_id, "sender_id"), _id(receiver_id, "receiver_id")
        content, stamp = _text(content, "content", strip=False), _time(create_time)
        if msg_type != "text":
            raise ValidationError("第一阶段仅支持 msg_type='text'")
        with self.database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _require_user(conn, sender_id)
            _require_user(conn, receiver_id)
            chat_id = ensure_private_chat(conn, sender_id, receiver_id)[0]
            cursor = conn.execute(
                "INSERT INTO messages(sender_id, receiver_id, create_time, content, msg_type, chat_id, message_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sender_id, receiver_id, stamp, content, msg_type, chat_id, message_hash(sender_id, receiver_id, stamp, content)),
            )
            return _message(_require_message(conn, cursor.lastrowid))

    def get_message(self, message_id: int) -> Message:
        with self.database.connection() as conn:
            return _message(_require_message(conn, message_id))

    def list_messages(
        self, *, user_id: int | None = None, peer_id: int | None = None,
        keyword: str | None = None, start_time: datetime | str | None = None,
        end_time: datetime | str | None = None, limit: int = 100, offset: int = 0,
    ) -> list[Message]:
        """时间升序；start_time 包含，end_time 不包含；keyword 按字面匹配。"""
        _page(limit, offset)
        if peer_id is not None and user_id is None:
            raise ValidationError("peer_id 必须与 user_id 一起使用")
        clauses, parameters = ["msg_type='text'", "receiver_id IS NOT NULL"], []
        if user_id is not None:
            _id(user_id, "user_id")
            if peer_id is None:
                clauses.append("(sender_id = ? OR receiver_id = ?)")
                parameters.extend((user_id, user_id))
            else:
                _id(peer_id, "peer_id")
                clauses.append("((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))")
                parameters.extend((user_id, peer_id, peer_id, user_id))
        if keyword is not None:
            clauses.append("instr(content, ?) > 0")
            parameters.append(_text(keyword, "keyword", strip=False))
        start = _time(start_time) if start_time is not None else None
        end = _time(end_time) if end_time is not None else None
        if start is not None and end is not None and start >= end:
            raise ValidationError("start_time 必须早于 end_time")
        for operator, stamp in ((">=", start), ("<", end)):
            if stamp is not None:
                clauses.append(f"create_time {operator} ?")
                parameters.append(stamp)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.database.connection() as conn:
            if user_id is not None:
                _require_user(conn, user_id)
            if peer_id is not None:
                _require_user(conn, peer_id)
            rows = conn.execute(
                "SELECT * FROM messages" + where + " ORDER BY create_time, id LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            )
            return [_message(row) for row in rows]

    def get_conversation(self, user_id: int, peer_id: int, **filters) -> list[Message]:
        return self.list_messages(user_id=user_id, peer_id=peer_id, **filters)

    def search_messages(self, keyword: str, **filters) -> list[Message]:
        return self.list_messages(keyword=keyword, **filters)

    def update_message(
        self, message_id: int, *, sender_id: int | None = None,
        receiver_id: int | None = None, content: str | None = None,
        create_time: datetime | str | None = None, msg_type: str | None = None,
    ) -> Message:
        updates = {}
        for field, value in (("sender_id", sender_id), ("receiver_id", receiver_id)):
            if value is not None:
                updates[field] = _id(value, field)
        if content is not None:
            updates["content"] = _text(content, "content", strip=False)
        if create_time is not None:
            updates["create_time"] = _time(create_time)
        if msg_type is not None:
            if msg_type != "text":
                raise ValidationError("第一阶段仅支持 msg_type='text'")
            updates["msg_type"] = msg_type
        if not updates:
            raise ValidationError("请至少指定一个要修改的消息字段")
        with self.database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            original = _require_message(conn, message_id)
            for field in ("sender_id", "receiver_id"):
                if field in updates:
                    _require_user(conn, updates[field])
            final = {**dict(original), **updates}
            updates["message_hash"] = message_hash(final["sender_id"], final["receiver_id"], final["create_time"], final["content"])
            updates["chat_id"] = ensure_private_chat(conn, final["sender_id"], final["receiver_id"])[0]
            fields = ", ".join(f"{field} = ?" for field in updates)
            conn.execute(f"UPDATE messages SET {fields} WHERE id = ?", (*updates.values(), message_id))
            return _message(_require_message(conn, message_id))

    def delete_message(self, message_id: int) -> None:
        with self.database.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _require_message(conn, message_id)
            conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def stats(self) -> dict[str, int]:
        with self.database.connection() as conn:
            row = conn.execute("SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM messages)").fetchone()
            return {"users": row[0], "messages": row[1]}
