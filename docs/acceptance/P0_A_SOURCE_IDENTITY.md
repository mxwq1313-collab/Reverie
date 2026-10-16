# P0 A 来源身份与跨批次去重验收

审查基线日期：2026-10-13；本阶段验收日期：2026-10-14（Asia/Shanghai）。源码基线Commit：13ebbde；分支feature/archive-platform-v0-9。验收对象为本阶段源码，不是既有Windows发行包。应用版本0.8.0、SQLite Schema2、chat-exchange1.0保持。

## 结论

P0-A源码验收通过。经登记Windows结构化来源的不同事件不再因发送者、时间和正文相同而合并；同一来源ID的内容冲突明确失败，不覆盖已有消息。普通JSON/CSV、mock和Android保持legacy内容去重，本阶段没有扩展来源支持或恢复历史已丢失事件。

## 修改与实际行为

| 条件 | 当前结果 |
|---|---|
| 不同复合来源ID、相同双方/时间/正文，同批或跨批 | 分别入库，重复数为0 |
| 相同来源ID、双方/时间/正文/类型/会话相同 | 判为重复；重新创建Importer或重复文件行为一致 |
| 相同来源ID、正文/时间/方向或已归档文本被用户修改 | source_identity_conflict；不覆盖，默认记录失败，严格模式整批回滚 |
| 相同来源ID对应多条已有记录 | source_identity_ambiguous；保留已有记录并要求核对 |
| 新来源事件与缺少登记来源身份的旧消息内容完全相同 | legacy_identity_ambiguous；不静默合并，不擅自重复追加 |
| 不同账号、会话、分片、local/server ID类型 | 依登记复合身份分别处理 |
| 普通交换JSON包含identity_strategy元信息 | 不改变主机策略，仍为legacy-content |

LoadedDocument/ImportDocument增加仅由可信主机Loader声明的identity_strategy，报告记录实际策略。Normalizer不再拒绝不同ID的相同文本；共享Importer在已有BEGIN IMMEDIATE事务内检查(source,source_id)，使用既有source与hash索引，不新增数据库表/列，也不删除或重算旧hash。来源原记录、输出文件及旧归档不被覆盖。

## 验证

全部自动数据为自建；隔离快照由实际Git的169个跟踪文件逐文件复制，真实聊天/账号/原库未参与。

| 验证 | 结果 |
|---|---|
| 新测试修复前 | 17项：4通过、11失败、2缺少新策略字段错误；确认旧行为与新契约差异 |
| 新来源身份回归修复后 | 17/17通过，含跨批、同批、重启、冲突、旧数据歧义、CRUD编辑及严格回滚 |
| 既有外部来源契约 | 34/34通过；其中一个旧“拒绝相同内容不同ID”测试更新为明确保留3个事件 |
| 完整业务回归 | 457运行，456通过，0失败/错误，1跳过；unittest主体71.699秒 |
| 跳过 | test_symlink_to_backup_rejected：Windows symlink privilege unavailable；没有修改权限或绕过 |
| 管理回归 | 15/15通过，2.466秒；前次请求自动审批超时未启动，获准重试一次后通过 |
| 5万条原有自建导入案例 | 首次2.581670秒，重复0.711714秒；属于当前机器文本基准，不外推媒体/其他机器 |

实际命令为`python -B -X utf8 -m unittest discover -s tests -v`和`python -B -X utf8 -m unittest discover -s tools/tests -v`；新增/相关测试先单独执行。夹具由已有tools/prepare_fixtures.py恢复。原始日志位于当前工作区work/archive_step1/evidence，未进入发行包或Git数据目录。

本阶段没有重做真实微信获取、模型推理和EXE验收；桌面/网页/助手现有源码回归通过，不代表既有EXE已经包含此修复。Schema1/2迁移、标准协议和旧入口由完整回归保护。

## 开源比较和下一步调整

[WechatExporter](https://github.com/BlueMatthew/WechatExporter)的当前说明涉及iTunes来源、多类型/群名称及增量导出。本阶段缩小了事件身份与重复导入方面的缺口，但本项目完整获取、群聊、附件/导出类型和增量会话仍不足；不同输入来源无法用测试数量直接比较解析能力。其GPL-2.0代码不复制到本项目。

[chatlog](https://github.com/sjzar/chatlog)与[PyWxDump](https://github.com/xaoyaoo/PyWxDump)原仓库仅有移除通知，不能当成可接入旧实现。本阶段不扩展未知来源或换SDK；固定来源仍需验证完整快照、分片游标和客户端兼容。

下一阶段为P0-B：统一消息、来源、引用、能力与批次契约，保持旧文本路径和数据格式。根据用户新增重点，契约必须覆盖Codex界面的会话范围、账号/连接/登录/回答状态和引用展开需求；随后P0-C/D完成存储与完整性基础，再在P1优先改善Codex会话体验、界面状态及功能闭环。每个后续阶段单独验收、重新比较差距并本地Commit。
