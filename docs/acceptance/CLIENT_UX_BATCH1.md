# 第一批客户端体验逐项验收

2026-10-14，初始基线 fe8ab50，feature/archive-platform-v0-9，正式版本保持0.8.0。

## U1：按归档模式显示读取能力

来源页依据已打开归档的实际版本显示基础单批限制或扩展快照分批能力，并提供就地创建升级副本入口；只读获取能力，不自动迁移用户库。

验收 45 项，45 通过、0 跳过、0失败。命令：python -B -X utf8 -m unittest discover -s tests -p test_client_experience.py -v；python -B -X utf8 -m unittest discover -s tests -p test_workbench.py -v；python -B -X utf8 -m unittest discover -s tests -p test_codex_workflow_ui.py -v。

已验证基础/扩展切换、升级入口、原库字节保留、无归档不创建以及读取异常时禁用升级并显示能力未确认。

## U2：搜索结果与原会话往返

上下文跳转前保存实际搜索范围、日期、关键词、已加载结果与像素阅读位置；新增返回结果按钮。切身份、切库、新搜索或归档文件/WAL变化使旧现场失效。

验收 9 项，9 通过、0 跳过、0失败。命令：python -B -X utf8 -m unittest discover -s tests -p test_client_experience.py -v。

验证筛选/结果/原联系人恢复、超过100条加载后的像素位置、源修改失效、新搜索与主动切会话清除现场，以及上下文失败保留原结果。

## U3：流式回答保持阅读与选区

回答显示改为只替换变化的文本片段，保留未变化正文、选区和引用；仅在原本停在底部时跟随生成，离开底部可点击回到最新。

验收 19 项，19 通过、0 跳过、0失败。命令：python -B -X utf8 -m unittest discover -s tests -p test_client_streaming.py -v；python -B -X utf8 -m unittest discover -s tests -p test_codex_workflow_ui.py -v。

验证十次连续增量后的顶部文本锚点与选区、底部跟随、回到最新、最终角色更新、Unicode与引用保留，以及新对话清空。

## U4：失败问题保留与受范围约束的重试

Codex提供取回编辑和重新发送，失败/停止保留部分回答，重新连接保留失败问题但不自动发送。本地检索/问答提供重试和更新索引后重试；重试绑定原归档、范围、内容身份及模型设置。

验收 32 项，32 通过、0 跳过、0失败。命令：python -B -X utf8 -m unittest discover -s tests -p test_client_retry.py -v；python -B -X utf8 -m unittest discover -s tests -p test_client_streaming.py -v；python -B -X utf8 -m unittest discover -s tests -p test_codex_workflow_ui.py -v；python -B -X utf8 -m unittest discover -s tests -p test_knowledge_ui.py -v。

验证假服务发送失败后编辑/成功重试、源变化拒试、部分回答保留、重连不发送；本地缺索引更新后续查、模型服务失败恢复、切范围撤销以及无证据不当作网络失败。

## U5：导出完成后直接打开结果

成功结果提供打开阅读首页、打开文件夹和复制路径；单会话TXT打开该文件，多会话TXT打开目录。新导出开始/校验失败不沿用旧成功结果，输出丢失和系统启动失败明确显示。

验收 27 项，27 通过、0 跳过、0失败。命令：python -B -X utf8 -m unittest discover -s tests -p test_client_export.py -v；python -B -X utf8 -m unittest discover -s tests -p test_readable_export.py -v。

验证HTML-only/双格式/单TXT/多TXT、目录复制、失败后按钮禁用、输出删除和系统启动失败；原归档字节不变。自动验收替换系统启动函数，没有打开个人文件。

## U6：基础键盘导航与可见焦点

会话列表新增单个可聚焦入口、焦点边框、↑↓/Home/End选择及Enter打开；聊天页Ctrl+F搜索、Ctrl+Shift+F全会话搜索、Alt+←返回结果，Esc优先返回或清除筛选。助手输入不被聊天快捷键拦截。

验收 40 项，40 通过、0 跳过、0失败。命令：python -B -X utf8 -m unittest discover -s tests -p test_client_keyboard.py -v；python -B -X utf8 -m unittest discover -s tests -p test_client_experience.py -v；python -B -X utf8 -m unittest discover -s tests -p test_workbench.py -v。

使用Tk真实事件绑定验证↑↓/Enter、Ctrl+F/全局搜索、Alt+←/Esc、空列表、Home/End边界及助手草稿不受影响。几何检查不能替代真实系统DPI和屏幕阅读器验收。

## 最终综合验收

全量 628 项，627 通过、1 原有 Windows 符号链接权限跳过、0失败；管理 15/15 通过。

命令：`python -B -X utf8 -m unittest discover -s tests -v` 与 `python -B -X utf8 -m unittest discover -s tools/tests -v`。全量新增32项测试（六项体验31项、运行诊断1项）；全部使用自建数据和假服务。

补充搜索分页保护：源文件或WAL在分页间变化时拒绝追加，查询期间变化时拒绝新结果，返回旧搜索必须与原文件身份一致。相关回归已纳入最终全量。

| 单元 | 本地提交 | 摘要 |
|---|---|---|
| U1 | cdb2414 | feat: 按归档模式显示读取能力并提供就地升级入口 |
| U2 | e6450bd | feat: 支持搜索结果与原会话上下文往返并保留位置 |
| U3 | f893bfb | fix: 流式回答保留阅读位置和选区并支持回到最新 |
| U4 | 2a16ab7 | feat: 保留失败问题并提供范围绑定的助手重试操作 |
| U5 | 68f3fef | feat: 为成功导出增加直接打开和复制路径操作 |
| U6 | a80d358 | feat: 增加会话键盘选择和搜索返回快捷键 |

PyInstaller使用既有固定环境及SDK1.2.6.1；EXE SHA-256：`cb3967dc6c96e90e5942526c363cf784969712604240b67f2dc1da8274afbe22`。

四项EXE在仅保留System32 PATH、移除PYTHONHOME/PYTHONPATH且隔离数据目录的条件下通过：

- 导入/重复/可读导出：3新增、3重复、3导出。
- 工作台：125/126条分页、上下文、原文复制及六项客户端行为；能力副本、搜索往返、流式阅读/选区、失败问题/索引恢复、导出动作和键盘入口。
- 知识：离线检索、原文回查、API以及来源变化撤权。
- Codex：独立未登录官方组件握手、5工具、模型目录和登录开始/取消，未打开浏览器或发真实推理。

导出打开验收替换系统启动函数，核对传入对象，不证明特定第三方默认浏览器或文本编辑器兼容。流式阅读与失败恢复使用自建通知/假模型；未发送个人聊天。

## 验证边界与后续

真实微信完整历史、真实账号登录及模型质量、系统DPI/跨屏、第二台Windows仍待独立验收。真实服务不可达时请求只能在服务返回后完成取消。大数据响应优化、阅读锚点、助手侧栏/持久历史、富消息均为第二/三批，第一批未将其计为完成。

初次沙箱GUI测试停滞，终止该次尝试后在正常本机权限验收。开发过程的测试分组/路径导入/单数测试收据错误已修正，原尝试日志保留；最终上述结果以最后收据为准。部分源代码在全量中补齐分页保护后，旧尝试已终止并按最终源码重跑。没有绕过Git隐私或推送钩子。
