# 阶段 A 验收：流式尾部渲染 · 2026-10-18

范围：wechat_archive/ui/agent_panel.py、rich_markdown.py。

已实现：局部文本/标签、130ms 合并、引用与链接清理、Unicode、选区和主题阅读位置。

功能状态：最终完整业务 961 项通过，管理工具 33 项通过，五个 EXE 入口通过；本阶段新增用例包含在完整集合中。仅使用合成数据/已有夹具，不调用模型。

性能状态：本次参考检查通过，可保存本阶段代码提交。

```json
{
  "render_p95_le_30": true,
  "heartbeat_le_60": true,
  "final_le_100": true
}
```

整体持续拖动仍有 91.0ms 峰值，本阶段通过不等于 P4 或整体流畅度已完成。所有数值、画面检查及未达项目见 [本轮总报告](UI_LAG_FIX_ACCEPTANCE_20261018.md) 与 [数据回执](UI_LAG_PERFORMANCE_DATA_20261018.json)。

版本保持 2.2.3，不推送、不建正式标签或 Release。用户原有未跟踪审查计划保持不变。
