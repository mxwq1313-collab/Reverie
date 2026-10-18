# 阶段 C 验收：消息时间线与滚动索引 · 2026-10-18

> 2026-10-18 发行状态更新：本文保留版本调整前的阶段验收快照。用户随后明确要求发布 2.2.4，功能回归通过的 C/D 改动已决定纳入本轮发行；性能门槛仍未全部通过。当前发行状态见 [2.2.4 回执](SIXU_2_2_4_RECEIPT.md)。

范围：wechat_archive/ui/message_widgets.py 的 BubbleTimeline。

已实现：共享菜单、时间预算、统一布局、增量测量、长跨度有界视口、同步迁移、稳定估高、深色首次滚动、合并转发逻辑坐标、切换会话时关闭旧菜单。

功能状态：最终完整业务 961 项通过，管理工具 33 项通过，五个 EXE 入口通过；本阶段新增用例包含在完整集合中。仅使用合成数据/已有夹具，不调用模型。

性能状态：部分峰值参考检查未通过；本阶段代码保留为工作区候选，按审查计划不提交。

```json
{
  "timeline_100_wall": true,
  "timeline_100_heartbeat": false,
  "timeline_300_wall": true,
  "timeline_300_heartbeat": true,
  "timeline_append_100_wall": true,
  "timeline_append_100_heartbeat": true,
  "scroll_le_5": true
}
```

整体持续拖动仍有 91.0ms 峰值，本阶段通过不等于 P4 或整体流畅度已完成。所有数值、画面检查及未达项目见 [本轮总报告](UI_LAG_FIX_ACCEPTANCE_20261018.md) 与 [数据回执](UI_LAG_PERFORMANCE_DATA_20261018.json)。

版本保持 2.2.3，不推送、不建正式标签或 Release。用户原有未跟踪审查计划保持不变。
