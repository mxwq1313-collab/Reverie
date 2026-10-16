# RMFH 备份格式分析器与解析接口

版本 0.5.3；日期 2026-10-13（北京时间）。本阶段范围是 ChatPackage / Index / Media 的文件结构及 RMFH 外壳。用户已确认实际来源 `D:\xwechat_backup`。

## 使用

双击导入窗口入口，选择备份文件夹，点击 **分析 RMFH**。这个操作只使用来源和报告目录，不要求目标归档库有效。结果包含三个文件，窗口可以直接打开摘要。

从完整项目目录运行：

```powershell
python -m cli wechat analyze-backup D:\xwechat_backup --report-dir import_logs
python -m cli wechat rmfh-header "某个消息包的完整文件路径"
```

第二条命令中的路径需替换为实际文件；文件清单中可定位。头分析命令明确拒绝数据库文件和未知/截断外壳。

## 报告约定（1.0）

| 文件 | 内容 |
|---|---|
| structure_report.json | 来源、状态、清单完整性、目录父子关系/层级、文件相对路径/大小/mtime、分类、文件级问题 |
| header_analysis.json | 逐文件头、前缀模式统计、头字段原始值、大小端整数、头尾边界、正文区间、外壳支持/拒绝/非 RMFH/数据库跳过状态 |
| summary.md | 目录模板、分类统计、前缀模式表、头字段偏移表、问题和接口说明 |

报告保存到独立的新目录 `rmfh_analysis_<UTC时间>_<随机标识>`，不覆盖旧报告。禁止输出到原备份内部。JSON/Markdown 使用 UTF-8，写入临时文件并原子替换最终文件。报告是外壳分析，不包含密钥、聊天正文或元信息内容的全文。

分类由路径中的 ChatPackage、Index、Media 名称及已观测元信息文件名决定，不代表已确认文件正文类型。逐文件状态：

- `supported_envelope`：匹配已观测的外壳投影，记录正文区间；编码为 unknown。
- `rejected_envelope`：RMFH 标记存在，头字段/长度/固定尾不符合投影，明确拒绝外壳解析。
- `non_rmfh`：不是 RMFH，内容格式未验证；消息包/索引/backup.attr 出现这种状态列为问题。
- `database_skipped`：.db/.sqlite/.sqlite3 或 EnMicroMsg.db 只记录名称和大小，不打开。

分析状态 `success` 仅表示本次范围内的结构和外壳分析通过，CLI 返回 0；`partial` 有文件级问题但报告已生成，返回 2；`unsupported` 或 `failed` 返回 1。`inventory_complete=false` 表示清单中断，不能把其中统计当作全部文件。所有结果明确 `analysis_only=true`、`content_decoded=false`、`message_count=null`、`import_supported=false`。

## 可用解析接口

模块：`wechat_archive.wechat_adapter.backup`。

```python
from pathlib import Path
from wechat_archive.wechat_adapter.backup import (
    RMFHFormatAnalyzer, RMFHAnalysis, RMFHContainer, PayloadSpan,
    parse_header, parse_container,
)

analyzer = RMFHFormatAnalyzer(Path(r"D:\xwechat_backup"))
result: RMFHAnalysis = analyzer.analyze()
paths = result.save(Path("import_logs"))
overview = result.overview()

# 单文件外壳接口；package 必须是真实文件路径。
container: RMFHContainer = parse_container(package)
span: PayloadSpan = container.payload
assert span.offset == 128
assert span.length == container.bytes - 256
assert span.encoding == "unknown"
```

`analyze_file(path)` 只接受指定来源范围内的普通文件，返回一个文件分析记录。`parse_header(data)` 至少需要 16 字节 RMFH 前缀，只解析可见整数，不声称已确认字段含义。`parse_container(path)` 完整实现当前外壳投影及边界检查；遇到未知格式抛出 UnsupportedWeChatSource。没有用未实现的正文接口代替外壳解析。

`PayloadSpan` 仅给出位置和长度，不读取/解码区间。解密接口仍独立保留于 decryptor.py；本阶段没有推进密钥提取或正文解密。

## 文件头分析

| 偏移 | 长度 | 记录方式 | 含义证据 |
|---|---:|---|---|
| 0 | 4 | RMFH | 可见标记 |
| 4 | 4 | raw_hex、little_endian、big_endian | 未确认 |
| 8 | 2 | 同上 | 未确认 |
| 10 | 2 | 同上 | 未确认 |
| 12 | 4 | 同上 | 未确认 |
| 16–127 | 112 | 头块哈希与非零字节数量 | 未确认，不输出原文 |
| 文件末尾 128 字节的起点 | 4 | RMFT | 可见固定尾标记 |

本备份观测投影为：偏移 8 的 LE 数值为 1、偏移 12 的 LE 数值为 0、偏移 10 的 LE 低字节为 1；不把它们命名为版本、条数、消息类型或算法。外壳要求 128 字节头和固定末尾 128 字节尾，正文区间为 `[128, size-128)`。不会在未知正文中搜索 RMFT，以免把正文中的同名字节误当分隔符。

每个文件最多读取头尾共 256 字节，对大媒体文件也是如此；JSON 记录只公开已识别 RMFH 的前 16 字节，不输出非 RMFH 元信息的内容。头尾哈希不是全文件校验和。

## 实际分析与限制

对用户授权的 D:\xwechat_backup：720 个目录、5719 个文件、14901896197 字节；5715 个 RMFH 外壳均匹配投影，4 个非 RMFH 元信息文件单独记录；14 种前 16 字节模式。ChatPackage 872 个、Index 1250 个、Media 3587 个、元信息 10 个。

这些证据不证明备份完整性、正文编码、加密算法、账号身份或微信版本。目录/文件前后大小、mtime、文件身份一致只是稳定性检查，不是原子文件系统快照或全文件哈希证明。

自动测试只使用自建外壳。实际目录只读分析、数据库/浏览器保持检查及发布验证见 RMFH_ANALYZER_ACCEPTANCE.md。
