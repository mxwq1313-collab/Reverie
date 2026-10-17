# 思绪 2.3.0 当前工作状态

> 后续决定：用户明确要求以 2.2.3 发布当前已回归的功能修复，并保留剩余卡顿说明。以下是更早的 2.3.0 排查保存记录；当前发行状态见 [2.2.3 发布说明](SIXU_2_2_3_RELEASE.md)。

2026-10-17。本文件供续作定位；详细技术依据、失败实验和验收边界见 [验收记录](SIXU_2_3_0_READINESS.md)。不要从旧工作目录、交付 EXE 或历史报告重新开始。

## 权威工作区

- 实际源码仓库：当前包含本文件的 `wechat_archive` Git 根目录；分支 `feature/sixu-mbti-ui`，HEAD `c728f922086f3db672859ab35b56d0aa5d3a027c`。
- 主窗口为 Python/Tk 桌面应用；旧 `wenxi-demo` 顶层网页不是优化目标。
- 已保留的生产修改：工具精简/随机回忆迁回工具、提示稳定、真实持续布局、完整周期背景纹理、滚动意图和失效控件修复、实时内部分栏与捕获取消。
- 当前完整回归 935/935、管理 33/33、`build/r23i/Sixu/思绪.exe` 五项通过。EXE 元数据 2.2.2，源码与构建哈希已核对。
- 尚未发布 2.3.0；无本轮 Commit、推送、标签、PR 或 Release，真实暂存区未改。

## 性能结论

普通候选用户确认黑条消失但仍明显卡顿。PostMessage 原生合并用户反馈仍有黑条/闪块/布局异常，因此只保留显式诊断入口 `tools/windows_paint_candidate.py`，正常应用没有安装钩子。

直接 Tcl C API idle 原型改善计时，但录像中 AI 控件残缺；补齐移动子树的原型抽样恢复完整，只对实际移动子树处理的纯计时改善约 13%，尚不能宣布目标达成。原型均留在忽略的 `build/r231/paint_tcl_{idle,subtree,exposure}.py`，没有进入生产。

WM_TIMER 饥饿、直接在原生回调调用 Python Tk、CS_OWNDC、没有实际尺寸变化的虚假快计时均已排除。隔离 Tk 8.6.15 无明显收益，未修改系统或应用运行时。

## 最新证据与复测

- 全量：`build/r231/full_regression.txt`；管理：`management_accepted.txt`。
- 构建/五入口/哈希：`packaging_final.txt`、`packaged_checks_final.json`、`frozen_source_integrity.json`。
- 纯计时：`native_live_compare.json`、`tcl_idle_held_fixed.json`、`tcl_exposure_compare.json`，均包含真实宽度与前台断言。
- 画面：`human_live`、`human_combined`、`tcl_idle_wgc`、`tcl_subtree_wgc`、`human_exposure` 的 JSON/MKV/原生帧时间戳；部分录制失败如实标记，不能抹去。
- `tools/windows_resize_probe.py` 可限定本合成进程收集 CPU/GDI、窗口消息、调用栈及录像；纯计时必须去掉原生钩子/采样/录像并保持前台。WGC 可选依赖仅在 `build/r231/capture_deps`。
- 自动内部拖动必须使用单调递增的事件 time，检查实际宽度变化；时间戳 0 会把后续 Press 误认为双击。启动 gate 只在 Computer Use 激活窗口成功后创建；用户输入打断时不能仍然启动。
- API `sky.drag` 没有持续轨迹参数，程序拖边只产生一次尺寸变化，不能冒充真人连续拖动。

## 继续顺序

先读取最新人工反馈与完整录像，再决定是否继续改原生重绘或另找 Tk/GDI 热点。已有明确视觉失败的方案不能以计时较快为理由发布。采用新方案后需重新完整回归、真正的 2.3.0 版本构建和五项打包验证。

发布已有用户授权，但以流畅度/视觉/功能/打包全部通过为条件；条件未满足时保持 2.2.2。发布到 origin 时保留远程 main 既有历史，无 force、无绕过钩子。按仓库约定显式路径审查、隐私检查；不把 build、录像、私有数据或失败原型提交。不要覆盖运行中的旧 EXE。


## 最新人工采集的实际状态

`build/r231/human_exposure.json`：窗口保持前台 100 秒，但内部宽度变化 0、外框变化 0；WGC 仅 2 个静止源帧。编码与解码技术状态为通过，**拖动验证无效**，不能作为视觉或卡顿通过的依据。最新实际移动子树原型尚无有效人工拖动结论；早先普通候选仍卡、PostMessage 组合仍异常的人工结论保持有效。当前没有运行中的合成采集窗口。
