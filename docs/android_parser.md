# 第五阶段 Android 微信解析框架

程序版本 0.5.0，现有归档数据库结构仍为 2，输出协议仍为 chat-exchange 1.0。

## 输入和支持边界

当前可以读取**已解密、已关闭写入、满足登记字段投影的 Android SQLite 快照**。必须同时提供 android_source.json 声明账号、Schema 和时间单位。检测到 MicroMsg 或 EnMicroMsg.db 只是候选，不代表解析成功。

这是对输入结构的明确支持，不是所有微信版本的兼容性认证。开发及验收全部使用自建模拟库，未读取真实用户数据。

支持：目录/文件检测、SQLite 表和字段报告、私聊 text、方向/毫秒时间映射、LoadedDocument、原导入引擎与去重。不支持：解密、未知 Schema、未知消息类型、媒体资源提取和群聊解析。

已知但不支持的记录统计到 skipped_unsupported_count；未知类型或受支持文本中的错误使整次解析 failed，document=None，不能继续导入。不要把 skipped 和 failed 混为一类。

## 先运行模拟样例

完整解压项目，在项目目录执行：

```powershell
python -m cli android detect android_mock
python -m cli android schema android_mock
python -m cli android parse android_mock --output data/android_exchange.json
python -m cli --db data/android_demo.db wechat import android_mock --adapter android
python -m cli --db data/android_demo.db wechat import android_mock --adapter android
python main.py --db data/android_demo.db serve --open --port 0
```

detect 输出候选报告；schema 输出只读表结构；parse 输出解析报告并保存标准 JSON，不写归档库。wechat import 才通过原引擎写入指定目标。

模拟源 7 条：解析 5 条私聊文本，图片/群聊各跳过 1 条，失败 0。首次导入 5 条，重复导入新增 0、重复 5。已生成标准文档也在 android_mock/exchange.json。

android parse 输出必须使用新文件，不能覆盖来源或已有文件。失败不会输出交换文档。CLI 成功退出 0，失败退出 1；导入的退出码及日志沿用既有 Import Engine。源码用 python -m cli，安装包用 python -m wechat_archive 或 wechat-archive。

## 目录、文件和元信息

```text
android_mock/
├── MicroMsg/
│   └── mock-account-001/
│       ├── EnMicroMsg.db        # 自建 SQLite，不是真实手机数据
│       └── android_source.json
└── exchange.json              # 标准输出示例
```

目录检测只扫描指定目录、MicroMsg 和其直接账号子目录，不遍历整台设备。发现多个账号数据库时失败，必须指定一个文件或账号目录。文件输入可使用明确的 .db/.sqlite/.sqlite3，元信息应在同一目录并准确绑定文件名。

必要元信息示例：

```json
{
  "format": "android-wechat-source",
  "format_version": "1.0",
  "database_file": "EnMicroMsg.db",
  "schema_profile": "enmicromsg-legacy-text-v1",
  "time_unit": "milliseconds",
  "sqlite_snapshot": true,
  "account": {"wxid": "账号的稳定标识", "nickname": "账号昵称"},
  "simulation": false
}
```

可选 database_sha256 为 64 位哈希，用于把元信息绑定到快照；有值时必须匹配。示例库有该哈希且 simulation=true。元信息必须是 UTF-8 JSON；未知字段、版本、错误类型、路径跳转都拒绝。不能在元信息里加入密钥；当前没有密钥获取或使用入口。

账号由明确元信息提供，不从昵称、目录哈希或其他联系人猜测。必要时由上游数据获取流程确认账号；元信息声明本身不证明数据来自哪个微信版本。

DetectedSource 的 confidence 是路径/文件线索评分，不是准确率、真实性或版本兼容性概率。状态 candidate 还须经过元信息、只读完整性、Schema 及数据校验。

## Schema 配置和映射

登记配置位于 wechat_adapter/android/profiles/legacy_text_v1.json，由 schema.py 注册，extractor 和 mapper 只使用逻辑字段映射。微信版本细节不会进入既有数据库、浏览器或 Import Engine。

| 来源投影 | 标准字段/行为 |
|---|---|
| rcontact.username | User.id 与带账号范围的 external_id |
| rcontact.conRemark / nickname | 优先备注，再昵称，再稳定 username |
| message.msgId | 文件内局部 Message.id，必须为正整数且唯一 |
| message.msgSvrId（可选） | 大于 0 时记为 server:ID，否则使用 local:msgId |
| message.createTime | 明确毫秒整数，转换为 UTC 固定微秒 ISO |
| message.talker | 已定义对方身份及 private 会话 |
| message.isSend | 1：账号→对方；0：对方→账号 |
| message.type=1 | 当前支持的文本 |
| message.content | 原始文字，保留空白、换行和 Unicode |

公开 Android 读取实现使用 message/rcontact、毫秒 createTime、isSend 以及 @chatroom 分组标识，本工程据此登记一个有限投影；这里只参考字段语义，没有复制或移植其解析/资源代码。[公开字段读取实现](https://raw.githubusercontent.com/ppwwyyxx/wechat-dump/master/wechat/parser.py)、[类型定义](https://raw.githubusercontent.com/ppwwyyxx/wechat-dump/master/wechat/msg.py)。

当前必需 message 的 msgId、createTime、talker、isSend、type、content，rcontact 的 username、nickname；按配置检查 INTEGER/TEXT 亲和类型。conRemark、msgSvrId 为可选列。无关额外列/表只出现在结构报告中，不参与解析；这不作为未知版本已被认证的依据。

当前 profile 要求毫秒，接受的日期范围为 2000 年起至 2101 年前。这是保守配置边界，用于发现单位错配，不是宣称真实微信日期范围。范围、类型码和 group 后缀都在 profile 中管理。未知 profile、缺少字段、字段类型或时间单位不匹配均失败，不尝试其他映射。

外部身份为 wechat-android:<编码账号>:<编码用户>，与 mock 身份范围分离。已删除联系人导致 talker 无定义时，当前失败，不虚构联系人。姓名为空可以显示稳定 username，身份仍不按昵称合并。

## 只读、安全和快照要求

Reader 使用 mode=ro、immutable=1、query_only，并关闭扩展、拒绝写入及 ATTACH 授权。表/列只能来自已检查的结构，标识符经过引用。来源的大小、mtime 与 SHA-256 在读取前后比较，变化时作废结果。

immutable 的前提是文件不再发生变化，不能把它用于正在写入的数据库；WAL 还可能含有已提交而未进入主文件的数据。[SQLite URI 文档](https://sqlite.org/uri.html)、[SQLite WAL 文档](https://sqlite.org/wal.html)。

因此当前拒绝 WAL 模式头和所有 -wal/-shm/-journal 侧文件，既不忽略也不删除，更不自动恢复。应由上游流程提供完整离线快照。本阶段不会修改来源来“修复”输入。指纹变化检查不替代可靠的快照获取流程。

拒绝 URI、网络路径、控制字符、路径穿越、输入符号链接及目录候选越界。目标归档库不能是源数据库或元信息文件。解析、结构报告和检测不创建归档库，也不覆盖已有输出。

## 报告、失败和导入

解析报告包含 status、contacts、participants、messages_total、text_messages、failed、skipped_unsupported_count、原因分组、源哈希、Schema 签名、结构报告和 issues。

任意受支持文本错误（非法时间、空内容、错误方向、缺联系人等）会保留精确序号并使整次解析失败，不输出部分 LoadedDocument。group 与登记的已知非文本类型跳过并计数；未知类型失败。

成功标准文档带解析报告元信息，再由 WeChatImporter 调用原 Validator/去重/事务/Report。文本重复不在解析器里删除，由原导入引擎统计。总体 import report 的 messages 是可导入文本数，原库所有行和跳过数在 source_metadata.metadata.parse_report 中。

## 解密边界与扩展

decryptor.py 中 Decryptor.decrypt(path,key) 当前返回 NotImplemented，Parser 不调用它。非明文 SQLite 头可能表示加密或未知格式，不能仅凭头就断言加密。不得把此失败当作可自动解密的承诺。

未来解密应生成新的明文快照，不能覆盖原来源，再交给本 Parser。未来新版本先新增并验证 Schema profile、样例和测试，再注册；不能用最相似的字段集强行解析。

目前全部验收使用模拟数据；尚未测试真实手机版本、超大 Android 数据源或长期并发。当前能力是明确条件下的文件读取与解析框架。
