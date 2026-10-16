"""可重复运行的虚构演示数据；不重置或覆盖已有聊天。"""

from .errors import ConflictError
from .services import ChatService
from .database.hashing import ensure_private_chat, message_hash

DEMO_USERS = [
    (1, "demo_me", "我", None),
    (2, "demo_zhang", "张三（演示）", None),
    (3, "demo_li", "李四（演示）", None),
]
DEMO_MESSAGES = [
    (1, 1, 2, "2026-01-01T04:00:00.000000Z", "你好，这是演示聊天。", "text"),
    (2, 2, 1, "2026-01-01T04:01:00.000000Z", "你好，下午三点开会。", "text"),
    (3, 1, 2, "2026-01-01T04:02:00.000000Z", "收到，开会前我会准备材料。", "text"),
    (4, 3, 1, "2026-01-01T05:00:00.000000Z", "文件已经整理好了。", "text"),
    (5, 1, 3, "2026-01-01T05:01:00.000000Z", "谢谢，我稍后查看。", "text"),
]


def seed_demo(service: ChatService) -> bool:
    """空库插入样例，完全相同的样例库不重复插入，其他非空库拒绝写入。"""
    with service.database.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        users = [tuple(row) for row in conn.execute("SELECT id, wxid, nickname, avatar FROM users ORDER BY id")]
        messages = [tuple(row) for row in conn.execute(
            "SELECT id, sender_id, receiver_id, create_time, content, msg_type FROM messages ORDER BY id"
        )]
        if users or messages:
            if users == DEMO_USERS and messages == DEMO_MESSAGES:
                return False
            raise ConflictError("目标库已有其他数据，演示操作已停止；请用 --db 指定新的演示文件")
        conn.executemany("INSERT INTO users(id, wxid, nickname, avatar) VALUES (?, ?, ?, ?)", DEMO_USERS)
        for row in DEMO_MESSAGES:
            _, sender, receiver, stamp, content, _ = row
            chat_id = ensure_private_chat(conn, sender, receiver)[0]
            conn.execute("INSERT INTO messages(id,sender_id,receiver_id,create_time,content,msg_type,chat_id,message_hash) VALUES (?,?,?,?,?,?,?,?)", (*row, chat_id, message_hash(sender, receiver, stamp, content)))
        return True
