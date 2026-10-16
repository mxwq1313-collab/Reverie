# 第四阶段 WeChat Adapter 验收

日期：2026-10-12（北京时间）。程序版本 0.4.0，数据库结构仍为 2，输出协议 chat-exchange 1.0。

## 完成范围

- WeChatAdapter 抽象接口，所有可运行来源返回 LoadedDocument。
- WeChatBackupParser 的 detect、extract_users、extract_messages、export_exchange 接口。
- 微信模拟数据：账号加两位联系人、两个私聊、五条双向文字消息。
- mock → 标准字段映射、明确秒/毫秒时间单位、发送方向和稳定账号身份。
- 电脑版备份、Android 数据接口预留，当前实际调用均明确拒绝未实现能力。
- 只覆盖 BaseImporter.load 的 WeChatImporter，共用原 Validator、SQL、去重和报告。
- wechat detect、convert、import CLI 入口，转换后的标准 JSON 随工程提供。
- 接入说明、字段映射契约与模块 README。

当前仅支持 wechat-mock 1.0。未实现真实微信数据库读取、加密解密、图片视频提取、群聊或真实电脑版备份解析。

## 原有兼容性

原有数据库、迁移、浏览器与测试文件逐字节对比第三阶段源码包一致；数据库没有新增表或迁移版本。程序元信息与 CLI 新命令是本阶段扩展。

原有 79 项测试原样通过，新增 20 项接入测试，**总计 99 项全部通过，0 失败、0 错误、0 跳过**。本次完整运行耗时 12.993 秒。

测试环境：Windows、Python 3.10.11、SQLite 3.40.1。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

新增检查包括：

- 返回 LoadedDocument，完整样例通过原 Validator。
- msgId、content、source_id、外部身份字段正确映射。
- Unix 秒/毫秒、整数字符串、微秒精度与越界/布尔/浮点错误。
- 发送/接收方向及单人笔记会话正确。
- 首次导入及重复导入共用原去重；转成标准 JSON 再导入也跳过重复。
- 同一批次不同 msgId 的相同消息被跳过；不同账号命名空间不误合并。
- 错误格式、版本、字段、方向、时间和 talker 拒绝并生成失败报告。
- 非文本类型进入原 Validator，部分导入和严格模式继续生效。
- 文件/目录检测、空消息数据和未实现抽象接口。
- BackupFiles / EnMicroMsg.db 检测与拒绝不打开真实内容；显式选择也不能绕过。
- CLI 导入、重复计数、转换、检测、失败报告及不覆盖既有输出/来源。

## 实际流程检查

转换命令生成 wechat_mock/exchange.json：3 位用户、2 个私聊、5 条消息。输出通过独立 JSON Schema Draft 2020-12 校验。

实际 CLI 第一次导入新增 5 条，重复导入新增 0 条、duplicated_count=5，两个报告分别保存。验证使用 work/ 中的独立库和日志目录，没有将模拟记录混入正式库。

Microsoft Edge 实际打开原有浏览器：张三私聊 3 条，自己发送 2 条；李四私聊 2 条；北京时间 12:01 正确。搜索“开会”返回 1 条，清除恢复 3 条。没有 JavaScript 运行异常。截图为 phase4-wechat-mock-preview.png。

## 安装包与源码验证

0.4.0 wheel 已成功构建并检查包含适配器代码、模块 README、原 Schema、迁移 SQL、建表 SQL 和网页资源。独立环境只安装本包后，模拟转换输出 5 条，首次导入新增 5 条、重复导入跳过 5 条，原浏览查询返回张三私聊 3 条、当前身份总计 5 条。

完整解压源码后，`python -m cli wechat import` 首次和重复运行均符合预期。对比第三阶段源码包，原数据库、迁移、浏览器、Import Engine 和原测试共 26 个文件字节一致；未引入数据库或浏览器变更。

正式库仍为空，原虚构演示库仍为 3 位参与者、5 条消息。本机日志、备份、虚拟环境与缓存不进入源码包。

## 后续接口

下一阶段实现具体 Android 解析器，输出 LoadedDocument 后复用当前管线。路径类型检测不等于真实格式或解析能力认证；本阶段 mock 字段规则不是对真实微信版本的格式声明。
