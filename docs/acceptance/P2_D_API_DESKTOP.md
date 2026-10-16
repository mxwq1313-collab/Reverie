# P2-D 只读 API、第二客户端及桌面开发包验收

日期：2026-10-14。基线 d24adb1，feature/archive-platform-v0-9；正式版本仍 0.8.0，不打标签或发布 Release。

## 实际实现

KnowledgeAPI v1.0 通过受限 Python 调用或 stdio JSON-lines 使用，启动时固定 Scope；capabilities/chunks/resolve，无索引不声明搜索，显式配置独立索引才增加 search/status。请求恰含 version/id/method/params，拒绝未知方法/参数、版本、路径/SQL/扩大身份范围；有输入与响应预算。索引查询改为 mode=ro/query_only，原文始终只读。

knowledge CLI 是实际第二客户端，提供能力、切片、回查、独立构建/重建、状态、检索、本地 ask 和 API 模式；必须指定已有 --db 与身份，缺库不初始化。GUI、CLI 和 API 复用领域服务；没有任意可执行插件、网络监听或写库 API。详见 [接口说明](../KNOWLEDGE_API.md)。

最终兼容复核新增 Schema1 真实结构测试，发现其没有 source/source_id 列，已改为缺失列返回 None，保持原库字节不变；新增替换文件撤权回归。此前阶段报告的 Schema1 兼容声明以本次实际专项复核为准。问答“模型认为证据不足”测试加强为确认生成调用后返回空结论。

## 测试与开发包证据

新增 8 项 API/CLI、1 项发布诊断和2项旧库/文件替换测试，最终 P2 共47项新测试。覆盖字节不变、能力协商、权限参数、JSON-lines/预算/错误继续、命令行第二客户端、缺库不初始化、新桌面诊断及旧版本读取。全量 596 项，595 通过 / 0 失败 / 1 跳过；耗时 136.399 秒。跳过为已有 Windows 符号链接权限项。 管理15/15通过。

沿用固定SDK1.2.6.1构建新的独立 Windows 开发包。无 Python PATH、清除 PYTHONHOME/PYTHONPATH 的4项 EXE 探测通过：3条自建消息首次/重复/导出均3；工作台125/126条、分页/定位/复制/原库不变；知识1条范围内原文检索、回查、v1.0 API、源变化撤权；官方 Codex initialize/account-read、5动态工具、6模型目录、独立未登录 login start/cancel。参考 [官方 App Server 协议](https://learn.chatgpt.com/docs/app-server)，未浏览器登录或真实推理。EXE SHA-256：2c5579fbe4578b46bfa61534d0bfe89ec06e821fcab1a48dc1f2d36cee6c7709。

构建程序本身返回0；首次日志显示脚本因Windows编码解码失败返回1，构建收据与EXE四项实际运行均成功，随后修正日志显示脚本。源/模型协议验收仍使用自建数据和替身；默认本机Ollama地址不可用，真实模型/同义召回/结论正确率/提示注入抵抗、DPI截图和第二台Windows未验收。没有操作个人库或真实微信来源，没有覆盖旧开发包。

## 开源差距与下一方向

[Open WebUI](https://github.com/open-webui/open-webui) 的混合检索/重排、多格式知识、持久工作区和扩展机制更成熟；[AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) 的桌面模型与知识工作区体验仍领先。ChatArchive 本阶段建立的是受范围控制的聊天原文证据闭环，没有宣称达到这些平台的通用能力或规模。

下一方向调整为：先补 P1 中文短词/深分页与群聊/附件，否则知识覆盖不足；选定真实已有本地模型后，单列同义召回、缺证据拒答和证据归因基准，再按测量决定混合重排与 ANN。持久问答、服务配置保存和 DPI/多机作为后续产品单元。任意插件执行/MCP/OpenAPI网络化仅在实际客户端需求和认证设计明确后推进。
