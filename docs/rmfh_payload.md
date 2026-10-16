# RMFH 元信息与载荷阶段（0.5.4）

日期：2026-10-13（北京时间）。当前范围：只读元信息结构探测、有限载荷采样、独立解码接口和解码可行性报告。来源仍为用户确认的 D:\xwechat_backup。

## 使用

导入窗口选择备份目录后点击 **探测载荷**。这个操作不需要有效的目标归档库。命令方式从项目目录执行：

```powershell
python -m cli wechat study-payload D:\xwechat_backup --report-dir import_logs
```

可选 `--samples-per-pattern` 为 1–4（默认 2），`--sample-bytes` 为 1–65536（默认 65536），`--total-bytes` 为 1–16777216（默认 4194304）。上限不合法时明确失败。

目录/头分析保持每文件最多 256 字节；每个选定容器另检查 256 字节头尾。上述正文预算只统计元信息和正文区间的读取，不能把它理解为包含目录/头分析的所有 I/O。

## 已得到的真实证据

四个非 RMFH 元信息文件：

| 文件 | 大小 | 顶层 wire 字段 | 证据 |
|---|---:|---:|---|
| alt_name.dat | 67 | 1 | wire 投影完整读完 |
| detail.dat | 6 | 1 | 同上 |
| pkg_info.dat | 233 | 9 | 同上 |
| roam_device_info.dat | 236 | 6 | 同上 |

均为**结构兼容**，不是已验证的 .proto/微信字段映射。字段名称、业务含义、账号绑定和是否包含可用密钥尚未确认。带 wxroam 前缀的字段只记录形状与长度，其密钥角色为 unverified；没有将其当作密钥使用。

载荷按 14 种前缀模式各选两个较小消息包，获得 28 个 ChatPackage、28 个同目录同名 Index 候选。47 个正文完整读取，9 个按上限截取；元信息和正文总读取 822234 字节，低于 4 MiB。媒体正文未采样，数据库文件未打开。

56 个样本均为 unknown_encoding；没有确认可用的真实正文解码方法，没有恢复真实文本。熵、打印字符比例、压缩签名候选、wire 探测和前缀摘要仅为证据，不能单独证明加密或具体算法。取样不能推广为所有文件均不可解码。

## 输出约定（1.0）

- `metadata_report.json`：每个元信息文件的读取范围、完整性、字段号/wire 类型、无语义映射的数值、字节摘要、字符串形状与嵌套结构候选。
- `payload_samples.json`：模式与文件选择、同名配对候选、正文位置、完整/截取标记、字节分布、头尾未知区域形状、wire/文本/压缩证据和解码状态。
- `decoder_assessment.json`：总体覆盖、预算、解码条件及问题。
- `summary.md`：中文汇总。

报告输出到新的 rmfh_payload_<UTC时间>_<随机标识> 目录，UTF-8 写入，禁止位于原备份内部。不会保存原始采样、字符串全文、密钥或聊天正文。哈希区分采样摘要与全文件校验；不会冒充全文件哈希。

## 解码 API

```python
from wechat_archive.wechat_adapter.backup import RMFHPayloadStudy, DecoderRegistry

result = RMFHPayloadStudy(source, samples_per_pattern=2,
                         sample_bytes=65536, total_bytes=4194304).analyze()
paths = result.save(output_directory)

decoded = DecoderRegistry().decode(sample_bytes, complete=True)
# decoded.summary() 可记录；decoded.data 是内部 bytes，默认不输出到报告。
```

默认注册 gzip、zlib、bzip2 和 xz，只接受完整、单段、无尾随字节的流，检查结束状态/格式校验，最大输出 1 MiB；xz 解码内存上限 64 MiB。不使用无界 flush 或解压函数。

扩展后端必须继承 PayloadDecoder，通过 `register(profile, decoder)` 明确登记。声明 requires_key=True 时，没有密钥返回 needs_key，返回未认证结果则 authentication_failed。异常被转换为通用错误，不向报告泄露密钥。生产尚未注册任何微信加密格式；认证路径测试仅用自建 HMAC 样例，不代表微信算法。

状态包括 decoded、unknown_encoding、unsupported_encoding、needs_key、needs_complete_sample、invalid_stream、unsupported_stream_layout、output_limit、authentication_failed、decoder_failed。unknown_encoding 不能自动变成 needs_key；带疑似密钥标识也不代表密钥可用。

## wire 探测边界

支持 wire 0/1/2/5：varint、64 位块、长度分隔块、32 位块。最大数据 64 KiB、默认累计 256 字段、嵌套深度 2。拒绝 group、截断、非法字段号、溢出、超限和当前投影不接受的非最短 varint。未读取完整样本时不认证整段 wire 结构。LEN 可能是字符串、bytes、子消息或 packed 字段，不能仅凭可读字符串确定业务含义。

## 阶段状态与后续条件

分析状态 success 表示有限分析完成，CLI 0；partial 表示部分采样/来源问题，CLI 2；failed 表示分析失败，CLI 1。它们均不表示真实消息导入成功。本阶段成功交付分析与明确条件，真实聊天恢复仍待后续。

下一步需要具体微信版本/格式证据；如确认涉及加密，需适用密钥、参数和认证方法；随后确认消息 Schema、账号、方向与时间。当前没有手机操作、密钥提取、算法猜测、Android 数据库解析、媒体正文导入或 SQLite 设计变更。

## 依据

wire 投影依据 [Protobuf 官方编码说明](https://protobuf.dev/programming-guides/encoding/)；字段名和声明类型需 Schema 才能确定。压缩流边界及限量 API 依据 Python 3.10 官方 [zlib](https://docs.python.org/3.10/library/zlib.html)、[bz2](https://docs.python.org/3.10/library/bz2.html)、[lzma](https://docs.python.org/3.10/library/lzma.html) 文档。实际来源的格式结论仅来自本机观测与当前探测，不沿用未经验证的外部微信算法推断。
