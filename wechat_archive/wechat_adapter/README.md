# WeChat Adapter 接入边界

v0.5.0 支持 wechat-mock 1.0，以及符合登记 Schema 的 Android 离线明文 SQLite 快照。电脑版 BackupFiles 仍预留；不解密、不提取图片视频，不承诺所有微信版本兼容。详见项目 docs/android_parser.md。

适配器返回 `LoadedDocument`，payload 为既有 chat-exchange 1.0。`WeChatImporter` 继承 `BaseImporter`，负责来源选择和路径前置检查；标准校验、写库、去重、事务和报告均沿用 v0.3.0。

| 文件 | 职责 |
|---|---|
| base.py | WeChatAdapter 与抽象 WeChatBackupParser 接口 |
| detector.py | 来源整体轮廓检测，实际数据能力标记 |
| mapper.py | mock 字段、方向、时间和稳定身份映射 |
| mock_adapter.py | 当前唯一可运行的微信来源适配器 |
| backup_adapter.py | 电脑版真实备份接口预留，调用时明确报未实现 |
| android_adapter.py、android/ | 登记明文快照解析框架，独立 Reader、Schema、Mapper、Parser |
| importer.py | 适配器选择与既有 Import Engine 桥接 |

Python 用法：

```python
from wechat_archive.wechat_adapter import MockWeChatAdapter, WeChatImporter

loaded = MockWeChatAdapter().load("wechat_mock/export.json")
report = WeChatImporter("data/wechat_mock.db").import_file("wechat_mock/export.json")
```

未来真实解析器的接口为 detect(path)、extract_users()、extract_messages()、export_exchange()。只有最后一步输出 LoadedDocument 后才能进入共享导入层；检测到路径名字不代表已经能解析。

完整命令、范围和字段定义见项目 `docs/wechat_adapter.md` 与 `docs/wechat_mapping.md`。示例输入在 `wechat_mock/export.json`，已转换样例在 `wechat_mock/exchange.json`。
