# 第四阶段：微信数据接入层

此页记录 v0.4.0 的历史接入范围。v0.5.0 新增了条件明确的 Android 明文快照框架，当前能力见 [Android 解析文档](android_parser.md)。

程序版本 0.4.0；数据库结构仍为 2；输出交换格式仍为 chat-exchange 1.0。现有数据库、浏览器、JSON/CSV 导入流程沿用第三阶段。

## 当前支持范围

| 来源 | 检测 | 实际转换/导入 |
|---|---|---|
| wechat-mock 1.0 JSON | 支持 | 支持模拟私聊文字 |
| 含 export.json 的模拟目录 | 支持 | 同上，只读取这个明确文件，不递归扫描 |
| 名为 BackupFiles 的路径 | 路径特征提示 | 未实现，不读取真实备份 |
| 名为 EnMicroMsg.db 的文件 | 路径特征提示 | 未实现，不打开数据库 |
| 普通 JSON、未知版本或其他来源 | 明确拒绝 | 不猜测或自动当作微信数据 |

**当前不支持真实微信数据库读取、加密/解密、图片视频提取、群聊或真实电脑版备份解析。** `--adapter backup/android` 也不会绕过这个限制。

## 先体验

完整解压项目，在项目目录运行：

```powershell
python -m cli wechat detect wechat_mock/export.json
python -m cli wechat convert wechat_mock/export.json --output data/wechat_exchange.json
python -m cli --db data/wechat_mock.db wechat import wechat_mock/export.json
python -m cli --db data/wechat_mock.db wechat import wechat_mock/export.json
python main.py --db data/wechat_mock.db serve --open --port 0
```

样例包含当前账号及两位联系人、两个私聊、五条双向文字消息。首次新增 3 位参与者、2 个私聊和 5 条消息，第二次新增 0 条、duplicated_count=5，报告在 import_logs/。

已转换的标准文件随工程附带于 `wechat_mock/exchange.json`。convert 可不带 output，将标准 JSON 输出到终端；带 output 时必须指定新文件，不覆盖来源或已有文件。detect 和 convert 均不会创建或写入数据库。

源码目录使用 `python -m cli` 或 main.py；安装包使用 `python -m wechat_archive` / wechat-archive。全局 --db 在 wechat 前。import 支持 --strict、--report-dir，以及 auto/mock/backup/android 适配器选择。

## 数据流程

```text
模拟微信数据
  → detector：格式与当前支持状态
  → MockWeChatAdapter / mapper
  → LoadedDocument（chat-exchange 1.0）
  → WeChatImporter（继承 BaseImporter，仅实现 load）
  → 原 Validator / ID 映射 / SHA-256 去重 / 事务 / Report
  → 原 SQLite
  → 原聊天浏览器
```

WeChat Adapter 不直接连接 SQLite，不新增数据库结构，不实现另一套校验、哈希或日志系统。直接微信模拟导入后，再导入其标准 JSON，也会被同一个去重系统跳过。

字段对应、时间单位、发送方向、账号身份隔离和错误边界详见 [映射契约](wechat_mapping.md)。

## 类与接口

目录位于 wechat_archive/wechat_adapter/：

```text
base.py             WeChatAdapter 与 WeChatBackupParser 抽象接口
detector.py         SourceDetection，supported 与类型检测
mapper.py           mock → 标准字段映射
mock_adapter.py     当前可运行适配器
backup_adapter.py   电脑版真实备份接口预留
android_adapter.py  Android 接口预留
importer.py         原 Import Engine 桥接
README.md           模块说明
```

所有可运行适配器 load(path)/export_exchange(path) 返回 LoadedDocument。标准 payload 应通过既有 Validator。检测属于某种来源，并不等同于已实现该来源解析。

未来 WeChatBackupParser 接口定义：

```python
class WeChatBackupParser:
    def detect(path): ...
    def extract_users(self): ...
    def extract_messages(self): ...
    def export_exchange(self): ...  # LoadedDocument
```

当前是抽象接口，不能作为已实现解析器实例化。电脑版和 Android 默认适配器调用时均明确报告未实现。未来的具体解析器应在自身模块处理来源版本、字段及已获得的数据访问能力，最后输出标准格式，再注册相应来源支持状态。

## 错误与报告

wechat import 继续使用原导入报告：成功退出 0，部分成功退出 2，失败退出 1。失败报告也保存在日志目录；映射阶段失败作为 file issue，不能仅凭 failed_count 判断是否成功。

缺少 msgId、错误 isSend、非法 createTime、未知 talker 会给出消息序号。非 text 类型交给原 Validator 形成 message issue，--strict 维持第三阶段的整份拒绝行为。

当前 mock 在内存中转换，仅为接入边界验证；不构成真实微信格式、超大备份或长期并发性能的兼容保证。

## 下一阶段边界

下一阶段单独实现 Android EnMicroMsg.db 的具体解析器，首先明确输入是否已可读取及数据版本；不要在本阶段增加数据库破解或密钥获取。只需让新来源输出 LoadedDocument，再进入已完成的导入管线。
