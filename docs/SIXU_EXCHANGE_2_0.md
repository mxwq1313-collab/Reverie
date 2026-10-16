# 思绪聊天交换 2.0

格式标记为sixu-chat-exchange，format_version为2.0，与旧chat-exchange 1.0区分。Windows桌面文件导入可自动识别，或选择对应格式。

## 数据结构

- namespace：稳定来源命名空间。
- users：id、nickname；可用external_id明确映射到既有身份。微信来源沿用账号命名空间，不按昵称合并。
- chats：id、kind（private/group）、title与members。私聊最多两人，群聊成员明确登记。
- messages：稳定id、chat_id、sender_id、带时区的create_time、kind、原始content。私聊还需receiver_id。群聊不使用单人接收者。
- kind：text、image、emoji、audio、video、file、location或system；emoji以图片资源兼容存储，原始文字和描述保留。未知类型保存在来源中并报告。
- attachments：kind、相对于交换JSON目录的path、可选name/SHA-256和variant（original/compressed/thumbnail）。不接受绝对路径、..、反斜线、链接或重解析点。缺失路径保留为missing；可补齐后重新导入。

每个JSON最多100000条消息、64MiB；单条文本最多16MiB。全部微信历史封存为多个受预算约束的批次，不用动态SDK偏移分页。rich_snapshot.json记录批次、原始JSONL、摘要与计数；原始计数包含未识别发送者及未知类型。

批次导入以SQLite事务为边界；取消保留已提交批次。重新导入同一封存目录会按来源身份去重。相同来源ID内容冲突整批回滚，不覆盖已有消息；不同来源ID的相同原文保留为不同事件。

## 最小私聊示例

```json
{
  "format": "sixu-chat-exchange",
  "format_version": "2.0",
  "namespace": "self-built-example",
  "users": [{"id":"example_self","nickname":"自己"},{"id":"example_peer","nickname":"示例伙伴"}],
  "chats": [{"id":"example_chat","kind":"private","members":["example_self","example_peer"]}],
  "messages": [{"id":"example_1","chat_id":"example_chat","sender_id":"example_self","receiver_id":"example_peer","create_time":"2026-10-15T09:00:00+08:00","kind":"text","content":"保留原文与表情 😀"}]
}
```

附件原文件位于数据库旁的数据库名.media目录；备份和分发归档时需一起保全。导出的HTML/TXT通过相对路径关联附件，manifest.json记录每个输出文件摘要。
