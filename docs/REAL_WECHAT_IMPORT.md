# 真实 Windows 微信私聊导入（v0.5.5）

本版本把一个真实 Windows 微信私聊接入既有平台，不更换数据库或浏览器。已实测 Windows 微信 4.1.15.51，提取工具 wechatauto-replica 1.2.6.1。本次成功不能外推其他微信版本或所有消息存储方式。

## 四层架构

| 层 | 文件/接口 | 职责 |
|---|---|---|
| 获取 | wechat_source/acquisition.py | 在独立工作进程调用已审查的第三方 DB API，生成真实结构化文件；密钥不进入项目 Adapter |
| 来源解析 | wechat_source/parser.py | 只读读取登记的来源格式，校验版本、身份、时间单位、路径和读取上限 |
| 标准化 | wechat_source/mapper.py、ExternalExportAdapter | 原字段转换为 chat-exchange 1.0 / LoadedDocument；来源证据与未支持记录保留 |
| 通用导入 | 原 Validator、BaseImporter、SQLite | 原校验、事务、去重、导入报告；原 Web 浏览 |

Adapter 不扫描微信进程、不解密原库、不另建数据库写入流程。数据库仍为 Schema 2，交换协议仍为 1.0。

## 从现有导出文件导入

源码包先全部解压。从项目目录运行：

```powershell
python -m cli wechat detect "D:\chat_exports\private.json"
python -m cli wechat convert "D:\chat_exports\private.json" --adapter external --output "D:\chat_exports\private_exchange.json"
python -m cli --db data/my_wechat.db wechat import "D:\chat_exports\private.json" --adapter external
python -m cli --db data/my_wechat.db wechat import "D:\chat_exports\private.json" --adapter external
python main.py --db data/my_wechat.db serve --open --port 0
```

转换是可选项，不写数据库；输出必须是新文件。导入可以选择已存在的归档，追加并去重。来源 JSON 不能成为归档目标。

桌面方式：双击 `导入数据.cmd`，选择 **Windows 微信结构化导出** 或 **自动识别**，选择真实 JSON → 预览检查 → 开始导入 → 查看已导入的聊天。窗口仍使用原报告和浏览器；不会把真实来源替换成示例。当前窗口接收文件，尚未提供一键获取 Windows 微信数据按钮。

## 获取本机真实私聊

保持 Windows 微信已登录。数据获取工具放在独立 Python 环境，归档核心不依赖它。不需要手机连接，不访问 Android 数据库。

首次使用时可在项目外准备工具环境，例如：

```powershell
python -m venv D:\wechat_tools\source_env
D:\wechat_tools\source_env\Scripts\python.exe -m pip install cryptography==50.0.2 zstandard==0.25.0
D:\wechat_tools\source_env\Scripts\python.exe -m pip install --no-deps wechatauto-replica==1.2.6.1
```

只安装来源读取所需依赖。调用工具包的完整 UI 门面需要其他依赖，本项目不调用它。工作进程校验工具版本和已审查 db.py 的 SHA-256；新版本或修改过的模块明确拒绝，须重新审查。

从归档项目目录获取一个双向私聊：

```powershell
python -m cli wechat acquire-export "D:\chat_exports\private.json" --tool-python "D:\wechat_tools\source_env\Scripts\python.exe" --workdir "D:\wechat_tools\private_work" --limit 50
```

`--peer` 可提供已知稳定 wxid，不能填昵称。省略时从最近会话选择第一个可核验的双向私聊；当前使用检测到的首个账号，明确多账号选择留待下一阶段。`--limit` 为 2–500 条来源记录，不代表全部历史文本条数。没有可核验双向文本时明确失败。

输出文件必须是新的 `.json`，不覆盖；输出和工作目录不能位于微信原数据目录。获取层只读访问原库，第三方工具解密出的副本位于独立工作目录。工作副本与导出包含个人聊天，应留在本机，不进入源码压缩包或自动测试。

只加载未修改的 DB 模块，隔离 UI/OCR 门面；不操作微信窗口、不发送消息、不运行无障碍热激活。密钥在内存使用，覆盖第三方持久化回调以禁用 key cache；标准化文件与导入报告不保存密钥。

## 已登记来源契约

不是“任何 JSON 都支持”。入口格式标志为 `wechat-external-export`、版本 `1.0`，工具为 `wechatauto-replica 1.2.6.1`，API 为 `WeChatDB.get_messages+get_message_row`。

| 来源字段 | 标准化/证据 |
|---|---|
| account.wxid、conversation.wxid | 文档用户引用；数据库 external_id 使用账号与 wxid 命名空间，昵称仅展示 |
| account.verification=contact_row | 获取时核对自身联系人行，不根据昵称或分片内部 sender_id 猜账号 |
| conversation.kind=private | 当前只支持两人私聊，群来源整份拒绝 |
| timestamp_unit=unix_seconds | 整数 Unix 秒 → UTC 标准时间；不通过数值长度猜秒/毫秒 |
| source_database | 原消息分片标识，保留在来源复合 ID 和元信息 |
| source_message_id、source_id_kind | 原 server_id，缺少时使用分片内 local_id；组合账号/私聊/分片/ID 类型后生成文档 ID |
| sender_wxid | 来自所在分片 Name2Id 的解析，不假定 sender_id=2 为自己；收件人是本私聊另一方 |
| raw_type、raw_payload.database_row | 原 SQL 类型、内容、时间、ID、分片、sort_seq 与身份核验；二进制以 base64 保留 |
| capture | 实际客户端版本、获取时间、验证库数量、密钥缓存禁用标志 |

原始内容须为 SQL 字符串，`local_type=1`，并与来源记录内容完全一致；保留空格、换行、Unicode。二进制文本、SDK 展示占位和未验证解码不当作恢复出的文字。

标准化按原时间、sort_seq、分片、local_id 排序。消息 ID 不假设全局唯一：`source_id` 是 `[账号,私聊,分片,server/local,原ID]` 的 JSON，`source_hash` 是原记录摘要。source.metadata 保留 source_platform、source_account、source_databases、工具、获取信息和来源文件指纹。

## 未支持记录、错误与去重

当前运行模型只有文本，不增加群聊或媒体数据库表。未知/非文本/无效来源记录保存到 `source.metadata.external_parse.quarantine_records`，每条有 raw_type、raw_payload、parse_status、reason 和来源位置。原文件也完整保留。

默认把已核验文本交给原 Validator/Importer，同时在导入报告 warnings 提示隔离数量。严格模式 `--strict` 遇到任何隔离记录拒绝整份文件。文件内全无可核验文本时失败，不建立归档；失败报告仍保留来源隔离元信息。检测成功只是候选类型，预览/标准化才确认记录可支持。

格式/工具版本/身份/时间单位未知，读取超限，引用或来源证据不一致均明确报错。JSON 上限 64 MiB、记录上限 100000，重复键/NaN/链接或不允许的路径拒绝，不尝试猜测字段。

去重仍使用原内部双方 ID、UTC 时间和原文的 SHA-256。重复导出入库新增 0。若两个不同来源 ID 具有完全相同的双方、秒时间和内容，当前引擎不能安全区分，Adapter 拒绝歧义；不微调时间、不静默合并、不改数据库。跨文件历史冲突的完整兼容方案仍需后续设计。

## 当前支持范围

已验证一个真实 Windows 私聊的原始 SQL 文本、小批量导出、CLI/窗口文件导入、重复去重和原网页显示。未验证其他微信版本/全部账号/全历史；未实现二进制文本解码、群聊、媒体、官方 RMFH 正文恢复。

数据获取依赖仍可读取本机版本的第三方工具。版本升级后先重新验证工具和字段契约，未知变化拒绝。下一步是账号/私聊选择、全历史分页与断点获取，随后接入窗口获取按钮。

开源参考：[wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica)、[PyPI 1.2.6.1](https://pypi.org/project/wechatauto-replica/1.2.6.1/)。本项目调用其 DB API，未复制其底层密钥/解密算法。
