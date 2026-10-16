"""网页的分页只读查询；继续使用第一阶段数据库，不变更表结构。"""

from .chat_service import ChatService, _id, _page, _require_user, _text, _time
from ..errors import ValidationError


class BrowseService:
    def __init__(self, service: ChatService):
        self.service = service

    def users(self, *, limit=1000, offset=0):
        _page(limit, offset)
        with self.service.database.connection() as conn:
            conn.execute("BEGIN")
            total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            items = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?", (limit, offset))]
        return self._result(items, total, offset)

    @staticmethod
    def _result(items, total, offset):
        return {"items": items, "total": total, "offset": offset, "has_more": offset + len(items) < total}

    def contacts(self, user_id, *, keyword=None, limit=50, offset=0):
        _id(user_id, "user_id")
        _page(limit, offset)
        query = _text(keyword, "keyword", strip=False) if keyword is not None else None
        # 只对当前查看身份的消息汇总，避免显示其余两人之间的内容。
        prefix = """
            WITH relevant AS (
                SELECT CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END AS peer_id,
                       id, content, create_time, sender_id
                FROM messages WHERE (sender_id = ? OR receiver_id = ?) AND msg_type='text' AND receiver_id IS NOT NULL
            ), ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY peer_id ORDER BY create_time DESC, id DESC) AS rank
                FROM relevant
            ), counts AS (
                SELECT peer_id, COUNT(*) AS message_count, SUM(sender_id=?) AS own_count FROM relevant GROUP BY peer_id
            )
        """
        joins = " FROM users u LEFT JOIN ranked r ON r.peer_id = u.id AND r.rank = 1 LEFT JOIN counts c ON c.peer_id = u.id"
        where = " WHERE (u.id != ? OR c.message_count > 0)"
        params = [user_id, user_id, user_id, user_id, user_id]
        if query is not None:
            where += " AND (instr(u.nickname, ?) > 0 OR instr(u.wxid, ?) > 0)"
            params.extend((query, query))
        with self.service.database.connection() as conn:
            conn.execute("BEGIN")
            _require_user(conn, user_id)
            total = conn.execute(prefix + " SELECT COUNT(*)" + joins + where, params).fetchone()[0]
            rows = conn.execute(
                prefix + " SELECT u.id, u.wxid, u.nickname, u.avatar, r.content AS last_message, r.create_time AS last_time, COALESCE(c.message_count, 0) AS message_count,COALESCE(c.own_count,0) AS own_count"
                + joins + where + " ORDER BY (r.create_time IS NULL), r.create_time DESC, r.id DESC, u.id LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            items = [dict(row) for row in rows]
        for item in items:item['own_ratio']=item['own_count']/item['message_count'] if item['message_count'] else 0
        return self._result(items, total, offset)

    def messages(self, user_id, *, peer_id=None, keyword=None, start_time=None, end_time=None, limit=50, offset=0):
        _id(user_id, "user_id")
        _page(limit, offset)
        params = []
        if peer_id is None:
            clauses = ["(m.sender_id = ? OR m.receiver_id = ?)"]
            params.extend((user_id, user_id))
        else:
            _id(peer_id, "peer_id")
            clauses = ["((m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?))"]
            params.extend((user_id, peer_id, peer_id, user_id))
        if keyword is not None:
            clauses.append("instr(m.content, ?) > 0")
            params.append(_text(keyword, "keyword", strip=False))
        start = _time(start_time) if start_time is not None else None
        end = _time(end_time) if end_time is not None else None
        if start is not None and end is not None and start >= end:
            raise ValidationError("开始时间必须早于结束时间")
        for op, stamp in ((">=", start), ("<", end)):
            if stamp is not None:
                clauses.append(f"m.create_time {op} ?")
                params.append(stamp)
        clauses.extend(("m.msg_type='text'", "m.receiver_id IS NOT NULL"))
        where = " WHERE " + " AND ".join(clauses)
        with self.service.database.connection() as conn:
            conn.execute("BEGIN")
            _require_user(conn, user_id)
            if peer_id is not None:
                _require_user(conn, peer_id)
            total = conn.execute("SELECT COUNT(*) FROM messages m" + where, params).fetchone()[0]
            rows = conn.execute(
                "SELECT m.*, s.nickname AS sender_name, r.nickname AS receiver_name FROM messages m JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.receiver_id"
                + where + " ORDER BY m.create_time, m.id LIMIT ? OFFSET ?", (*params, limit, offset),
            )
            items = [dict(row) for row in rows]
        return self._result(items, total, offset)
