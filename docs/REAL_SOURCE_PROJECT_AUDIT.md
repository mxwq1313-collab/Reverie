# Phase 1：真实微信接入前的项目审查

日期：2026-10-13（北京时间）。本报告在修改产品代码前完成。

## 版本与指令

用户任务模板描述 v0.4.0、目标 v0.5.0；实际工程已为 v0.5.4，历史 v0.5.0 是 Android 明文框架阶段。按现有工程执行真实导入 MVP 功能目标，保留全部历史设计和版本记录，不倒退代码。

项目和祖先目录未找到 AGENTS.md / AGENTS.override.md / agent.md；本会话用户提供的 AGENTS 指令仍适用。已阅读 README、PROJECT_CONTEXT、TODO、CHANGELOG、第三/第四阶段与最近 RMFH 载荷验收记录，检查数据库、迁移、交换 Schema、BaseImporter、Validator、哈希、Adapter 和 CLI。

## 已完成能力

- SQLite 存储及用户/消息 CRUD，私聊、会话成员和来源别名；当前数据库 PRAGMA user_version=2。
- 实际表：users、messages、chats、chat_members、chat_sources、migration_history。
- chat-exchange 1.0：source / users / chats / messages / media 预留；当前运行支持私聊文本。
- BaseImporter 生命周期：检查报告目录 → load 返回 LoadedDocument → validate_document → 初始化/迁移归档 → 单事务持久化 → 保存报告。
- Validator 检查必填/未知字段、来源、身份引用、会话成员、时间、文件内重复标识和能力范围；默认允许部分合法记录导入，严格模式整批拒绝/回滚。
- 去重：内部双方 ID、UTC 时间、原文内容四项经无歧义 JSON 和 SHA-256；批内与已有库均检查。
- 浏览器、本机只读接口、搜索/筛选/分页、桌面导入入口。
- mock 转换链路、条件明确的 Android 明文适配、RMFH 外壳/有限载荷证据；已有 297 项运行记录，296 通过、1 个权限项跳过。

## 当前不足

没有完成真实微信私聊从来源到 SQLite/网页的验收。RMFH 文件识别、元信息 wire 兼容和载荷取样不等于真实消息解码；此前真实文本恢复为 0。手机提供版本 8.0.69，本机当前 Weixin.exe 为 4.1.15.51，尚不能据此断言备份创建时版本。

Import Engine 不负责提取数据库密钥或操作微信。当前仅有 mock/backup/android Adapter，没有成熟 Windows 导出结果的来源解析与标准化。

## 保持稳定的部分

Database Layer、迁移、BaseImporter 的事务与写入、Validator、哈希及原网页资源均不做无意义重构。新来源应提供 LoadedDocument，再走现有 Validator/Importer。群聊和媒体保持显式未支持。

## 数据模型检查

- Message.id 仅为交换文档内 ID。数据库还保留 source、source_id、source_hash、external_id；不能假定来源 local_id 全局唯一。
- 新接入应保留平台、账号、来源数据库/导出逻辑来源、原始消息 ID；必要时组合身份生成交换 ID。来源没提供数据库分片信息时明确记录未知，不编造。
- User.external_id 写入 users.wxid，必须基于稳定 wxid/账号身份，昵称仅用于展示。多个导出工具应复用同一账号的稳定身份命名空间。
- source.metadata 可携带来源工具、版本和原始来源报告引用；当前 Message 不允许额外 raw_type/raw_payload 属性。
- 未知类型和群聊应保留在来源侧隔离记录（raw_type、raw_payload、parse_status、原因和位置），并在导入报告可见；不静默丢弃，不为了这一项更改稳定 SQLite 表。
- 现有内容哈希可能合并同双方、同一时间精度且相同内容的两条不同来源消息。适配器应检测这种歧义并明确拒绝/记录，不能伪造时间来绕过去重。

## 四层接入边界

1. 数据获取：调用已审查的第三方工具，取得本机结构化导出；不把获取密钥逻辑写进 Adapter。
2. 来源解析：按工具实测/源码确认的 JSON/SQLite 契约读字段，保留未支持记录和来源证据。
3. 标准化：ExternalExportSource → chat-exchange 1.0，明确账号、方向、时间单位和复合消息标识。
4. 通用导入：既有 Validator → BaseImporter → SQLite → Web。

## 验收门槛

选择一个真实私聊，身份使用可验证的来源 ID；至少含双方文本及来源时间。第一次导入可在原网页接口读取，第二次新增为 0。自动测试和真实验收分开记录；没有真实来源时不得用 mock 宣称完成。
