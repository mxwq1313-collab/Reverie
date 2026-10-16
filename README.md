# 思绪 · 本地聊天归档

<!-- SIXU_2_2_1_BEGIN -->
## 思绪 2.2.1 · 左下角随机回忆与界面精简 · 2026-10-16

移除“正在检测电脑微信账号……”浮动提示，检测进度继续由底部状态栏与进度条提供。随机回忆从工具标签中移出，改为左下角交错箭头符号入口，点击打开紧凑的非模态小窗口；时光胶囊与统计保留各自独立图标。

小窗口突出会话范围、打捞操作与回忆正文，日期/关键词筛选默认收起，回看/复制/保存/原文定位按用途分组。关闭再打开保留当前回看记录；归档或会话变化时撤销旧回忆。支持键盘、悬停说明、浅色/深色与大字号，避免底部按钮被正文挤出。

验证：完整业务回归888项，其中1项旧版本断言已修正，受影响模块13/13复验通过；管理19/19通过；本轮专项6/6，最终EXE五项入口通过，原生截图检查回调错误0。使用自建归档，不读取真实微信或发送模型请求。发布目标为[mxwq1313-collab/Reverie](https://github.com/mxwq1313-collab/Reverie)，正式版本与资产以v2.2.1 Release及发行清单为准。详见[2.2.1发布与验收](docs/SIXU_2_2_1_RELEASE.md)。
<!-- SIXU_2_2_1_END -->

<!-- SIXU_2_2_BEGIN -->
## 思绪 2.2.0 · 合并图片、微信账号与缩放响应 · 2026-10-16

合并转发图片复用普通聊天的缩略图、预览、GIF播放和另存；通过明确的摘要、大小和图像格式绑定资源。重新读取可采集本账号本地缓存的转发子图片，重读保持去重；既有归档可复用相同的已导入图片。缺失资源明确显示未取得。

工具区仅保留归档管理、语义检索、随机回忆、文字小工坊四个直接标签；删除概览标签、工具页头返回跳转和页面切换浮动提示。时光胶囊仍在左下角。账号下拉优先显示微信昵称及微信号，保持实际账号绑定；未连接时可使用精确匹配的本人归档昵称并标注，不能把其他联系人的昵称当作账号本人。

连续缩放时保持当前正文排版，尺寸稳定后统一调整；取消嵌套布局事件处理并恢复可见区任务。最终三组可见窗口对照最长间隔341.024→71.911ms；3轮最大化/还原/最小化通过，回调错误0。结果适用于本机该场景。

验证：追加账号和最后缩放调整前，完整业务872/872、管理19/19通过；追加后受影响模块分轮137项全部通过，最终EXE五项独立入口通过。当前集合882项，未把未重跑的882项声称为全量结果。截图两张图片的原资源仍缺失；真实账号检测未取得在线本人资料，当前归档精确匹配出一个本人昵称，另一个待连接核验。

GitHub目标为用户已创建的公开仓库[mxwq1313-collab/Reverie](https://github.com/mxwq1313-collab/Reverie)。发布流程核对源码树，再由Windows工作流验证并生成v2.2.0 Release；实际提交、标签和资产状态保存在发行清单。详见[2.2.0发布与验收](docs/SIXU_2_2_RELEASE.md)。
<!-- SIXU_2_2_END -->

<!-- SIXU_2_1_1_BEGIN -->
## 思绪 2.1.1 · 合并消息与导航调整 · 2026-10-16

按用户授权发布2.1.1。合并转发默认收起为聊天记录卡片，可原位展开普通消息、选择/复制/再次收起；实际头像及占位改为圆角正方形；时光胶囊移至左下角统计上方，随机回忆和文字小工坊改为同级工具标签；使用用户新提供的猫咪Logo。

状态：已实现并验证。完整回归860项：860通过、0失败、0跳过；后续压力检查修复文本同步测量占用问题，末次2.1.1专项17/17、工作台18/18、媒体13/13、大归档UI12/12，管理15/15，最终EXE五项入口通过。截图群聊10条合并消息只读展开与收起通过，原归档摘要不变。展开卡片30条内部长消息、24次缩放/90帧采样，未采到大块黑区、回调错误0。GitHub提交仍待用户提供目标仓库地址，未擅自设置远程或上传。

本地程序与压缩包位于build/r211，详情见[2.1.1发布与验收](docs/SIXU_2_1_1_RELEASE.md)。
<!-- SIXU_2_1_1_END -->

<!-- SIXU_2_1_BEGIN -->
## 思绪 2.1.0 · 回忆工具与交互界面 · 2026-10-16

按用户授权发布2.1.0。优化Codex回答排版、引用与流式定位，归档管理/检索/小窗口按工作顺序重排，导入与分析报告移入设置；三项小工具各有独立页面、筛选/分页/回看/文本整理及复制保存。会话卡片取消最近消息预览，统计简化，支持精确绑定的本地微信圆形头像。用户提供的猫咪图应用到品牌、窗口和EXE图标。

连续缩放合并布局，只精确排版可见消息并复用画布；本轮最终24次缩放、90帧采样，未采到大块黑区，Tk错误0。相同失败私聊185,566条离线封存、隔离导入与重读去重通过，原归档主文件摘要不变；本地资源缺失仍如实标记。

状态：已实现并验证。全量业务 845 项：844 通过、0 失败、1 项既有 Windows 符号链接权限跳过；其中包含 2.1 专项 13/13、工作台专项 18/18，另有管理 15/15。最终 EXE 五项独立入口通过，Windows 文件及产品版本均为 2.1.0，七档 ICO 图像与用户提供原图的技术转换结果逐一匹配。 发布运行文件位于build/r21/release/Sixu，压缩包与验收在build/r21；源码和公开验收进入本地Git，未推送。详见[2.1.0发布与验收](docs/SIXU_2_1_RELEASE.md)。
<!-- SIXU_2_1_END -->

<!-- SIXU_2_0_BEGIN -->
## 思绪 2.0.0 · 全量归档与表情补全 · 2026-10-16

按用户授权发布2.0.0。电脑微信入口默认读取所选会话全部本地记录；可选择500、5000、5万、10万或100万条，全量快照不再受固定条数选择限制。扩展归档每批最多2000条，并保留8MiB正文与64MiB批文件预算，后台显示读取与保存数量，可取消后续批次并从封存目录恢复。基础格式的严格边界保持，不把未知格式强行解释。

新增旧归档表情补全，从添加页高级设置或缺失附件详情进入；保留正文、来源ID和原有可用附件，只补全缺失资源。取消整次导入共用的50次/90秒CDN预算，改成单资源大小、像素、时长限制，重复失败不反复请求；仍仅允许已声明官方地址且摘要、格式校验通过。透明GIF首帧改用可见帧作缩略图。

状态：已实现并验证。全量801项：800通过、0失败、1项原有Windows符号链接权限跳过；新增导入3项与表情6项均通过，管理15/15，最终EXE五项独立入口及2.0补全显示检查全部通过。用户单独授权CDN验证后，真实隔离副本补全171条，加原有7条共178/180可用，余2条无资源URL；3种真实资源Tk显示通过。原归档摘要未变，未向模型发送真实聊天。

验收、用法与限制见[2.0.0发布记录](docs/SIXU_2_0_RELEASE.md)。
<!-- SIXU_2_0_END -->

<!-- SIXU_LARGE_ARCHIVE_BEGIN -->
## 大归档响应与轻量界面 · 2026-10-15

启动/打开归档、搜索和会话切换改为可替换后台读取；归档文件与WAL未变化时复用完整校验和有限内存查询结果，变化后重新验证。消息和联系人小批次绘制与清理，离屏消息收起内部控件，连续缩放合并布局并复用图形；图片只按可见区域加载，解码去重、排队和缓存有界，空闲停轮询。保留只读、身份范围和版本撤销约束，修复富媒体深分页偏移被附件查询覆盖的问题。

减少圆角框，以浅底边阴影、细线和导航侧标区分层次；去掉右上角Codex入口框及主界面内部文件名，必要范围说明改称当前归档。补充按压、悬停、可取消导航反馈并尊重减少动画设置。

20万条自建消息、50会话：读取序列完整校验23→1；重复搜索读取938.185→0.832ms，重复会话页44.744→0.836ms。数据范围为只读访问阶段，首次扫描仍需要时间；真实界面另做事件循环与缩放验证。

状态：已实现并验证。全量792项：791通过、0失败、1项原有Windows符号链接权限跳过；末次新增专项12/12，管理15/15，最终EXE五项独立检查通过。正式版本保持1.1.0，未推送。详见 [大归档响应验收](docs/SIXU_LARGE_ARCHIVE.md)。
<!-- SIXU_LARGE_ARCHIVE_END -->

<!-- SIXU_CLIENT_POLISH_BEGIN -->
## 全局控件与流畅度 · 2026-10-15

统一按钮圆角和输入框/搜索/下拉框的填充、边界与内边距；搜索样式覆盖来源、帮助、历史及范围弹窗。原生下拉打开时同步当前主题和字体，并保留键盘及既有回调。删除恢复默认强度按钮及对应操作，保持模型卡片标题居中。

联系人切换重绘252→2张，松绿主题六次自建测量的控件操作中位126.373→0.788ms；高度变化跳过不必要摘要计算，滚轮延迟任务合并并释放，不重复注册销毁回调。测量仅指控件阶段，不代表整个客户端或模型延迟。

另修复诊断入口拒绝已有目录后仍新增错误报告的问题，五种入口均验证保留原有内容。

状态：已实现并验证。全量发现780项：779通过，0失败，1项跳过；管理15/15，最终EXE五项独立检查通过。正式版本保持1.1.0，未推送。详见 [控件与流畅度验收](docs/SIXU_CLIENT_POLISH.md)。
<!-- SIXU_CLIENT_POLISH_END -->

<!-- SIXU_LIGHT_CONTROLS_BEGIN -->
## 轻量参数浮层与搜索框 · 2026-10-15

按截图将模型/努力程度调整为紧凑无标题栏圆角浮层，使用模型菜单、有效强度滑杆、快速开关与恢复默认；外部点击/Esc收起。模型与请求语义保持。联系人和消息搜索统一浅色填充框与占位文字，输入后Enter搜索；移除重复搜索按钮。身份/说明、计数/范围行统一高度，对齐两个搜索与列表。下拉箭头改成轻量细线V形，聊天标题和逐条时间去除常驻UTC+08:00显示，仍按原时区转换。

窗口标题与左上角按最新要求仅显示“思绪”，六档强度依次为练气、筑基、金丹、元婴、化神、渡劫，底层请求参数保持兼容。模型入口选定后直接显示当前模型名，箭头采用独立图标并垂直居中；查询进度改成易读的成功或未完成说明。

状态：已实现并验证。相关界面回归144/144（0失败、0跳过）；随后入口改名与滑条动效的最终控件专项11/11，管理15/15，最终EXE五项独立检查通过。本轮未重跑全部后端测试。正式版本保持1.1.0，未推送。详见 [轻量控件验收](docs/SIXU_LIGHT_CONTROLS.md)。
<!-- SIXU_LIGHT_CONTROLS_END -->


<!-- SIXU_STATISTICS_MODEL_BEGIN -->
## 附件点击详情、聊天足迹与 6.1 Sol · 2026-10-15

图片、表情直接展示，其他附件只保留点击入口；文件名、大小、状态与保存操作都在点击后查看。左下角改为“统计”，按当前身份或整个归档展示聊天日历、时段/星期分布、连续活跃、夜间比例、参与者与附件统计；仅基于已导入归档，本地只读聚合，后台计算并复用缓存。

已实际核实旧0.153.4无法完成6.1 Sol请求；隔离的官方0.162.1组件签名有效，GPT-6.1-Sol完成合成回复和archive_*工具调用。新版随附此组件与许可证，首次迁移默认6.1 Sol，之后保留主动改选。用户确认无官方题库授权，已接入官方资料索引、概括说明与正版测评入口，并提供明确授权的题库导入；没有分发完整官方题目或假冒正式测试。

流畅度：252会话/1004条自建记录，结果一致、归档摘要不变；联系人SQL759→3，中位28.14→5.30ms；100条消息附件SQL102→3。未变联系人复用控件。数据是查询阶段基准，不代表所有UI或模型请求延迟。

状态：已实现并验证。全量发现761项：760通过、0失败、1项既有Windows符号链接权限跳过；管理15/15。最终EXE五项独立检查通过；真实GPT-6.1-Sol合成回复与只读工具调用通过。正式版本保持1.1.0，未推送、未创建正式标签。详情见 [统计、模型与资源验收](docs/SIXU_STATISTICS_MODEL.md)。
<!-- SIXU_STATISTICS_MODEL_END -->


<!-- SIXU_MEDIA_REPAIR_BEGIN -->
## 思绪 1.1.0 图片表情修复版 · 2026-10-15

修复实际微信图片定位：优先匹配消息 packed_info 中的本地缓存标识，避免把 XML 中的 CDN 明文 MD5 当作缓存文件名。补充按月份的 Emoticon 缓存目录；本地恢复失败的表情，在用户授权的官方 CDN 地址补全后校验 MD5、大小和图像格式。开关可在添加页关闭，来源 API 默认离线，不改变系统或 Codex 代理。

已用原先失败的真实来源验收：8 张图片、8 个表情恢复成功，含 50/51 帧 GIF；最终 EXE 对两个会话各读取 50 条，23 个附件引用全部取得，归档中 22 个去重资源均可用，其中 15 个图像资源可解码。真实 Tk 缩略图显示通过；合并转发可展开 10 条文本子记录。

“正在回复”改为“千丝万绪…”并保留符号动画。按用户最终要求，导航、主要操作和状态保留文字，仅明确的辅助操作采用图标，悬停或键盘聚焦显示说明；同时可见的不同辅助操作使用不同符号。后台读取期间可切页，写入动作继续互斥；缩略图校验及解码移到后台，缓存未变页面的排版。本机同组 8 个真实媒体、3 次冷缩略图构建的主线程中位耗时 76.046 ms → 37.978 ms；文本切页基准 47.38 ms → 44.28 ms，仅代表该基准。

追加字号、字体与主题切换优化：按变化类别更新，避免重置同一Tk主题；字体局部样式预备12–24字号，隐藏页面显示时再应用最终外观；连续点击应用合并处理。修复复制字体描述时把负像素单位变成点数造成的字号应用错误。同一125条合成记录基准，字号回调中位 2079.146 ms → 71.754 ms，包含后续事件循环重绘的总耗时 3574.412 ms → 1902.316 ms。总重绘仍有首次字体载入与Windows绘制成本，不能把回调返回快宣称为所有像素立即就绪。

验收：全量 740 项，739 通过、0 失败、1 项既有 Windows 符号链接权限跳过；管理 15/15。最后字体样式调整后补跑相关界面与兼容性 100/100；最终 EXE 五项独立探测通过。媒体真实读取与显示验证和合成回归分别记录。保留正式版本 1.1.0 及原 v1.1.0 标签；本次为单独标识的本地修复构建，未推送。

使用方式、原因、验收范围及限制见 [媒体修复验收](docs/SIXU_1_1_MEDIA_REPAIR.md)。
<!-- SIXU_MEDIA_REPAIR_END -->


<!-- SIXU_1_1_BEGIN -->
## 思绪 1.1.0 · 2026-10-15

Codex 对话改为用户靠右、Codex 靠左，增加符号轮换的“正在回复”提示；完成、停止和断线时清除。流式增量每轮合并刷新，排版后跟随最新回答，保留上翻阅读、复制及消息引用。

修复 Code Mode host 被关闭导致 archive_* 调用失败。提问前实际读取所选归档的一批原文，并随请求传入编号引用、筛选条件与覆盖数量；不足全量时明确标记。真实 GPT-5.6-Sol 自建口令测试已成功调用 archive_messages 并返回正确口令和引用，没有读取或上传真实聊天。

一键读取接入普通图片和本地 GIF/PNG/JPEG/WebP 表情缓存；修正媒体输出目录不一致造成的误判失败。按消息声明的MD5匹配并验证表情内容，缺失不联网补抓。随包提供 HEVC 解码器，wxgf 图片转换为可显示预览并保留原始容器。读取结果显示取得、缺失和异常数量。旧消息可重读补充缺失附件，仍按来源ID去重。

页面切换复用既有控件，减少重复映射及整窗本地化。全量727项：726通过、0失败、1项既有Windows符号链接权限跳过；管理15/15。最终协议、群聊范围、流式与1.1专项补跑21/21；最终EXE五项独立探测均通过。GPT-5.6-Sol真实自建口令调用再次通过，确认模型实际调用archive_messages并返回正确口令和引用。未读取或上传真实微信聊天。

已发布1.1.0；最终记录见 [1.1发布与验收](docs/SIXU_1_1_RELEASE.md)。
<!-- SIXU_1_1_END -->


<!-- SIXU_FIXES_BEGIN -->
## 思绪 1.0 修复批次 · 2026-10-15

本批次调整来源读取与主界面，不提高正式版本号。

- 来源列表与读取动作排除零消息会话，移除标识列；检测不再显示空白统计和无结果面板。
- 添加页直接“导入副本文件”；项目 .db 副本会连同已核验的同名 .media 资源导入并打开。旧归档读取群聊/附件时自动准备兼容工作文件，原库保留，无需手动创建升级副本。未知数据库仍按已登记格式校验。
- Codex 只读工具支持所选群聊和私聊的消息正文及附件元数据；身份范围的“所有私聊”仍不含群聊。固定线程、回合、归档与成员权限，发送前先核对读取能力；动态工具显式即时提供。附件原文件不自动上传。
- “未识别”拆分为发送者未映射与来源类型未登记。登记的群发送者前缀可恢复账号；其余记录保留正文与原始来源，以未映射身份呈现，不计入本人发送数。已知附件类型仍保留附件引用；未登记类型保留可读内容、类型号和原始字节，不能宣称所有专有编码均可解码。
- 右上角始终显示 Codex 应用图标作为统一入口；移除聊天头部与工具页的重复助手入口，以及设置页重复的新建/打开/升级操作。主聊天搜索与可选本地模型语义检索各保留一条不同用途的路径。
- 修复群消息及联系人预览中的重复发送者前缀、联系人画布空白焦点边框、本人占比换行与群成员箭头状态。原文复制与存储保留来源内容。
- 中英文帮助同步解释副本导入、消息与发送者状态、读取边界和统计。

验证：全量719项，718通过、0失败、1项既有Windows符号链接权限跳过；管理15/15。最终修复专项9/9、来源读取4/4及EXE五项独立验证均通过，12张真实合成窗口图已核查。未读取用户私有微信库、未进行真实模型推理；没有推送或创建新正式版本标签。

详见 [修复验收说明](docs/SIXU_1_0_FIXES.md)。
<!-- SIXU_FIXES_END -->

<!-- SIXU_1_0_BEGIN -->
## 思绪 1.0.0 · 2026-10-15

新增Codex本地历史记录与同线程恢复、模型/努力程度组合入口、可搜索的会话范围面板；历史、保存和设置位于同一工具栏。联系人显示本人发送数与占比，群聊按群名折叠成员并显示各成员发言份额。扩展归档接入群聊、Unicode表情、图片/动图、音视频及任意文件的原文件保存与离线导出；缺失或未解密资源明确标注。帮助按操作步骤、标题与说明重写，并适配窄窗口。

新建桌面归档使用扩展Schema3；旧库继续可读，新增群聊与附件前创建升级副本。旧来源命名空间与消息ID继续复用，避免升级重读产生重复身份或重复消息。原私聊工具保持只读与范围隔离，附件不会自动上传给模型。

已发布1.0.0：全量710项，709通过、0失败、1项既有Windows符号链接权限跳过；管理15/15。最终补跑1.0专项13/13、群聊来源4/4、Codex协议/面板31/31、导出5/5通过。最终EXE五项独立验证通过，含GIF播放、群成员折叠、本人占比、附件字节保真、历史及参数入口。12张合成窗口图已完成核查。原文、二进制附件和自建归档摘要保持。真实来源与真实推理质量的未验边界在发布说明中保留。

完整变更、升级方式与支持边界见[1.0发布说明](docs/SIXU_1_0_RELEASE.md)。
<!-- SIXU_1_0_END -->


<!-- SIXU_UI_BEGIN -->
## 思绪命名与视觉对齐 · 2026-10-15

项目显示名称统一为“思绪”，英文名 Sixu；桌面顶栏/窗口标题、Codex对话导出标题、本地浏览器、Windows程序属性与开发包入口同步更新。包名、已有配置位置、数据库与业务接口保持兼容，正式版本保持0.8.0。

桌面各栏采用16逻辑像素留白，以8像素为主要操作间距；会话/聊天/Codex标题使用统一字体与行高，搜索输入/下拉/按钮统一高度；消息与筛选、底部计数沿同一边缘排列，Codex范围靠左并按实际宽度省略。保留各主题、中英文、字号、抽屉/收起与原文操作。本地浏览器同步中性配色及间距、控件尺寸。

状态：已实施并验证。全量693项：692通过、0失败、1项原有Windows符号链接权限跳过；管理15/15。6组尺寸/字号布局检查与17张合成窗口渲染完成，最终EXE四项独立探测通过。未读写用户聊天库，未推送或正式发布。详见[命名与界面验收](docs/SIXU_VISUAL_ALIGNMENT.md)。
<!-- SIXU_UI_END -->


<!-- CODEX_CONTROLS_BEGIN -->
## Codex 使用区、添加流程与响应优化 · 2026-10-14

右侧统一名称Codex；展开时仅侧栏关闭图标，折叠后仅顶栏展开图标。归档范围是可操作按钮，可选文件、身份和会话；输入区提供完整组件模型目录（含隐藏项）、模型支持的努力程度、快速模式与刷新图标。参数保存并随每次请求冻结，中途改变用于下一次发送，当前流式回答继续；切模型保持同一授权范围内的对话线程。

设置/复制/保存/编辑/删除/刷新等采用矢量图标并保留键盘、可访问文本和悬停说明。添加页按账号→会话→归档、来源→预览导入排列，空表和未执行统计隐藏；说明与路径低频项折叠。消息改为无底色块的可选原文，自身方向使用细线，输入框用细下划线，标签页用选中线。

非当前页面实际取消映射，减少隐藏控件绘制。相同100条合成消息、各3次本机源码运行，中位首屏恢复1.18s→1.19s，重复刷新81ms→67ms；源码计时不含进程和Tk初始化，真实鼠标/DPI与模型延迟待验。

全量693项，692通过、1原有Windows符号链接权限跳过；管理15/15；最终EXE四项独立探测通过。实际Codex0.153.4独立无登录目录验证完整11项目录、服务层fast参数被接受并返回priority别名、普通层default被接受；没有真实账号或推理请求，目录不等于模型访问授权或速度保证。

正式版本0.8.0，未推送或发布。详见[本阶段验收](docs/CODEX_CONTROLS_UI.md)与[使用帮助](docs/USER_GUIDE.md)。
<!-- CODEX_CONTROLS_END -->


<!-- FAST_HELP_BEGIN -->
## 客户端响应、配色与侧栏帮助 · 2026-10-14

启动恢复放到窗口建立后的事件循环；消息未变化时复用控件和原文选择，排版缓存宽度/字体，仅重排变化内容，屏幕外正文暂不绘制，空闲轮询降频。减少重复快捷键和功能说明，改用文字按钮、平面会话行、导航细线和矩形消息文本面。

主题新增暖砂、雾蓝、松绿、紫雾，与浅色/深色/跟随系统共7项；保留字体、中文/English、目录与AI设置。左侧新增“帮助”，内置离线章节、关键词搜索与中英文帮助正文，按需创建帮助界面；文档见[使用帮助](docs/USER_GUIDE.md)。

本机源码、100条合成消息、1240×820窗口、各3个新进程，中位“窗口建立至首屏会话就绪”2.24s→1.19s，重复刷新2.04s→0.075s。计时不包括进程加载/Tk建立；未宣称全部交互或冻结EXE启动速度已按相同方法验收。

全量684项，683通过、0失败、1原有Windows符号链接权限跳过；管理15/15；最终EXE四项独立探测通过，包含四个新配色、帮助搜索/英文正文与控件复用。仅用自建数据，原文、姓名和数据库哈希保持；真实硬件滚动、系统DPI、其他电脑、实际AI质量继续待验。正式版本0.8.0，未推送或发布。详情见[响应与帮助验收](docs/FAST_CLIENT_HELP.md)。
<!-- FAST_HELP_END -->


<!-- LIGHT_SETTINGS_BEGIN -->
## 轻量工作区与用户设置 · 2026-10-14

细滚动条支持拖动/键盘/滚轮，空闲进度和取消控件隐藏，主区域以浅色差分区。AI侧栏仅保留提问、阅读、复制、保存和重试；Codex连接/登录/运行组件/范围/模型及本地模型配置移入独立设置页。

设置支持浅色/深色/跟随系统、已安装字体、12–24逻辑像素字号、简体中文/English、滚动速度、紧凑导航、恢复归档、减少动画、默认AI侧栏、存储目录、导出目录/格式。配置持久化并即时应用；跟随系统自动复核，原文和姓名不翻译。新文件位置重定向，当前归档不移动；配置/登录资料保留原配置位置。

工具仅显示归档管理、导入报告和可用原文检索，隐藏助手占位页/备份载荷诊断及未配置模型的回答入口；低层兼容接口保留。全量隔离675项，674通过、0失败、1原有Windows符号链接权限跳过；管理15/15及最终EXE四项探测通过，打包探测包含真实控件的深色/英文/字号/存储重定向与保存复核。

使用合成数据完成多页/多主题/英文实际渲染，真实鼠标/系统DPI跨屏/其他电脑待验；沿用独立GUI进程回归以避免本机连续Tk解释器限制。正式版本0.8.0，未发布或推送。详情见[轻量界面与设置说明](docs/LIGHT_WORKSPACE_SETTINGS.md)。
<!-- LIGHT_SETTINGS_END -->


<!-- ROUND_SCROLL_FIX_BEGIN -->
## 圆角界面与滚轮修复 · 2026-10-14

已按用户确认改善按钮/区域过于方正的问题：原生 ttk 圆角按钮、输入/下拉和标签页，圆角导航与联系人卡片、圆形头像、16像素消息气泡及圆角AI输入区；收紧按钮内边距，聊天标题操作放在同一行。继续使用现有业务与数据管线，正式版本保持0.8.0。

滚轮按所在区域统一路由，消息正文/时间/气泡边缘、头像、动态设置子控件均可响应；Canvas保留细小增量，文本累积不足一格的增量，嵌套文本到达边缘时交给外层。保留Shift+滚轮原生水平行为、原文选择和键盘操作。

全量663项按隔离模式执行：662通过、0失败、1原有Windows符号链接权限跳过；新增滚轮专项10项纳入全量；管理15/15通过。开发EXE已构建，无外部Python PATH的导入导出、工作台/Copilot、知识和独立无登录Codex四项探测通过。五张合成窗口渲染已核查。常规单进程Tk全量回归在反复创建窗口时停滞，未声明通过；真实鼠标硬件、触控板、实际系统DPI/跨屏和其他电脑继续待验。

Codex官方资料仅提供工作区结构参考；官方截图浏览被管理员策略拦截，没有取得当前逐像素视觉规范。详情见[圆角与滚轮修复说明](docs/ROUND_SCROLL_FIX.md)。
<!-- ROUND_SCROLL_FIX_END -->


<!-- CLIENT_VISUAL_AUDIT_BEGIN -->
## 客户端审美修补 · 2026-10-14

仅调整 Tk 桌面客户端视觉：中性浅色主题、深灰主操作、淡蓝自身消息、统一控件和文本滚动条、轻量折叠设置、AI 输入/发送组合区域。保留既有字号设置、路由、快捷键和数据/AI管线，正式版本仍为0.8.0。

客户端专项 76/76 通过；全量 653 项，652 通过、0 失败、1 个既有 Windows 符号链接权限跳过；管理 15/15 通过。 Windows 开发包已构建；无外部 Python PATH 的导入导出、工作台/Copilot、知识与独立无登录 Codex 四项 EXE 探测均通过。

视觉边界：已检查并保存修补前合成窗口。用户通过 Esc 停止 Computer Use，修补后人工视觉复核尚未完成；程序布局与交互回归通过不等于审美验收。真实系统 DPI、跨显示器和其他电脑继续待验。Codex 官方资料仅支持结构参考，没有取得其精确颜色、字号或圆角规范。

[前端审美报告](docs/CLIENT_VISUAL_AUDIT.md) · [验收记录](docs/acceptance/CLIENT_VISUAL_AUDIT.md)。
<!-- CLIENT_VISUAL_AUDIT_END -->


<!-- COPILOT_PHASE1_BEGIN -->
## 常驻 AI Copilot 第一阶段 · 2026-10-14

常驻AI侧栏、折叠/拖宽/布局恢复、Ctrl+L/询问AI入口、AIContext和基础上下文注入已完成；复用既有连接登录、流式、引用和重试。提问时界面仅冻结元数据，校验与参与者解析在后台，原文按授权只读工具按需查询。全量653项：652通过、0失败、1个原有Windows符号链接权限跳过；管理15/15通过。独立Windows开发包构建完成；无Python PATH的导入导出、工作台/Copilot、知识与独立无登录Codex四项EXE探测通过。

正式版本保持0.8.0；用户归档Schema和历史数据保留。历史持久化、选中/可视消息及位置、RAG增强和主动提示留待后续阶段。

[使用与上下文契约](docs/COPILOT_PHASE1.md) · [阶段验收](docs/acceptance/COPILOT_PHASE1.md)。
<!-- COPILOT_PHASE1_END -->


## 客户端体验第一批进度

2026-10-14：六项客户端优化已逐项验收并各自提交：动态能力、搜索往返、流式阅读、失败重试、导出打开、键盘操作。全量 628 项，627 通过、1 原有 Windows 符号链接权限跳过、0失败；管理 15/15 通过。 新Windows开发包构建成功；无Python PATH的导入导出、工作台六项新行为、只读知识与独立无登录Codex四项EXE探测通过。 正式版本保持0.8.0，未迁移个人归档或发布正式Release。

报告：[第一批客户端验收](docs/acceptance/CLIENT_UX_BATCH1.md)；使用说明：[客户端体验](docs/CLIENT_EXPERIENCE.md)。







2026-10-14 当前 P2：P2-A/B/C/D 已形成可运行源码闭环：原文引用、独立可重建索引、本地问答 UI，以及 GUI/CLI 复用的 v1.0 stdio 只读 API。最终596项595通过/1原有跳过；新 EXE 的导入导出、工作台、知识撤权/API、独立无登录官方 Codex 四项探测通过。真实本地模型质量与 P1 剩余功能仍待验收/实施。 当前实现/限制及下一步以 [P2-D 版本化只读扩展接口与开发包完成](docs/acceptance/P2_D_API_DESKTOP.md) 和 docs/UPGRADE_CYCLE.md 为准；以下路线中的预留表述保留原方案历史含义。


2026-10-14 当前 P2：增加工具与设置→本地知识问答：范围、离线/本地模型选择、更新/重建索引、原文检索和回查、结构化证据问答、取消、复制及新文件保存。缺证据不调用模型，伪造/缺失引用拒绝，源变化丢弃回答，推断与原文分别标明；既有 Codex 助手保持。默认127.0.0.1:11434无法连接，真实模型质量尚未验收。 当前实现/限制及下一步以 [P2-C 本地证据问答界面完成](docs/acceptance/P2_C_LOCAL_RAG_UI.md) 和 docs/UPGRADE_CYCLE.md 为准；以下路线中的预留表述保留原方案历史含义。


2026-10-14 当前 P2：实现独立 SQLite 向量索引、精确余弦检索、增量复用/删除、显式重建、取消/故障回滚与过期拒查；离线字符向量可直接使用并标为字面检索，Ollama 接口仅选已有本机模型，记录真实模型摘要/维度，不下载或调用云模型。 当前实现/限制及下一步以 [P2-B 独立索引与模型接入完成](docs/acceptance/P2_B_REBUILDABLE_INDEX.md) 和 docs/UPGRADE_CYCLE.md 为准；以下路线中的预留表述保留原方案历史含义。


2026-10-14 当前 P2：实现 KnowledgeSource/ChunkRef，私聊原文按 Unicode 字符切片、稳定 keyset 分页，绑定归档文件身份、身份/联系人范围、消息版本、原文摘要；修改/删除/切库/切范围使引用或游标失效。只读 Schema1/2/3，不创建或迁移用户库。 当前实现/限制及下一步以 [P2-A 引用式知识接口完成](docs/acceptance/P2_A_KNOWLEDGE_SOURCE.md) 和 docs/UPGRADE_CYCLE.md 为准；以下路线中的预留表述保留原方案历史含义。


## Codex使用界面改进

开发版提供连接→登录→选择范围→提问的清楚流程，未登录不能发送；快捷问题只填入、Ctrl+Enter发送。消息引用可回查当前授权原文，回答可复制或保存到新文件；归档设置可创建验证后的升级副本。详见[本阶段验收](docs/acceptance/P1_CODEX_WORKFLOW.md)。真实账号推理与登录网络问题仍需独立验证。


## 封存历史与断点导入

Schema3源码归档的全范围读取使用选定会话封存快照，逐批写入与断点同事务；可停止后续批次并恢复。快照目录可从“文件导入”预览/导入，或`python -m cli --db <Schema3副本> import-snapshot <目录>`；已完成重复操作会按来源身份去重。预览来源记录数不等于支持文本数，未知内容仍保留，真实来源全历史尚未独立验收。详见[阶段报告](docs/acceptance/P0_D_SNAPSHOT_STREAMING.md)。


## 创建升级副本

开发源码新增`python -m cli upgrade-copy <已有归档> <新的目标文件>`，仅对Schema1/2完整离线归档创建Schema3副本，原库保留；默认Schema2不变。旧版软件不能打开新副本，当前新源码可读其中已有私聊文本。媒体/群聊产品功能仍待后续，详见[副本迁移验收](docs/acceptance/P0_C_COPY_SCHEMA.md)。


## 当前源码契约与引用

P0-B新增来源能力与统一消息契约，以及Codex的内容版本/范围绑定引用；实际运行仍为登记私聊文本，领域媒体/群聊类型不等于已经可导入。详情见[本阶段验收](docs/acceptance/P0_B_CONTRACTS.md)；既有EXE仍是之前发行包。


## 开发源码升级进度

P0-A来源身份修复已完成源码验收，既有免安装EXE保持旧发布状态。登记Windows来源不同ID相同正文分别保存，同ID内容冲突明确报告；普通标准文件仍沿用原内容去重。详情见[阶段验收](docs/acceptance/P0_A_SOURCE_IDENTITY.md)和[升级记录](docs/UPGRADE_CYCLE.md)。


当前版本 **v0.8.0 归档工作台**，在实际最新 v0.7.0 上实施。原生 Python/Tk/ttk；SQLite Schema 2、chat-exchange 1.0 和原导入/来源/导出契约保持兼容。

完整解压 Windows 包，双击 **ChatArchive.exe**，保留 `_internal`。四个一级入口是聊天归档、添加记录、导出归档、工具与设置；电脑微信/文件导入属于添加记录，CRUD/备份/报告/设置及 Codex 助手属于工具与设置。已有归档直接进入浏览，可恢复有效身份/会话；没有归档显示打开/添加入口。

源码 GUI：`python -m wechat_archive.desktop`。原 CLI：`python main.py --help` 或 `python -m cli`；旧导入窗口、脚本和网页入口保留。

说明见 [归档工作台](docs/WORKBENCH.md)，证据与未验证边界见 [验收](docs/WORKBENCH_ACCEPTANCE.md)。完整回归 440 项：439 通过，0 失败，1 个原有符号链接权限项跳过。最终 EXE 已实际验证浏览、搜索、上下文、复制、分页、导入/去重及导出。

现有 Codex 功能保留；账号登录的 token_exchange_failed 网络故障尚未解决。界面改版没有扩展群聊、媒体、未知格式、RMFH 正文或超限全历史。以下既有来源/兼容说明保留，本轮没有重新读取真实微信。

## Windows 桌面软件

免安装包保留同目录 `_internal` 文件夹，不能只复制 EXE，也不要在 ZIP 预览里直接启动。默认归档保存在 `%LOCALAPPDATA%\WeChatArchive\chat.db`，与程序分开，升级程序不删除数据。导入报告位于该数据目录的 import_logs。

可以选择现有归档库，直接查看或导出，无需重复导入；默认归档存在时下次启动自动恢复。JSON/CSV/真实微信结构化文件导入、去重、网页查看、HTML/TXT 导出均沿用原功能。

v0.5.7 曾仅封装导入窗口，不含获取组件；这段记录保留为历史。v0.6.0 已整合真实读取和软件内浏览，包内不包含个人聊天或密钥。以前的桌面打包基线见 [旧桌面版说明](docs/WINDOWS_DESKTOP.md)。

## 可读存储：离线 HTML 与 TXT

已归档的文本可以保存为不依赖微信、软件服务的文件：HTML 保留双方消息排版，TXT 保留原文便于长期保存和搜索。双方身份、时间、方向、空格和换行均保留；默认按 UTC+08:00 显示，数据库原时间不变。

双击 **导入数据.cmd**，将“目标归档库”选为已有归档，点击底部 **导出可读文件**，选择保存位置。系统创建新子目录，含 index.html、各会话 HTML/TXT 和完整性清单 manifest.json。不需要重新选择来源文件，既有输出不覆盖。

从项目目录导出：

```powershell
python -m cli --db data/real_wechat_verified.db export-readable "D:\chat_exports\readable_20261013"
```

只读导出的是**已经入库的全部所选文本**，不限于网页当前页。本次真实私聊 38 条已导出为 HTML/TXT；未入库的 12 条来源隔离记录仍在原来源/报告中。获取全历史是独立下一阶段，不会因导出自动补齐。使用、范围、只读与完整性约定见 [可读存储说明](docs/READABLE_STORAGE.md)。

## 真实微信导入（当前主线）

本机 Windows 微信 **4.1.15.51** 的真实验收：2 个身份、1 个私聊、38 条原始文本，其中发出 15 条、收到 23 条；二次导入新增 0 条、重复 38 条。时间和原文逐条与来源一致，用户已人工确认网页显示双方文字。50 条来源记录中另有 12 条非文本/未支持记录保留在导出文件与报告，不进入文本归档。

四层流程为 **数据获取 → 来源解析 → 标准化 → 通用导入**。本版本只接受登记工具 API 生成的 `wechat-external-export 1.0` 文件；普通第三方 JSON 或任意 SQLite 不能凭后缀导入。工具版本和原始文本证据不匹配时明确拒绝。

使用桌面入口：双击 **导入数据.cmd**，选择 **Windows 微信结构化导出**（也可自动识别），选择导出的 JSON，预览后开始导入。已有归档追加并去重。真实来源类型没有“填入示例”，防止把演示当成实际导入。

从项目目录运行已有导出文件：

```powershell
python -m cli wechat detect "D:\chat_exports\private.json"
python -m cli --db data/my_wechat.db wechat import "D:\chat_exports\private.json" --adapter external
python -m cli --db data/my_wechat.db wechat import "D:\chat_exports\private.json" --adapter external
python main.py --db data/my_wechat.db serve --open --port 0
```

来源获取入口是 `python -m cli wechat acquire-export`，需要单独准备工具环境并保持 Windows 微信登录。具体步骤、字段契约、来源标识和限制见 [真实导入说明](docs/REAL_WECHAT_IMPORT.md)。本次实测记录见 [真实验收](docs/REAL_WECHAT_MVP_ACCEPTANCE.md)，技术选择见 [路线比较](docs/REAL_SOURCE_ROUTE_COMPARISON.md)，完整阶段汇报见 [最终报告](docs/REAL_SOURCE_FINAL_REPORT.md)。

源码包和自动测试不含任何真实聊天、账号库或密钥。v0.6.0 自动测试 **383 项，382 通过、1 项历史权限测试跳过**；EXE 的真实读取/导入/显示/导出验收独立记录。此前各阶段的 331/351/360 项记录保留为历史证据。

## 保留的备份研究与历史入口

**v0.5.4 新增元信息与载荷探测。** 选择备份后点击 **探测载荷**，按模式选取较小消息包和同名索引候选，生成元信息 wire 报告、载荷证据、解码评估和中文摘要。默认单文件正文最多 64 KiB、正文及元信息合计最多 4 MiB。详见 [载荷阶段文档](docs/rmfh_payload.md)。真实样本当前编码仍未知，没有恢复聊天正文。

**v0.5.3 新增 RMFH 格式分析器。** 在窗口选择备份目录后点击 **分析 RMFH**，会生成文件结构 JSON、逐文件头分析 JSON 和中文摘要；分析不需要目标归档库。CLI 为 `python -m cli wechat analyze-backup <目录> --report-dir <报告目录>`。外壳解析接口和报告约定见 [RMFH 分析器文档](docs/rmfh_analyzer.md)。

**v0.5.2 新增微信 RMFH 备份结构检查，该备份路线的聊天正文解密和导入仍未完成。** 选择这种备份后点“预览检查”，可查看文件统计、缺失条件及检查报告。完整边界见 [微信备份说明](docs/wechat_backup.md)。

## 直接打开导入窗口

完整解压项目后，双击根目录的 **`导入数据.cmd`**。它自动定位项目，打开中文导入窗口，不需要输入命令或先切换目录。

1. 选择数据类型，或保留“自动识别”。
2. 点“选择文件”或“选择文件夹”，选择真实微信结构化导出、标准 JSON、CSV、历史示例/明文快照，或仅需检查结构的 RMFH 备份。
3. 确认目标归档库。默认 data/chat.db；“填入示例”会使用独立 data/ui_demo.db。
4. 可先点“预览检查”，它不会写入数据库；点“开始导入”执行。
5. 查看新增、重复、失败及报告；点“查看已导入的聊天”会打开该归档库。

保留导入窗口即可使用这里启动的浏览服务；关闭窗口会停止这些服务。导入进行中应等待完成再关闭。完整说明见 [导入窗口说明](docs/import_window.md)。

仍可使用 `python main.py import-ui`。如果 PowerShell 提示 No module named cli 或找不到 main.py，说明当前目录没有项目；双击入口可以避免这个问题。不要在 ZIP 预览里直接运行，须先“全部提取”。

## 现在能做什么

| 功能 | 已实现的行为 |
|---|---|
| 初始化数据库 | 创建 SQLite 文件和表；重复初始化保留已有数据 |
| 联系人 CRUD | 新增、按 ID 或 wxid 查询、分页列表、修改、删除 |
| 消息 CRUD | 新增、查询、筛选、修改、删除文本消息 |
| 双向会话 | 同时查询 A→B 与 B→A，按真实时间排序 |
| 搜索 | 中文和其他文本的字面关键词匹配，可限定联系人、会话、时间范围 |
| 数据保护 | 双端外键、唯一 wxid、事务回滚、关联消息阻止联系人删除 |
| 演示 | 独立 `demo.db`：3 位虚构联系人、5 条消息，重复运行不增加记录 |
| 中文网页 | 左侧联系人和最近消息，右侧双向聊天气泡，支持窄屏布局 |
| 网页搜索 | 当前聊天或全部聊天搜索、日期筛选、结果计数、分页加载 |
| 查看身份 | 切换归档中的参与者，查看其参与的聊天 |
| 只读网页接口 | 本机 HTTP GET 接口；网页不提供增删改功能 |
| 标准格式导入 | JSON 与 CSV，自动建立用户、私聊和消息 |
| 校验与报告 | 默认部分导入、可选严格模式，每次生成 import_logs/ JSON 报告 |
| 消息去重 | 统一时间与内容哈希，重复消息跳过并统计 |
| 数据库升级 | 版本 1→2 自动备份、事务迁移，保留旧记录 |
| 微信模拟接入 | wechat-mock 1.0 转换为标准协议，复用现有导入系统 |
| 来源检测和转换 | wechat detect / convert / import；external 真实结构化导出，RMFH 备份正文尚未实现 |
| Windows 真实私聊 | 隔离获取 API、稳定 wxid/分片来源、原始文本/UTC、未支持原记录保留；本机真实 38 条验收 |
| 微信备份结构 | RMFH 目录/消息包外壳检查、统计、报告；实际消息数量未知，正文导入明确失败 |
| RMFH 格式分析 | ChatPackage/Index/Media 逐文件清单、头字段原始值/大小端解释、头尾边界、14 种实测前缀模式、JSON/Markdown 报告 |
| RMFH 有限载荷探测 | 4 个元信息文件 wire 投影、14 模式采样覆盖、明确读取预算、注册式有界解码与认证边界；真实消息数仍未知 |
| Android 文件框架 | 已解密、停止写入的 SQLite 快照，账号元信息与登记 Schema 校验 |
| Android 结构和文本 | 表/字段报告，私聊文字、方向、毫秒时间，标准文档和解析报告 |
| 桌面导入入口 | 选择文件、预览、开始导入、结果与报告、打开对应聊天浏览器 |

## 先体验 Android 解析

完整解压项目，在项目目录运行自建模拟库：

```powershell
python -m cli android detect android_mock
python -m cli android schema android_mock
python -m cli android parse android_mock --output data/android_exchange.json
python -m cli --db data/android_demo.db wechat import android_mock --adapter android
python -m cli --db data/android_demo.db wechat import android_mock --adapter android
python main.py --db data/android_demo.db serve --open --port 0
```

模拟源中 7 条记录解析出 5 条私聊文本，图片/群聊各跳过 1 条；首次导入 5 条，重复跳过 5 条。自动测试和随包输入均为自建数据；真实来源验收单独记录，不随包发布。

**实际文件支持有明确前提：已解密、已关闭写入、附账号和 Schema 元信息、符合登记字段投影。** 未知结构和类型明确失败，不猜测；当前不解密，不提取媒体，不解析群聊，也不承诺所有微信版本兼容。详见 [Android 解析文档](docs/android_parser.md)。

## 先体验微信模拟接入

完整解压源码压缩包后，在项目目录运行：

```powershell
python -m cli wechat detect wechat_mock/export.json
python -m cli --db data/wechat_mock.db wechat import wechat_mock/export.json
python -m cli --db data/wechat_mock.db wechat import wechat_mock/export.json
python main.py --db data/wechat_mock.db serve --open --port 0
```

首次创建自己与两位联系人，共 3 位参与者、2 个私聊、5 条消息；重复导入新增 0 条、duplicated_count=5。报告仍在 import_logs/。

用 `python -m cli wechat convert wechat_mock/export.json --output data/wechat_exchange.json` 可先输出标准 JSON，不写库。工程也附带已转换样例 `wechat_mock/exchange.json`。转换输出必须是新文件，不能覆盖来源或已有文件。

模拟接入继续可用。电脑版 BackupFiles 仍未实现；Android 当前可读符合登记条件的明文快照，解密及媒体仍未实现。第四阶段历史契约见 [微信接入说明](docs/wechat_adapter.md) 与 [mock 映射](docs/wechat_mapping.md)。

本版本支持真实 Windows 结构化私聊文本、自己的笔记及历史登记条件下的明文快照。群聊、媒体、解密、其他未登记格式、电脑版备份、HTML 导出和 AI 分析留待后续阶段。网页功能沿用 v0.2.0。

## 先体验导入

源码压缩包必须先右键“全部提取”。在完整项目目录打开 PowerShell：

```powershell
python main.py --db data/import_demo.db import examples/chat_sample.json
python main.py --db data/import_demo.db import examples/chat_sample.json
python main.py --db data/import_demo.db serve --open --port 0
```

首次新增 3 条，第二次跳过 3 条重复消息。CSV 示例：

```powershell
python main.py --db data/csv_demo.db import examples/chat_sample.csv --namespace my-account --timezone +08:00
```

默认合法记录会写入，错误记录跳过并列出原因；加 `--strict` 要求任何错误都拒绝整份文件。报告默认在 import_logs/。完整 Schema、映射、时区、去重和扩展规则见 [导入格式文档](docs/IMPORT_FORMAT.md)。

## 先打开网页

如果使用源码压缩包，右键 → **全部提取** → 打开解压后的 `wechat_archive` 文件夹。不要在 ZIP 预览中直接运行启动文件。

- 双击 **`Run-Web-Demo.cmd`**：启动演示库并自动打开浏览器，立即体验联系人和聊天记录。
- 双击 **`Run-Web.cmd`**：打开正式库 `data/chat.db`；首次交付时它为空。

页面启动后保留终端窗口。在终端中按 **Ctrl+C** 停止服务，然后按提示关闭窗口。再次启动会自动选择可用端口。页面仅绑定 `127.0.0.1`，没有上传聊天或发布网站的步骤。

也可以从项目目录打开 PowerShell：

```powershell
python main.py serve --demo --open --port 0
```

查看指定的归档文件：

```powershell
python main.py --db data/my_archive.db serve --open --port 0
```

不加 `--open` 时不会自动打开浏览器，终端会显示实际访问地址。不指定 `--port` 时默认使用 8765；端口被占用时可改用 `--port 0` 自动选择。

### 网页操作

1. 在左侧“查看身份”选择参与者，点击联系人查看双方聊天。
2. 联系人列表显示最近消息和该双向聊天的总条数；昵称或标识可用于查找联系人。
3. 输入关键词，选择“当前聊天”或“全部聊天”，点击“搜索”。全部聊天只搜索当前查看身份参与的消息；点击结果上方的会话链接可回到来源聊天。
4. 选择开始日期和结束日期后点击“搜索”。两天均包含在内，统一按北京时间解释；“清除筛选”恢复列表。
5. 超过 50 条消息时点击“加载更多消息”；超过 50 位联系人时点击“更多联系人”。消息按时间先后显示，加载更多继续追加后面的记录。
6. 通过原有命令行或 Python 接口修改数据后，点击右上角“刷新”。网页本身只浏览，不修改数据。

网页包含空库、空会话、无搜索结果、加载失败和重试状态。启动窗口关闭后，页面需要重新启动服务才能继续读取数据。

### 本机 HTTP 接口

| GET 路径 | 参数与返回 |
|---|---|
| `/api/status` | 版本、演示/归档模式、数据库文件名、联系人和消息数量 |
| `/api/users` | `limit`、`offset`；分页参与者列表 |
| `/api/contacts` | 必填 `user_id`；可选 `q`、`limit`、`offset`；联系人摘要 |
| `/api/messages` | 必填 `user_id`；可选 `peer_id`、`q`、`start`、`end`、`limit`、`offset`；消息列表 |

分页接口返回 `items`、`total`、`offset` 和 `has_more`。网页每页 50 条，接口 `limit` 范围 1–1000。消息接口的 `start` 包含、`end` 不包含，时间参数需带时区；网页会将包含的结束日期转换为下一天零点。

HTTP 层禁用写入方法，不公开数据库或任意本地文件，不允许其他网站跨域读取。UI 只把聊天内容作为文本展示，内容中的 HTML 不会执行。这些约束不等同于登录认证；运行时本机上的其他程序仍可能访问该本地服务。

## 1. 先运行演示

**如果使用下载的 ZIP 压缩包，必须先完整解压。** 右键 `wechat_archive_phase1.zip` → “全部提取” → 选择保存文件夹 → 打开解压后的 `wechat_archive` 文件夹。不要在压缩包预览窗口中直接双击 `Run-Demo.cmd`：Windows 可能只将这一个文件临时提取出来，导致找不到旁边的 `main.py` 和其他模块。

完整项目文件夹里应同时看到 `Run-Demo.cmd`、`main.py`、`README.md` 和名为 `wechat_archive` 的子文件夹。启动入口现在会检查这些必要文件，缺少时显示解压提示。

在本项目目录打开 PowerShell，输入：

```powershell
python main.py demo
```

也可以双击项目根目录的 `Run-Demo.cmd`。它优先使用已创建的 `.venv`，并在运行结束后保留窗口。

演示结果包含：联系人列表、我与张三的 3 条双向聊天、关键词“开会”的 2 条搜索结果。首次运行 `created` 是 `true`，再次运行是 `false`；总数保持 **3 位联系人、5 条消息**。

默认演示数据库是 `data/demo.db`。演示操作遇到其他非空数据会停止，不会重置文件。若你修改过演示库，可以另建一个演示文件：

```powershell
python main.py --db data/demo_2.db demo
```

## 2. Python 环境

本次交付已在当前电脑创建并验证 `.venv`。可直接用：

```powershell
.\.venv\Scripts\python.exe main.py --help
```

如果移动项目或使用压缩包，重新创建虚拟环境；不要复制旧的 `.venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe main.py demo
```

无需激活环境，也无需安装数据库服务器。`sqlite3` 已随 Python 提供，不应单独安装。

两种直接运行方式等价：

```powershell
python main.py --help
python -m wechat_archive --help
```

工程也带有 `pyproject.toml`，开发时可选择 `python -m pip install -e .`，安装后会提供 `wechat-archive` 命令。安装过程中构建工具可能需要联网下载；直接运行以上命令不需要这一步。

## 3. 在独立练习库中完成 CRUD

下面的命令使用 `data/practice.db`。第一次练习请使用一个不存在的文件；这样新增的两个人 ID 才依次是 1 和 2。已有数据时，以命令实际返回的 ID 为准。

`--db` 是全局参数，必须放在子命令之前。相对路径按当前 PowerShell 目录解释。

### 创建数据库和联系人

```powershell
python main.py --db data/practice.db init
python main.py --db data/practice.db user add wxid_me "我"
python main.py --db data/practice.db user add wxid_zhang "张三"
python main.py --db data/practice.db user list
python main.py --db data/practice.db user get 2
python main.py --db data/practice.db user update 2 --nickname "张三同学"
```

### 插入和读取消息

```powershell
python main.py --db data/practice.db message add 1 2 "你好" --time "2026-01-01T12:00:00+08:00"
python main.py --db data/practice.db message add 2 1 "下午三点开会" --time "2026-01-01T12:01:00+08:00"
python main.py --db data/practice.db message get 1
python main.py --db data/practice.db conversation 1 2
python main.py --db data/practice.db search "开会" --user 1 --peer 2
```

`message add 1 2` 的含义是“联系人 1 发给联系人 2”。双方必须已经存在。省略 `--time` 时使用当前时间。

### 筛选、分页和修改

```powershell
python main.py --db data/practice.db message list --user 1 --peer 2 --limit 20 --offset 0
python main.py --db data/practice.db message list --start "2026-01-01T00:00:00+08:00" --end "2026-01-02T00:00:00+08:00"
python main.py --db data/practice.db message update 1 --content "你好，材料准备好了吗？"
python main.py --db data/practice.db stats
```

`--start` 包含起点，`--end` 不包含终点。`limit` 范围为 1–1000，默认 100；`offset` 默认 0。消息按时间升序排列，同一时刻按消息 ID 排序；联系人数按 ID 升序分页。

### 删除练习记录

```powershell
python main.py --db data/practice.db message delete 1
python main.py --db data/practice.db message delete 2
python main.py --db data/practice.db user delete 2
```

若联系人仍是任何消息的发送者或接收者，删除联系人会返回 `ConflictError`；先处理明确要删除的消息才能删除联系人。程序没有隐式级联删除或清空数据库命令。

## 4. Python API

从项目根目录运行 Python，或者在自己的工程中安装本包后导入：

```python
from wechat_archive import ChatService

service = ChatService("data/my_archive.db")
me = service.create_user("wxid_me", "我")
friend = service.create_user("wxid_friend", "张三")

message = service.create_message(
    me.id,
    friend.id,
    "下午三点开会",
    create_time="2026-01-01T12:00:00+08:00",
)

print(service.get_message(message.id))
print(service.get_conversation(me.id, friend.id))
print(service.search_messages("开会", user_id=me.id, peer_id=friend.id))
service.update_message(message.id, content="下午四点开会")
service.delete_message(message.id)
```

上面的创建示例在空库中运行一次；重复创建相同 wxid 会报冲突。可重复执行的完整示例位于 `examples/basic_usage.py`：

```powershell
python -m examples.basic_usage
```

它使用独立的 `data/api_example.db`，依次演示新增、查询、更新、搜索、删除，并只删除本次示例自己创建的消息。

| 接口 | 用途 |
|---|---|
| `create_user(wxid, nickname, avatar=None)` | 新增联系人，返回 `User` |
| `get_user(id)` / `get_user_by_wxid(wxid)` | 单条联系人查询 |
| `list_users(limit=100, offset=0)` | 分页读取联系人，参数按名称传入 |
| `update_user(id, wxid=..., nickname=..., avatar=...)` | 修改指定字段；`avatar=None` 清空头像标识 |
| `delete_user(id)` | 删除无消息关联的联系人 |
| `create_message(sender_id, receiver_id, content, create_time=..., msg_type="text")` | 新增文本消息，返回 `Message` |
| `get_message(id)` | 单条消息查询 |
| `list_messages(...)` | 组合会话、关键词、时间与分页条件 |
| `get_conversation(user_id, peer_id, **filters)` | 查询双向会话 |
| `search_messages(keyword, **filters)` | 按字面关键词搜索 |
| `update_message(id, content=..., sender_id=..., receiver_id=..., create_time=...)` | 修改指定消息字段 |
| `delete_message(id)` | 删除指定消息 |
| `stats()` | 返回联系人和消息总数 |

查询返回冻结的 `User` / `Message` 数据对象。修改数据须通过 `update_*` 方法，不直接修改对象。

错误类型可从 `wechat_archive` 导入并捕获：`ValidationError`（输入不合法）、`NotFoundError`（记录不存在）、`ConflictError`（重复标识、关联约束或库版本不匹配）。业务错误均继承 `ArchiveError`。文件权限、损坏和磁盘等底层异常在 Python API 中保持原始异常类型。

命令行成功返回退出码 0，并把 JSON 输出到标准输出；业务或存储错误返回 1，并把错误 JSON 输出到标准错误。命令语法错误由参数解析器报告，返回 2。

## 5. 数据库设计

`users` 保存所有参与者，包括自己。`wxid` 是本项目中稳定且唯一的外部标识；当前不会与微信账号同步。

| 字段 | 类型 | 规则 |
|---|---|---|
| `id` | INTEGER | 自增主键 |
| `wxid` | TEXT | 非空、唯一；接口会去掉首尾空白 |
| `nickname` | TEXT | 非空；接口会去掉首尾空白 |
| `avatar` | TEXT | 可为空，只保存文本标识 |

`messages` 保存消息：

| 字段 | 类型 | 规则 |
|---|---|---|
| `id` | INTEGER | 本地自增主键，不等同于微信原始消息 ID |
| `sender_id` | INTEGER | 必须关联已有 `users.id` |
| `receiver_id` | INTEGER | 必须关联已有 `users.id` |
| `create_time` | TEXT | 接口统一写入 UTC、固定微秒精度的 ISO 8601 |
| `content` | TEXT | 非空，保留原始首尾空白、换行和 Unicode |
| `msg_type` | TEXT | 第一阶段仅允许 `text` |

建表文件为 `wechat_archive/database/init.sql`。发送者、接收者与全局时间均有排序索引。

双向会话的查询条件是：

```sql
(sender_id = A AND receiver_id = B)
OR (sender_id = B AND receiver_id = A)
```

因此不能只按发送者筛选，否则会漏掉自己发出的消息。

时间输入必须含时区，例如 `2026-01-01T12:00:00+08:00` 或 `2026-01-01T04:00:00Z`，二者表示同一时刻。JSON 输出统一使用 UTC 的 `Z` 格式，Python 对象返回带 UTC 时区的 `datetime`。当前命令行未提供本地时区显示。

关键词用 SQLite `instr` 按字面、区分大小写匹配，`%` 和 `_` 没有通配含义。第一阶段没有全文搜索索引，大型归档可在后续引入 FTS。

每个连接启用 `PRAGMA foreign_keys=ON`。成功提交，异常回滚，使用后关闭。`application_id` 标记工程身份，当前 `user_version=2`。受支持的版本 1 会先备份再升级；未知库或未来版本会停止。新增会话、来源和哈希字段见导入格式文档。

## 6. 工程目录

```text
wechat_archive/
├── main.py                       # 直接运行入口
├── pyproject.toml                # Python 工程与可选安装配置
├── Run-Demo.cmd                  # Windows 双击演示入口
├── Run-Web-Demo.cmd              # 双击打开网页演示
├── Run-Web.cmd                   # 双击打开正式库网页
├── README.md
├── wechat_archive/
│   ├── __init__.py
│   ├── __main__.py               # python -m 入口
│   ├── cli.py                    # 命令行
│   ├── demo.py                   # 虚构样例
│   ├── errors.py                 # 业务异常
│   ├── importer/                 # Base/JSON/CSV、校验、报告、Schema
│   ├── migration/                # 逐级迁移管理与 SQL
│   ├── wechat_adapter/            # 接口、mock、映射、PC 预留、android/ 实现
│   ├── database/
│   │   ├── db.py                 # 连接、事务、版本与初始化
│   │   └── init.sql              # 表和索引
│   ├── models/
│   │   ├── user.py
│   │   └── message.py
│   ├── services/
│       ├── chat_service.py       # 可供后续导入模块调用的 CRUD
│       └── browse_service.py     # 网页分页、汇总和消息查询
│   └── web/
│       ├── server.py             # 本机网页与只读 HTTP 接口
│       └── static/               # HTML、CSS、JavaScript、图标
├── examples/
│   └── basic_usage.py
├── tests/
│   ├── test_service.py
│   ├── test_cli.py
│   ├── test_web.py
│   ├── test_importer.py
│   ├── test_migration.py
│   ├── test_wechat_adapter.py
│   ├── test_android_parser.py
│   └── android_fixture.py
├── docs/
│   ├── PHASE1_ACCEPTANCE.md       # 第一阶段历史验收记录
│   ├── PHASE2_ACCEPTANCE.md       # 第二阶段历史验收记录
│   ├── IMPORT_FORMAT.md           # 标准格式和导入说明
│   ├── PHASE3_ACCEPTANCE.md       # 第三阶段历史验收记录
│   ├── wechat_adapter.md          # 微信接入范围与使用说明
│   ├── wechat_mapping.md          # mock 字段映射契约
│   ├── PHASE4_ACCEPTANCE.md       # 第四阶段历史验收
│   ├── android_parser.md          # 输入条件、Schema、只读与解密边界
│   └── PHASE5_ACCEPTANCE.md       # 第五阶段验收
├── android_mock/                 # MicroMsg/账号目录、自建 SQLite 和元信息
├── wechat_mock/                  # export.json 原始模拟输入与 exchange.json 输出
├── import_logs/                  # 本机每次导入报告
└── data/
    ├── chat.db                   # 默认正式库，交付时为空
    └── demo.db                   # 独立演示库
```

源码目录直接运行时，默认正式库固定在项目的 `data/chat.db`，不随启动目录变化。通过 `--db` 或 `ChatService(path)` 指定的相对路径按当前工作目录解释。安装成普通包后，默认路径为 Windows `%LOCALAPPDATA%/WeChatArchive/chat.db`；其他平台为 `~/.local/share/WeChatArchive/chat.db`。演示同目录使用 `demo.db`。

## 7. 验证与阶段边界

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用临时模拟数据库，v0.4.0 原有 99 项保留；新增至少 30 项 Android 检测、读取、映射、失败、只读、路径、去重及 CLI 检查。结果见 `docs/PHASE5_ACCEPTANCE.md`。

SQLite 文件保存本地明文数据；本阶段没有数据库加密、登录、权限隔离或自动备份。未来导入真实聊天时，应先明确数据来源格式和备份方案，再增加解析器。

下一阶段可单独设计解密实现或验证更多真实版本的 Schema。解密应输出新明文快照，再交给当前 Parser，不混入解析器或修改来源。


## Git 与后续 Codex 开发

本地 Git 工作约定见 [Git 工作流](docs/GIT_WORKFLOW.md) 和根目录 AGENTS.md。首次检出运行 `python -X utf8 tools/prepare_fixtures.py` 恢复被忽略的自建测试夹具。真实资料和数据库不进入 Git，软件版本不因普通 Commit 自动变化。远程和正式 Release 需用户另行授权。
