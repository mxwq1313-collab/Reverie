"""只创建虚构 SQLite 数据；测试和交付样例共用生成器。"""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def create_android_fixture(root):
    account = Path(root) / "MicroMsg" / "mock-account-001"
    account.mkdir(parents=True, exist_ok=True)
    database = account / "EnMicroMsg.db"
    if database.exists():
        raise FileExistsError("模拟库已存在，生成器不覆盖文件")
    timestamp = int(datetime.fromisoformat("2026-01-05T12:00:00+08:00").timestamp()) * 1000
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE rcontact(username TEXT PRIMARY KEY, nickname TEXT, conRemark TEXT)")
        conn.execute("CREATE TABLE message(msgId INTEGER PRIMARY KEY, msgSvrId INTEGER, type INTEGER, isSend INTEGER, createTime INTEGER, talker TEXT, content TEXT)")
        conn.execute("CREATE TABLE chatroom(chatroomname TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO rcontact VALUES (?,?,?)", [("wxid_android_me", "我（Android示例）", None), ("wxid_android_zhang", "张三（Android示例）", ""), ("wxid_android_li", "李四（Android示例）", None), ("mock_group@chatroom", "虚构群聊", None)])
        conn.execute("INSERT INTO chatroom VALUES ('mock_group@chatroom')")
        conn.executemany("INSERT INTO message VALUES (?,?,?,?,?,?,?)", [
            (1, 1001, 1, 1, timestamp, "wxid_android_zhang", "你好，这是从 Android 模拟 SQLite 解析的文本。"),
            (2, 1002, 1, 0, timestamp+60000, "wxid_android_zhang", "收到，下午三点开会。"),
            (3, 1003, 1, 1, timestamp+120000, "wxid_android_zhang", "我会提前准备材料。"),
            (4, 1004, 1, 0, timestamp+3600000, "wxid_android_li", "文件已经整理好了。"),
            (5, 1005, 1, 1, timestamp+3660000, "wxid_android_li", "谢谢，我稍后查看。"),
            (6, 1006, 3, 0, timestamp+3700000, "wxid_android_li", "[模拟图片，不提取]"),
            (7, 1007, 1, 0, timestamp+3800000, "mock_group@chatroom", "群成员:\n模拟群消息，不解析")
        ])
    metadata = {"format":"android-wechat-source", "format_version":"1.0", "database_file":"EnMicroMsg.db", "schema_profile":"enmicromsg-legacy-text-v1", "time_unit":"milliseconds", "sqlite_snapshot":True, "account":{"wxid":"wxid_android_me", "nickname":"我（Android示例）"}, "simulation":True, "database_sha256":hashlib.sha256(database.read_bytes()).hexdigest()}
    (account / "android_source.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return database


def refresh_hash(database):
    file = Path(database).parent / "android_source.json"
    metadata = json.loads(file.read_text(encoding="utf-8"))
    metadata["database_sha256"] = hashlib.sha256(Path(database).read_bytes()).hexdigest()
    file.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
