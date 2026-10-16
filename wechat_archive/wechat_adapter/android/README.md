# Android WeChat Parser

v0.5.0 的具体读取框架。只接受已解密、停止写入的本机 SQLite 快照及 android_source.json，按登记 Schema 解析私聊文本，输出 LoadedDocument。

| 模块 | 职责 |
|---|---|
| detector.py | 有限层级目录/文件检测、合法路径与元信息检查 |
| database_reader.py | mode=ro、immutable、query_only 和写入授权拒绝；表/字段报告 |
| schema.py、profiles/ | 登记映射、字段及类型校验，未知 profile 拒绝 |
| extractor.py | 仅按映射读取指定表列 |
| mapper.py | 身份、方向、时间和文本转换 |
| parser.py | 检测→只读结构→提取→映射→标准文档/解析报告 |
| decryptor.py | 单独解密接口，当前返回 NotImplemented |

```python
from wechat_archive.wechat_adapter.android import AndroidWeChatParser
from wechat_archive.wechat_adapter import WeChatImporter

result = AndroidWeChatParser("android_mock").parse()
loaded = result.document  # 失败时为 None；先查看 result.report
report = WeChatImporter("data/android_demo.db", adapter="android").import_file("android_mock")
```

只支持一个明确登记的字段投影，不宣称兼容所有微信版本。任何受支持文本数据错误都使解析失败，不给出可导入文档；已知媒体或群聊记录按跳过统计，未知消息类型失败。

输入源及归档目标不能相同，解析/导出不覆盖来源。WAL/SHM/journal 侧文件拒绝，来源改变则结果作废。测试和工程样例全部是自行构造的 SQLite，未使用真实聊天。

完整元信息、支持范围、命令和映射规则见项目 docs/android_parser.md。
