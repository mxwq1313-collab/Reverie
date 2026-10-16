# 标准聊天交换格式与 Import Engine

工程版本 0.3.0、交换协议 1.0、数据库结构版本 2 分别管理程序、输入和存储，不应混用。

## 快速使用

从完整解压的项目目录运行，样例使用独立练习库：

```powershell
python main.py --db data/import_demo.db import examples/chat_sample.json
python main.py --db data/import_demo.db import examples/chat_sample.json
python main.py --db data/import_demo.db serve --open --port 0
```

第一次新增 2 位用户、1 个私聊、3 条消息；第二次新增 0 条，`duplicated_count=3`。第三条打开原有浏览器查看导入结果。

```powershell
python main.py --db data/csv_demo.db import examples/chat_sample.csv --namespace my-account --timezone +08:00
python -m wechat_archive --db data/my_archive.db import chat.json --strict --report-dir import_logs
```

源码目录另支持 `python -m cli ...`；安装包使用 `python -m wechat_archive ...` 或 `wechat-archive ...`。`--db` 在子命令前，导入选项在文件参数后。`.csv` 自动选择 CSV，其余按 JSON 读取；可用 `--format json/csv` 显式指定。

## JSON 协议

完整 Schema：`wechat_archive/importer/schemas/chat-exchange-v1.schema.json`，采用 JSON Schema Draft 2020-12。正常示例：`examples/chat_sample.json`；空数据：`examples/chat_empty.json`。

根对象要求 `format="chat-exchange"`、`format_version="1.0"`、`source`、`users`、`chats`、`messages`。三个记录数组允许为空；`media` 可省略，当前版本必须为空。

未声明字段、重复 JSON 对象键、NaN/Infinity、错误类型、无效 Unicode 和业务文本中的空字符都会报错。Schema 检查结构；ID 唯一性、引用、成员关系和当前运行能力由 `validator.py` 继续检查。

### Source

必填 `id` 是稳定来源命名空间，建议区分平台和账号，不能使用每次变化的临时文件名。可选 `name`、`account_id`、对象型 `metadata`；来源元数据保存到导入报告。

### User

| 字段 | 规则 |
|---|---|
| `id` | 文件内唯一的非空字符串，供其他记录引用，与 SQLite ID 不同 |
| `external_id` | 必填，跨文件稳定、全库唯一，写入 `users.wxid` |
| `nickname` | 必填非空文字，去除首尾空白 |
| `avatar` | 可选文字或 null，只保存标识，不读文件或网络 |

来源命名空间不会自动添加到 JSON 用户身份。平台或账号可能复用 ID 时，解析器应生成带平台/账号前缀的 `external_id`。不能只凭昵称合并同名用户。

已有 external_id 会复用联系人。新文件的昵称或头像不同则保留既有值，并在报告 warnings 中注明，不覆盖原资料。

### Chat

必填 `id`、`type`、`participant_ids`，可选 `external_id` 和 `title`。external_id 默认使用 id，与 source.id 共同标识来源会话。当前仅支持 private，需 1 或 2 个不同、合法的用户引用；1 人表示给自己留消息。

同一内部参与者组合复用一个私聊，`chat_sources` 保存来源别名。已绑定不同参与者的 `(source.id, external_id)` 会报冲突，不重新绑定。group 是协议预留，当前导入器拒绝。

### Message

| 字段 | 规则 |
|---|---|
| `id` | 文件内唯一，保存在内部消息 external_id 中 |
| `sender_id`、`receiver_id` | 必须引用本文件的合法用户 |
| `chat_id` | 必须引用合法会话，双方与私聊参与者一致 |
| `timestamp` | 带时区 ISO 8601，必须有秒，最多 6 位小数 |
| `type` | 当前仅支持 text |
| `content` | 必填非空文字，保留原始空白、换行和 Unicode |
| `source_id` | 可选原始消息 ID；未给出时使用文件内 id |
| `source_hash` | 可选 64 位 SHA-256，作为来源信息保存 |
| `media_ids` | 可选媒体 ID 数组，引用顶层 Media.id；当前必须为空 |

时间例如 `2026-01-01T12:00:00+08:00`，写入时统一为 UTC 固定微秒格式 `2026-01-01T04:00:00.000000Z`。JSON 不猜测缺失时区；未来解析器负责转换原始时间戳。

### Media 预留

Schema 定义了媒体 id、type、uri、mime_type、sha256、size_bytes，以及 image/video/audio/file 类型。当前不访问资源引用、不复制、不下载；非空 media 拒绝整份文件，避免静默忽略附件。

协议还预留 group 会话和 image/video/audio/file/system 消息。当前明确拒绝这些能力，不能据此声称已支持媒体或微信兼容性。

## CSV

UTF-8 或 UTF-8 BOM。表头恰好含 time,sender,receiver,content,type，顺序可变，不能缺少、重复或增加字段。逗号、引号和换行使用标准 CSV 引号规则。

```csv
time,sender,receiver,content,type
2026-01-01 12:00,我,张三,你好,text
2026-01-01 12:01,张三,我,收到,text
```

sender/receiver 是名字。外部身份为 `csv:<编码后的 namespace>:<编码后的名字>`；默认 namespace 为 default。同一 namespace 中同名视为同一用户；多个账号要指定不同 namespace。要区分同名用户或与其他来源精确合并时，使用 JSON 的稳定 external_id。

时间支持带时区 ISO，以及无时区的 `YYYY-MM-DD HH:MM`、`YYYY-MM-DD HH:MM:SS`、最多 6 位微秒的 `YYYY-MM-DD HH:MM:SS.ffffff`。无时区默认 +08:00，可用 `--timezone Z` 或固定偏移修改，不接受 IANA 名称。已经有时区的 CSV 时间不受默认值覆盖。

仅表头是合法空数据；零字节文件缺少表头，返回文件级错误。报告包含逻辑消息序号及记录结束处的物理行号；多行内容可能跨行。

## 校验和提交

默认先解析、校验整份文件，再在一个写事务中保存合法记录。错误记录及其依赖消息跳过并报告；合法但没有消息的用户也可创建。

`--strict` 在输入出现任何错误时拒绝整份文件；写入阶段发生来源会话冲突或约束错误时，整批导入写入回滚。格式版本错误、损坏文件、缺少文件、非空媒体等文件级错误不进行导入写入。存储故障回滚导入事务。数据库自动升级是此前独立的可备份步骤。

错误示例：

```json
{"entity":"message","index":23,"code":"missing_field","message":"第23条消息失败：缺少发送者（sender_id）","field":"sender_id","record_id":"m23","line":null}
```

导入结果以 JSON 输出到标准输出：退出码 0 为 success，2 为 partial，1 为 failed。partial 可表示合法用户已保存而消息失败，应查看分项计数。报告目录不可写时，写库前停止；提交后突发日志写入故障则返回真实结果和 report_error，不宣称日志已保存。

## 去重

```text
message_hash = SHA256(UTF8(紧凑 JSON([内部发送者 ID, 内部接收者 ID, UTC 固定精度时间, 原始内容])))
```

数组编码避免直接拼接的边界歧义。不同时间偏移表示同一时刻会匹配；空白、换行或字符变化产生不同哈希。同一双方、同一微秒、相同文字视为一条消息，即使 source_id 不同。

哈希是本库去重键，不作为跨库身份；source_hash 另作来源保留。已有 CRUD、导入和迁移后的旧消息共用算法；修改双方、时间或内容会更新哈希。

使用非唯一索引保留旧库可能已有的重复记录；Importer 在 BEGIN IMMEDIATE 写锁内检查已存在哈希和本批哈希，重复导入会跳过。普通 CRUD 仍允许主动创建相同消息，保持既有行为。

## 报告

每次导入在项目 import_logs/ 保存 UTC 时间加随机导入 ID 命名的 JSON。包含来源、目标库、状态、用户/会话/消息输入数、创建/复用/失败数、成功/失败/重复消息数、耗时、错误、警告、回滚和迁移备份路径。

`messages = success_count + failed_count + duplicated_count`。users/chats/messages 是输入数，不是数据库总数；success/failed 为消息计数别名，time 为耗时文字。文件级错误通过 issues.entity=file 表达，不能仅用消息失败数判断是否成功。

## 迁移与扩展

版本 1→2 新增 chats、chat_members、chat_sources、migration_history，为 messages 追加 chat_id、message_hash、source、source_id、source_hash、external_id。旧 ID、正文、既有重复消息保留；时间统一为等价 UTC。

```powershell
python main.py --db data/chat.db migrate
```

打开受支持旧库也会自动升级。先用 SQLite backup API 在库旁 migration_backups/ 生成完整快照并验证，然后在同一事务中提交 DDL、回填、版本和历史。失败回滚且保留备份；新空库不备份，已升级库不重复备份。未知库、损坏结构、未来版本拒绝，不覆盖。

没有自动降级；v0.2.0 不能读结构版本 2，使用旧版时须读取升级前备份副本。本机日志和备份不打入源码压缩包。

第四阶段解析器继承 BaseImporter，实现 load(path) 返回 LoadedDocument，payload 满足本格式即可；其他校验、映射、写库、去重和报告共用。CSV 可附带 line_numbers。

未来添加能力时新增迁移 SQL、注册版本步骤、更新对应结构检查与模型，再补升级/回滚/兼容测试，不改写已发布旧迁移。当前 JSON/CSV 读取为内存中间模型，5 万条已验证，超大文件及长期并发性能未验证。
