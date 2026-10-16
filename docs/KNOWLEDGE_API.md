# 知识 API v1.0 与命令行

GUI 与命令行复用同一只读原文来源、范围/引用核验、派生索引和问答服务。可供第二客户端调用的版本化接口通过 stdio JSON-lines 通信，不监听网络。启动时固定归档、查看身份和可选联系人；后续请求不能传文件路径、SQL或扩大范围。

## 命令行

数据库参数位于 knowledge 子命令前，范围和索引参数位于操作前。只接受已有归档，缺失文件不会初始化。以下路径为示例，应换为自己的归档与独立索引。

```powershell
python -m wechat_archive --db C:\Archive\chat.db knowledge --user 1 --peer 2 capabilities
python -m wechat_archive --db C:\Archive\chat.db knowledge --user 1 --peer 2 chunks --limit 10
python -m wechat_archive --db C:\Archive\chat.db knowledge --user 1 --peer 2 --index C:\Archive\knowledge.db build
python -m wechat_archive --db C:\Archive\chat.db knowledge --user 1 --peer 2 --index C:\Archive\knowledge.db search "晶界偏聚能"
python -m wechat_archive --db C:\Archive\chat.db knowledge --user 1 --peer 2 --index C:\Archive\knowledge.db status
```

`build --rebuild` 重新计算全部片段；仅写所选独立索引，索引不能与原库相同或为其硬链接。默认离线字符向量，属于字面检索。`resolve` 接收 `chunks/search` 返回的完整 `reference` JSON，核验后返回对应原文片段。

使用已有本地模型时添加 `--embedding ollama --endpoint http://127.0.0.1:11434 --embedding-model 已安装向量模型名称`，重建/更新后按同配置查询。`ask` 再添加 `--model 已安装回答模型名称`。可用离线字面索引配合本地回答模型；回答 JSON 分别返回推断、结论引用和原文证据。没有证据不调用生成模型。模型名称应使用本机 `/api/tags` 列表的精确名称，不自动下载。

## 第二客户端协议

```powershell
python -m wechat_archive --db C:\Archive\chat.db knowledge --user 1 --peer 2 --index C:\Archive\knowledge.db api
```

每行一个请求，每行一个响应，UTF-8。请求须恰含四个字段，ID 为非负整数或 1–64 字符字符串。请求上限 64 KiB，超限输出错误后退出；响应上限 256 KiB，过大时缩小读取页。API 本身不提供 build、ask、删除、导入或任意插件执行。

```json
{"version":"1.0","id":1,"method":"capabilities","params":{}}
{"version":"1.0","id":2,"method":"chunks","params":{"limit":10}}
{"version":"1.0","id":3,"method":"search","params":{"query":"晶界偏聚能","limit":5,"min_score":0.2}}
```

成功响应含 `version/id/ok/result`，失败含 `version/id/ok/error`；error 使用 validation、conflict、not_found 或 backend。`capabilities` 仅声明当前可用方法：无索引时只有 capabilities/chunks/resolve，启动时配置索引才增加 status/search。它不泄露本机路径；作用域不是远程多用户认证机制。

`chunks` 游标必须原样带到下一页，源内容/范围/处理变化时重新读取第一页。`resolve` 的 params 为 `{"reference":完整ChunkRef对象}`。search/status 只读打开索引，源/模型版本不匹配时拒查，需退出只读 API 后由显式 build 或 GUI 更新。

## 扩展边界

当前开放的是受约束的查询协议和 Python 服务接口，不加载任意第三方代码，不是 MCP/OpenAPI 网络服务。将来有实际远程客户端/多用户需求时，再定义认证、协议兼容和插件生命周期；不能把 capabilities 当成任意来源已受支持。只覆盖已入库私聊文本，群聊/媒体仍按 P1 待办推进。
