"""User-facing descriptions of completed local tool work; protocol names stay internal."""
TOOL_STATUS={
    'archive_overview':('已读取会话概况','会话概况读取未完成'),
    'archive_users':('已读取参与者信息','参与者信息读取未完成'),
    'archive_contacts':('已完成联系人查询','联系人查询未完成'),
    'archive_messages':('已完成聊天记录查询','聊天记录查询未完成'),
    'archive_message':('已完成原始消息读取','原始消息读取未完成'),
}


def tool_status(name,success):
    pair=TOOL_STATUS.get(name,('已完成资料读取','资料读取未完成')) if isinstance(name,str) else ('已完成资料读取','资料读取未完成')
    return pair[0 if success else 1]
