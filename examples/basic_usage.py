"""从项目目录运行：python -m examples.basic_usage。创建独立的示例数据库。"""

from datetime import datetime, timezone
from pathlib import Path
import sys

from wechat_archive import ChatService, NotFoundError


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    path = Path(__file__).resolve().parents[1] / "data" / "api_example.db"
    service = ChatService(path)
    # 用独立标识查找或新增；重复运行也不会重复建立联系人。
    users = []
    for wxid, nickname in (("example_me", "我"), ("example_friend", "示例朋友")):
        try:
            user = service.get_user_by_wxid(wxid)
        except NotFoundError:
            user = service.create_user(wxid, nickname)
        users.append(user)
    me, friend = users
    message = service.create_message(me.id, friend.id, "这是 Python 接口写入的示例。", create_time=datetime.now(timezone.utc))
    print("数据库：", path)
    print("新增：", message)
    print("查询：", service.get_message(message.id))
    print("更新：", service.update_message(message.id, content="这条示例消息已经修改。"))
    print("双向聊天：", service.get_conversation(me.id, friend.id))
    print("搜索：", service.search_messages("示例"))
    service.delete_message(message.id)
    print("删除本次示例消息后：", service.stats())


if __name__ == "__main__":
    main()
