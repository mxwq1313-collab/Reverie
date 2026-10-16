# 第五阶段 Android Parser 验收

日期：2026-10-12（北京时间）。程序版本 0.5.0，归档结构版本 2，交换协议 1.0。

## 完成项

- android/ 下的 detector、database_reader、schema、extractor、mapper、parser、decryptor 及文档。
- 目录/文件候选检测与 DetectedSource，必要账号和快照元信息。
- SQLite 只读表/字段/结构报告、文件完整性及读取前后指纹检查。
- JSON 注册的 Schema 投影，不将版本字段映射散入核心系统。
- 私聊文本、方向、毫秒时间、来源标识，LoadedDocument 与既有 Validator。
- AndroidAdapter→WeChatImporter→原 Import Engine→归档→浏览器。
- android detect、schema、parse，失败报告及不覆盖输出。
- 独立 Decryptor 接口，当前返回 NotImplemented，不尝试解密。
- android_mock/MicroMsg/mock-account-001/ 下的自建 SQLite 与元信息，未使用真实数据。

输入能力为已解密、已关闭写入、符合登记字段投影的 SQLite 快照，并不保证所有 Android 微信版本兼容。未知 profile、结构、类型及非法文本均明确失败；已知媒体和群聊只统计跳过。

## 测试结果

Windows、Python 3.10.11、SQLite 3.40.1。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

最终 **150 项全部通过，0 失败、0 错误、0 跳过**。原有 99 项保持通过，新增 51 项，超过要求的 30 项。最终运行耗时 14.893 秒。

新增覆盖：

- 正确根/MicroMsg/账号/文件、错误/空/缺失目录、多账号、缺元信息与候选不代表 Schema 支持。
- SQLite 表/列/结构、缺表缺列、类型不匹配、未知 profile、元信息类型/绑定/时间单位/快照声明/哈希错误。
- 文本正文、Unicode/空白、时间/方向、空/null 内容、未知类型、缺联系人、昵称/备注/标识回退。
- 来源和元信息字节保持不变，读上下文不创建侧文件，写入/DDL/ATTACH/危险 PRAGMA 被拒绝。
- WAL/SHM/journal、非明文输入、来源变化、URI/控制字符/穿越等拒绝，Decryptor 不被自动调用。
- 原导入和批内/重复去重、目录自动选择、目标不能覆盖来源/元信息。
- CLI detect/schema/parse、标准输出文件、失败不导出、输出不覆盖来源。

首次测试发现测试代码使用了 Windows 默认编码读取 UTF-8 元信息，已改为明确 UTF-8；运行时元信息 Reader 原本已使用 UTF-8。修正后及异常元信息边界补充后的完整测试通过。

## 模拟流程实测

模拟库含自己、两位联系人和群聊占位，7 条消息：5 条合法私聊文本、1 条图片占位、1 条群聊。解析报告 contacts=2、participants=3、text_messages=5、failed=0、skipped_unsupported_count=2。

实际导入首次新增 5 条，第二次新增 0 条、duplicated_count=5，报告保存在独立 work/ 目录。模拟来源没有写入正式库，原数据核心与浏览器未修改。

输出 android_mock/exchange.json 通过独立 JSON Schema 校验。Microsoft Edge 中张三私聊 3 条、发送气泡 2 条、北京时间 12:01、关键词“开会”返回 1 条，清除后恢复 3 条；无 JavaScript 运行异常。

## 交付和限制

0.5.0 wheel 已检查包含 android/ 代码、README 和 profiles JSON；独立安装后解析 5 条、跳过 2 条，首次导入 5 条、重复跳过 5 条，原浏览查询正常。

源码包包含自建 EnMicroMsg.db、元信息、生成器和标准输出。完整解压后解析和两次导入验证通过，来源 SHA-256 保持不变。缓存、日志、备份、虚拟环境排除。

与第四阶段源码包对比，原数据库、迁移、浏览器、Import Engine 和原测试共 27 个文件逐字节一致，既有两个归档文件也保持字节一致，没有重设计归档数据库或改变浏览器。

版本和字段依据为公开的文本读取资料及 SQLite 官方只读机制，详细链接和约束见 docs/android_parser.md。没有真实手机数据测试、没有解密、没有媒体/群聊解析或超大 Android 源性能验证。
