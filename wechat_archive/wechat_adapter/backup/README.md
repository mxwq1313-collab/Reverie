# RMFH 备份边界（0.5.4）

本模块只实现已观测 RMFH 外壳和备份目录的只读结构检查。聊天正文解密、消息字段映射和真实聊天导入仍未完成。

- `reader.py`：本机路径、链接/联接保护，只读头尾、128 字节 RMFH/RMFT 外壳投影和读取期间变化检测。
- `parser.py`：有限层级发现设备目录，枚举消息包/索引/媒体文件，输出 `BackupInspection`；原备份禁止保存报告或归档库。
- `decryptor.py`：独立的认证解密接口；默认实现明确抛出 `NotImplementedError`。
- `analyzer.py`：逐文件/目录清单、所有分类的文件头分析、结构/头分析 JSON 和中文摘要。parse_header 按偏移记录原始值；parse_container 返回外壳及 PayloadSpan。分析不依赖 Android 或 SQLite。
- `wire_probe.py`：有界 wire 类型 0/1/2/5 投影；支持结构兼容探测，不代表已知消息 Schema。字符串仅记录形状和摘要。
- `bounded_reader.py`：范围、单文件上限、总读取预算与只读变化保护。
- `payload_decoder.py`：注册式有界解码，默认仅压缩格式；需要密钥的后端必须认证。生产没有微信加密投影。
- `payload_study.py`：元信息/载荷取样和解码评估，输出四份报告，不生成 LoadedDocument。
- `RMFHBackupParser.export_exchange()`：当前明确抛出 `BackupSourceError`，没有生成可写库的 `LoadedDocument`。

不能把文件数量当作消息数量，不能从目录散列、昵称、文件名时间范围推断发送者/接收者。不能仅凭高熵数据宣称已确认加密算法。只有未来完成认证解密及登记消息 Schema 后才可接入原 Import Engine。

完整接口与报告约定见项目 docs/rmfh_analyzer.md。窗口“分析 RMFH”和 CLI analyze-backup 使用独立分析器；原 inspect 及 Import Engine 拒绝边界保持兼容。
