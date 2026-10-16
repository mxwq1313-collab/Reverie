# 微信 RMFH 备份结构检查

日期：2026-10-13（北京时间）。版本 0.5.2。数据库 Schema 2、chat-exchange 1.0 和原浏览器保持兼容。

## 当前结论

针对用户授权的 `D:\xwechat_backup`，已确认 `backup.attr`、`files/2/<目录>/ChatPackage`、`Index`、`Media` 结构，并检查全部 872 个消息包的文件头/尾。它们符合本次观测到的 RMFH/RMFT 外壳布局。来源手机为 Android，由用户说明；具体微信版本尚未知。

本次检查发现 1 个包含备份的设备目录、1 个批次目录、189 个会话目录、872 个消息包、1250 个索引文件、3587 个媒体文件、10 个元信息文件，共 5719 个文件、14901896197 字节（14.90 GB）。另一个账号目录为空，不影响检查。

**正文导入未完成。** 以上是结构统计，联系人数量及实际消息数量尚未知。本地检查不认证微信版本、消息正文 Schema、备份完整性或加密算法。用户目前没有解密密钥或已解密导出；当前没有经过验证的 RMFH 认证解密器和正文映射，不能产出 `LoadedDocument`。

## 窗口使用

完整解压后双击 `导入数据.cmd`。保留“自动识别”，或选“微信 RMFH 备份（结构检查）”，来源选择 `D:\xwechat_backup`，点击“预览检查”。

窗口会显示结构统计、“实际消息数量：尚未解析”、缺失条件及检查报告路径。已识别但不可解码的来源会禁用“开始导入”和查看聊天按钮；更换来源后可以正常导入已支持 JSON/CSV/模拟/Android 明文数据。

若未预览而直接点击导入，原 Import Engine 保存失败报告，错误码 `backup_content_unavailable`，`source_metadata.backup_inspection` 包含结构报告；不初始化或修改归档库。未知或损坏外壳明确拒绝，不尝试猜测聊天字段。

预览会在项目 `import_logs/` 保存结构检查报告，不写数据库。报告目录和归档目标都不能放入原备份。报告不包含密钥、正文或联系人姓名。模拟外壳示例在 `examples/rmfh_backup`，不是可导入的聊天样例。

## 命令入口

```powershell
python -m cli wechat inspect-backup D:\xwechat_backup
python -m cli wechat inspect-backup D:\xwechat_backup --report-dir import_logs
python -m cli --db data/chat.db wechat import D:\xwechat_backup --adapter backup
```

`inspect-backup` 返回 0 只表示结构已识别，必须同时读取 `import_supported`（当前为 false）；未知/损坏返回 1。`wechat import` 当前返回 1 并保存失败报告，实际导入消息为 0。禁止把检查退出码当作聊天导入成功。

## 已观测的外壳投影

只检查 `RMFH` 开头、前 16 字节的已观测整数形状、128 字节头、文件末尾固定 128 字节 `RMFT` 尾，以及二者之间的长度。不在密文里搜索分隔符，不把头中的未验证字段解释成账号身份或消息数量。消息包外壳通过检查不证明内文可读取。

检查普通文件使用 `rb`；不会打开/覆盖数据库。拒绝网络/URI/路径穿越、符号链接、Windows 目录联接、异常深度、过量文件、未知头尾及 `pkg.lock`。检查前后比对相关文件/目录的大小、mtime 和文件身份，检测到变化即拒绝；这种检查不等于文件系统原子快照，也不提供所有字节未变化的密码学证明。

## 架构和后续工作

```text
RMFH 目录 → BackupAdapter → RMFHBackupParser.inspect → BackupInspection
                                                  → 当前正文明确失败
未来：认证解密 → 已登记的消息 Schema → LoadedDocument → 原 Import Engine → SQLite
```

后续必须先取得合法可用的本备份密钥或可读导出，验证密钥来源、算法、参数和认证标签，再用独立模拟样本与用户授权的有限真实样本确认正文 Schema、账号、发送方向及时间单位。不能将一个 Android 版本的规则推给所有微信版本；也不能把 RMFH 备份密钥当作 Android SQLite 数据库密钥。当前没有执行手机 root、ADB 连接、进程注入或密钥提取。

## 参考与证据边界

外壳实现以本机文件的直接观测为依据。公开参考 [ChatImportKit](https://github.com/Cjh-y/ChatImportKit) 也区分了目录/容器识别与正文解密，且公开说明其正文解密尚未完成；其 [RMFH 文档](https://github.com/Cjh-y/ChatImportKit/blob/main/docs/RMFH.md) 和本次文件中观测到的 128 字节头尾存在描述差异，未把其中的密钥推断或字段含义当作已验证事实。

本次验收证据见 `BACKUP_INSPECTION_20261013.json` 和 `BACKUP_ADAPTER_ACCEPTANCE.md`。自动测试仅使用自建外壳，真实备份仅做用户授权的手动只读结构检查；未解析或保存任何聊天正文。
