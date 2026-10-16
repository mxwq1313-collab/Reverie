# P0 B 消息来源能力与引用契约验收

日期：2026-10-14（Asia/Shanghai）。基线5287c8a，分支feature/archive-platform-v0-9。应用0.8.0、Schema2及chat-exchange1.0保持；当前为源码阶段。

## 结果

本阶段源码验收通过：新增MessageRecord/SourceRef/MediaRef/ParseStatus/SourceCapabilities/ImportBatch/MessageRef，旧Message、LoadedDocument、WeChatAdapter.load和CLI保留。类型设计包含text/image/video/audio/file/location/system，但实际来源、Validator与SQLite仍只支持已登记私聊文本，未将类型设计标成媒体/群聊功能完成。

各Adapter声明准确能力：mock标为synthetic，Android仅登记离线明文Schema，external仅固定来源私聊文本且有复合身份，backup仅结构inspection、不声明正文。导入报告输出主机能力描述，交换JSON的任意元信息不能代替来源能力声明。

旧Adapter可通过iter_batches输出一个明确final的单批领域对象，包含原文/UTC/来源和稳定内容摘要；预算超限和任何恢复游标明确拒绝。此包装仍先调用旧load，不是有界流式，也不宣称断点/完整获取已经实现。

Codex归档工具每条消息新增结构化reference，保留原citation与五个动态工具接口。引用绑定本机归档文件身份、消息ID及实际内容摘要；展开重新核对归档、会话范围、消息是否存在及修改版本。引用不暴露本机路径，长文片段引用按完整原文计算，不能用截断文本替代消息版本。

## 验证证据

| 项目 | 实测 |
|---|---|
| 基线独立快照 | 172个Git跟踪文件逐文件复制，起始仓库干净 |
| 新契约回归 | 31/31通过：原文/UTC、类型/能力、未知拒绝、媒体路径/缺失/证据、单批预算与恢复拒绝、引用跨库/越权/删改/替换失效 |
| 既有Codex模块 | 31/31通过：假服务器连接/登录/工具/流式/停止/切范围/撤权，未向真实模型发送聊天 |
| 完整业务回归 | 488运行，487通过，0失败/错误，1原有权限跳过，主体75.140秒 |
| 跳过 | Windows symlink privilege unavailable；不更改权限 |
| 原5万条自建文本基准 | 首次2.501009秒，重复0.696624秒；不外推附件/其他机器 |

命令：`python -B -X utf8 -m unittest discover -s tests -v`；新test_contracts与test_agent先单独执行。夹具由既有prepare_fixtures恢复。日志位于当前工作区work/archive_step2/evidence；个人聊天、来源库和账号不参与。没有重建EXE，也未验证真实账号授权/模型、来源获取或其他机器。

## 与开源能力的差距及下一步

[WechatExporter](https://github.com/BlueMatthew/WechatExporter)的资料涉及多类型/群名称与离线导出；本阶段建立这些类型的契约和可失效引用，但实际持久化、显示与导出仍有差距。引用安全测试属于本项目证据，不据此宣称整体优于该项目。RMFH仅inspection的声明与[ChatImportKit](https://github.com/Cjh-y/ChatImportKit)当前说明中的正文研究边界一致，后者不是高星成熟正文解析器。

下一阶段P0-C调整为“显式新目标副本迁移与各读取入口兼容”：默认继续创建/使用Schema2，不在打开现库时自动升到富消息Schema；先证明新副本的旧ID、原文、来源、历史重复、外键、导出及失败恢复。随后P0-D验证来源快照/游标，P1优先将当前范围、连接/登录/回答状态和引用回查契约接入Codex界面，继续完善功能/UI。

Codex客户端依据[官方App Server文档](https://learn.chatgpt.com/docs/app-server)，本阶段不改变官方登录流程或五个工具协议。新引用是本应用返回的数据，不是OpenAI接口已经新增功能的声明。

## 限制

Schema2没有归档UUID或持久revision；引用当前绑定本机路径/文件身份的摘要，复制到其他位置视为另一个归档。后续Schema3可增加持久归档身份。legacy单批包装不解决旧load的整文件内存开销；新的领域类型不会绕过旧Validator。消息删改或原文件替换后引用明确失效，不能恢复旧文本或历史被合并事件。
