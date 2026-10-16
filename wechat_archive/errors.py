"""调用者可区分输入错误、记录不存在和数据冲突。"""


class ArchiveError(Exception):
    """聊天归档业务错误。"""


class ValidationError(ArchiveError, ValueError):
    """输入格式或范围不合法。"""


class NotFoundError(ArchiveError, LookupError):
    """请求的联系人或消息不存在。"""


class ConflictError(ArchiveError):
    """唯一标识、外键关联或数据库版本冲突。"""
