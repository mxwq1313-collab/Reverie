# 阶段 B 验收：联系人与头像 · 2026-10-18

范围：wechat_archive/ui/message_widgets.py 的 ContactList、avatar_service.py、patch_release_check.py。

已实现：ID 复用、2ms 创建/3ms 图片投递、120ms 标签去抖、有界缓存/排队、异步头像及有界视口、内容高度校准。

功能状态：最终完整业务 961 项通过，管理工具 33 项通过，五个 EXE 入口通过；本阶段新增用例包含在完整集合中。仅使用合成数据/已有夹具，不调用模型。

性能状态：本次参考检查通过，可保存本阶段代码提交。

```json
{
  "200_False_wall": true,
  "200_False_heartbeat": true,
  "200_True_wall": true,
  "200_True_heartbeat": true,
  "500_False_wall": true,
  "500_False_heartbeat": true,
  "resize_callback_le_8": true,
  "labels_complete_le_150": true
}
```

整体持续拖动仍有 91.0ms 峰值，本阶段通过不等于 P4 或整体流畅度已完成。所有数值、画面检查及未达项目见 [本轮总报告](UI_LAG_FIX_ACCEPTANCE_20261018.md) 与 [数据回执](UI_LAG_PERFORMANCE_DATA_20261018.json)。

版本保持 2.2.3，不推送、不建正式标签或 Release。用户原有未跟踪审查计划保持不变。
