# Phase 2/3：真实微信数据路线比较与选择

日期：2026-10-13。本机当前 Windows Weixin.exe=4.1.15.51。现有工程 v0.5.4，SQLite Schema 2、chat-exchange 1.0。

## 比较

| 项目 | 获取/输出 | 身份和消息字段 | 当前证据 | 本阶段选择 |
|---|---|---|---|---|
| wechatauto-replica | 本机加密 Windows 库的只读读取，JSON/SQLite 导出及 Python DB API | local_id、server_id、create_time、content；新版 get_messages 还保留 shard 与按该分片 Name2Id 解析的 sender_username | PyPI 1.2.6.1 已审查；本机 20 个库密钥校验通过，真实私聊 38 条原文入库、二次新增 0、用户确认页面显示 | 主线，隔离调用 DB 读取层 |
| PyWxDump | 历史上支持解密库及 JSON/CSV 导出 | 需按特定版本导出契约再核查 | 当前仓库访问不可用，GitHub 主题显示“删库”；原作者仓库 issue 的历史环境为 3.9.12.51 / PyWxDump 3.1.45，不足以证明当前 4.1.15.51 可用 | 不作为主线，不下载未知镜像 |
| sjzar/chatlog | 历史数据访问工具 | 当前无法审查可运行代码 | 主仓库仅留 2025-10-20 移除通知，代码和历史已移除；不能把旧能力当成现时可运行发行包 | 不作为主线 |
| ChatImportKit / RMFH | 目录、容器、元信息研究 | 正文加密/Schema 未验证 | 本机 56 个载荷样本编码未知，既有认证组合未恢复真实文本；公开参考也声明正文解密仍在研究 | 保留研究，不阻塞 Windows 导出主线 |

## 选择及必要修正

选定 wechatauto-replica 1.2.6.1 的 WeChatDB 读取 API，在项目之外的隔离环境使用。wheel SHA-256：5400c6e2155f157fac2caa3c0786f1035a81d3e1246427ab52771a3c992a81fc。许可 Apache-2.0；不复制底层算法到本项目。

其普通 export_history JSON 虽有稳定聊天 username，但未导出 shard/sender_username，仅有分片内部 sender_id 与展示姓名；直接使用会违反本项目身份要求。get_messages 已提供真实 sender_username 和 shard，来源获取层将保留这些字段，并用 get_message_row 保留 raw_type/raw_payload，再输出结构化文件。

不能假定 sender_id=2 就是自己，也不能用昵称识别群成员。群发送者需按消息所在分片 Name2Id 解析；本阶段仅选择真实私聊，群数据不进入聊天库。

不使用该工具的发送、监听、OCR、图片或 UI 无障碍热激活功能。仅加载已审查 DB 模块，日志静默，密钥保留内存，不写 key cache；源加密文件只读，明文工作副本写入独立工作目录。产品 Adapter 不获取密钥，只读第三方结构化结果。

## 已验证 / 未验证

- 已验证：本机 4.1.15.51 的库访问准备、自身联系人匹配、真实私聊双方 wxid、原 SQL 文本、时间及分片；38 条首次入库、二次新增 0/重复 38；网页接口读取以及用户人工确认双方文字。
- 公开 README 的版本宣传不是本机实测依据。该单例不能外推所有微信版本、所有账号、完整历史、二进制文本、媒体或群聊。
- 浏览器管理员策略阻止代理自动页面检查，未绕过；显示结论依据用户的明确人工确认。详见 REAL_WECHAT_MVP_ACCEPTANCE.md。
- RMFH 正文路线仍未解决；Windows 成功不证明备份包可解密。

## 原始参考

- https://github.com/fanyuantaier/wechatauto-replica
- https://github.com/fanyuantaier/wechatauto-replica/blob/main/wechatauto/db.py
- https://pypi.org/project/wechatauto-replica/1.2.6.1/
- https://github.com/xaoyaoo/PyWxDump/issues/248
- https://github.com/topics/wxdump
- https://github.com/sjzar/chatlog
- https://github.com/Cjh-y/ChatImportKit
