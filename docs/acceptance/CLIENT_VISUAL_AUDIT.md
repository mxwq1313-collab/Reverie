# 客户端审美修补验收

2026-10-14，初始基线86dfc75，feature/archive-platform-v0-9，正式内置版本0.8.0。

客户端专项 76/76 通过；全量 653 项，652 通过、0 失败、1 个既有 Windows 符号链接权限跳过；管理 15/15 通过。 Windows 开发包已构建；无外部 Python PATH 的导入导出、工作台/Copilot、知识与独立无登录 Codex 四项 EXE 探测均通过。

命令：

```powershell
python -B -X utf8 tools/prepare_fixtures.py
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 -m unittest discover -s tools/tests -v
```

专项共76项，模式为test_workbench.py、test_copilot_ui.py、test_client_streaming.py、test_client_keyboard.py、test_client_retry.py、test_knowledge_ui.py、test_import_ui.py。项目管理检查首次在普通沙箱无法写临时Git仓库配置，保留失败记录后在获准的环境重新运行15项，全部通过。

8个UI修改文件之外100个运行时文件哈希与基线一致；117个未涉及视觉构建的方法AST与基线一致，原有按钮command回调一致。五组正常文字对比度均大于4.5:1。证据保存在本地隔离验收目录，不含个人聊天或凭据，不入Git。

修补前合成窗口经Computer Use检查并保存真实截图；用户通过Esc停止Computer Use，因此修补后的主观审美、截图和实际系统DPI验收尚未完成。程序布局通过不代表人工外观通过。官方Codex页面视觉查看被浏览器管理策略阻止，不声称已取得精确设计规范。完整差距/措施见[审美报告](../CLIENT_VISUAL_AUDIT.md)。

独立EXE四项探测均在无外部Python PATH下通过，工作台探测包含六项既有体验和Copilot第一阶段；不登录、不发送真实模型问题。EXE SHA-256：c267a766ba0e8b50a9c361c8ca7b496770ea8ce2f8a91fa66aec3b6609743422。交付时保留完整_internal目录，不覆盖旧开发包或个人配置。
