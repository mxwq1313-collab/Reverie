# 思绪：附件详情、聊天足迹、6.1 Sol 与 MBTI 资源

2026-10-15，分支 `feature/sixu-mbti-ui`。正式版本保持 1.1.0，本次本地构建为“统计与MBTI版”。前一批界面调整见 [界面与 MBTI 验收](SIXU_MBTI_UI.md)。

## 用户可见行为

图片与表情直接展示；语音、视频、普通文件只显示用于点击的入口。文件名、大小、可用性、原副本说明和保存动作都移入点击后的窗口。原聊天正文与附件仍按原样保存；文件说明在详情中阅读，原文件不自动交给模型。

左下角原时间符号改为统计图标，打开“聊天足迹”。可选择当前身份或整个归档；显示消息、会话、活跃日、文字量、13周聊天日历、24小时与星期分布、最长连续活跃天数、夜间消息比例、参与者分布，以及去重附件数量与体积。默认北京时间，夜间定义为22:00–05:59。统计只读当前归档，不扫描原微信目录、不调用Codex；不能代表尚未导入的历史。不同范围或归档版本的结果分别校验，过期结果不写回当前页面。

统计界面按需创建，聚合在后台进行，未变数据直接复用；重复刷新合并为一次待处理请求。相同联系人列表复用原生控件，主题和字号变化继续走已有外观管线。

## GPT-6.1-Sol 核实与默认设置

官方模型文档列出 `gpt-6.1-sol` 可用于符合条件的Codex账号：[模型与可用范围](https://learn.chatgpt.com/docs/models)。这不等于本机已接入，因此另行测试实际插件。

当前插件原配置指向0.153.4，模型目录没有6.1 Sol，直接指定模型未完成。隔离安装OpenAI官方0.162.1，Windows签名为OpenAI OpCo, LLC且有效；其目录包含6.1 Sol。复用插件自己的登录，仅使用程序自建归档，6.1 Sol完成合成口令回复，随后实际调用`archive_overview`、`archive_users`和`archive_messages`，返回正确原文与引用；没有读取真实聊天。

新版随附已验证的官方组件及Code Mode host，附Apache-2.0许可证与文件摘要；不更新全局Codex。首次迁移到新组件时将6.1 Sol选为默认，此后保留用户主动切换的模型。目录、推理程度仍以服务端实际返回为准，首次连接会刷新旧缓存。插件登录资料位置保持。

## MBTI 官方资源边界

用户确认没有题库授权，并选择先接入官方资料和正版测评入口。已加入可在界面打开的官方资料索引、原创简要说明及核验日期，分析请求会实际携带这些资源；没有分发完整官方题目、计分钥匙或仿冒官方测试。

- [Myers & Briggs Foundation：四组偏好](https://www.myersbriggs.org/my-mbti-personality-type/the-mbti-preferences/)
- [官方测评与合资格人员入口](https://www.myersbriggs.org/my-mbti-personality-type/take-the-mbti-instrument/)
- [出版方题目与资料许可](https://www.themyersbriggs.com/en-US/Support/Copyright-and-Permissions)

“官方资料与测评”中另提供授权题库导入。授权题库的格式标识为`sixu-licensed-mbti-bank-v1`，需包含官方HTTPS来源、出版方、授权参考和允许模型处理的明确声明；软件只登记使用者声明，不能鉴定许可证真实性。内容按SHA-256保存在本机，篡改拒绝使用。每次分析最多携带5500字符的题目，明确实际提供题数，不能声称用过未提供题目或给出官方评分。模型资源中的文字作为参考数据，不作为操作指令。

## 流畅度验证

同一份自建Schema3归档，252个会话、1004条消息；读取结果逐项相等，归档SHA-256不变。每项连续3次，以下为本机查询阶段结果：

| 项目 | 修改前 | 修改后 |
| --- | --- | --- |
| 联系人SQL次数 | 759 | 3 |
| 联系人查询中位耗时 | 28.14 ms | 5.30 ms |
| 100条消息与附件查询次数 | 102 | 3 |

联系人与群成员统计按所选身份批量聚合；消息附件一次批量获取，并按原消息与序号排列。没有改变私聊/群聊范围、来源去重或事务写入。计时不包含完整窗口绘制、系统字体首次载入、物理鼠标延迟或模型耗时，不能据此宣称客户端所有操作同幅提速。

## 最终验收

全量发现761项：760通过、0失败、1项既有Windows符号链接权限跳过。按原用例隔离Tk解释器，并在执行断言前完成初始布局，没有扩大原协议等待上限。两项旧断言仍要求显示角色名或将搜索框与范围框放在同一行，已按用户的新界面要求改成原文/角色元数据保留与两行不重叠检查；没有删除原文、引用、选择或边界断言。管理脚本15/15通过。

冻结程序的导入/重复/导出、完整工作台、官方Codex组件、知识模块、群聊/附件/GIF/MBTI/统计专项共五项独立探测全部通过。官方组件检查使用独立未登录目录，登录仅开始后取消，不打开浏览器。真实6.1 Sol验证另行使用插件现有登录和程序自建口令，实际调用archive_overview、archive_users、archive_messages并返回正确原文；没有发送用户真实聊天。

冻结检查发现并修复原本地检索后台任务的时序问题：完成事件与释放忙状态分成两个队列事件，重试回调可能夹在中间而被丢弃。现在处理完成/错误事件时先释放运行计数，再触发回调；过期任务仍只释放计数，不能恢复旧范围结果。最终检索界面6/6、失败重试7/7和新增状态交接回归通过，冻结工作台也通过。

媒体冻结验收首次在过深的项目build路径导出时触发Windows WinError206；同一二进制改用经边界校验的短临时目录后完整通过，原失败回执另存。此项没有修改Windows全局设置，也不声称已消除所有超长路径限制。临时夹具仅含自建文字、GIF与二进制文件，验收回执保存回本项目。普通用户数据不在此测试中读取或改写。

最终EXE SHA-256：`5a8486f577f4749b32ee0e4b91772a4d195ac547d92f43221fefedea2c1316fd`。可运行目录为`build/sixu_delivery/release/Sixu`，其中包含`思绪.exe`、`_internal`、官方组件许可证和摘要。构建输入逐文件摘要与实际源码一致。测试汇总、构建输入和运行回执保存在`build/sixu_delivery/evidence`，不进入Git。

本机思绪设置已将默认模型改为GPT-6.1-Sol，组件指向随包0.162.1；原设置已逐字节备份，归档和存储设置保持。关闭旧版后运行本次新程序生效。后续用户主动切换模型会保留。

尚未验证：其他机器的系统DPI、所有微信版本、完整极大库的物理滚动延迟，以及基于真实聊天的MBTI推断质量。当前官方资源是资料索引与概括说明；完整题库需要用户另行取得授权，本次没有获取或分发。


## 可重建说明

沿用现有Python/Pillow/SDK与PyInstaller环境。官方组件来源为npm包`@openai/codex@0.162.1`及其`0.162.1-win32-x64`平台包；可用`npm install --prefix build/codex-package --ignore-scripts --no-audit --no-fund @openai/codex@0.162.1`隔离获取。将平台vendor下bin中的`codex.exe`、`codex-code-mode-host.exe`及对应许可证放入`build/codex_runtime`，核对OpenAI有效Windows签名与随包runtime_manifest.json摘要。再用`python -m PyInstaller --noconfirm --workpath build/sixu_delivery/build --distpath build/sixu_delivery/release packaging/windows.spec`构建。该过程不下载模型、不复制登录资料、不更改全局Codex。

授权题库JSON需包含`format: sixu-licensed-mbti-bank-v1`、`source_url`、`license.publisher`、`license.reference`、`license.allow_model_processing: true`与`items`。每题包含`id`、`text`及可选`choices`；此处仅描述接口，不提供未经授权的试题。
