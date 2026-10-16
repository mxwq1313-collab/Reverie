# Windows 桌面版 v0.5.7（2026-10-13）

当前交付是 Windows x64 免安装软件。下载桌面 ZIP，右键“全部提取”，打开 WeChatArchive 文件夹，双击 **ChatArchive.exe**。完整保留同目录 `_internal`，它包含运行库和资源；不要只复制 EXE，不在 ZIP 预览中运行。

## 使用

首次进入仍为已有中文归档窗口。可选择 JSON/CSV/登记的真实微信结构化导出文件，预览、导入、查看报告和聊天。SQLite 归档沿用 Schema 2，交换协议仍为 chat-exchange 1.0；已有归档可继续追加去重。

默认档案为 `%LOCALAPPDATA%\WeChatArchive\chat.db`；报告在同目录 import_logs。程序和数据独立，替换/移走程序文件夹不会自动删除档案。目录只在实际写入时创建，启动空窗口不自动建库。

已有档案：点击“选择归档库”并选择项目 SQLite 文件，检查通过即可点击“查看已导入的聊天”或“导出可读文件”。默认档案存在时启动自动恢复。不是项目库的文件拒绝作为可查看归档，不写原文件。

“查看聊天”仍使用本机浏览器；关闭软件会停止由该窗口启动的服务。“导出可读文件”产生独立 HTML/TXT，之后无需软件或微信即可阅读。

## 与当前真实数据的关系

已有真实归档是源码项目的 data/real_wechat_verified.db，已有真实导出是 outputs/real_wechat_mvp/source_export_cli.json。它们留在本机，没有包含在桌面发布包。可以直接选择这个归档查看，或者选择来源文件导入新的默认档案；重复仍跳过。

桌面 EXE 包含归档平台的导入/校验/去重/显示/可读导出。电脑微信获取工具仍是独立来源步骤，尚未提供窗口一键获取或完整历史分页。没有加入第三方获取 SDK，也没有研究新的备份/Android 格式。

## 验证与边界

本机 Windows 11 x64、Python 3.10.11、PyInstaller 6.22.3 构建。EXE 验收清除了 PATH 中 Python 以及 PYTHONHOME/PYTHONPATH/TCL_LIBRARY/TK_LIBRARY，程序运行前缀为自身 `_internal`；未调用本机 Python 解释器启动。

- 标准文件：首次 3 条、重复 3 条、离线导出 3 条。
- 真实私聊：首次 38 条、重复 38 条、离线导出 38 条；12 条未支持原记录保留。
- Tk 窗口构建、查看按钮和导出按钮、7 个 SQL/Schema/网页资源通过。
- 全量 360 项测试，359 通过、1 项历史权限跳过；原核心文件和归档 32 项指纹一致。
- 真实检查文件只在工作目录，未进入程序包。诊断未自动打开浏览器，未绕过此前的浏览器管理员策略；网页显示仍沿用前阶段用户人工验收，不宣称本阶段进行了真实浏览器截图检查。

EXE 运行验证与源码单元测试分别记录到 outputs/desktop_release 的凭证/日志。打包后还验证从中文/空格路径和任意工作目录运行，整包解压检查与完整性校验。

其他 Windows 机器尚未独立验收，当前没有安装向导、代码签名或自动升级功能。免安装版不要求管理员权限。软件数据路径约定沿用原实现，不重设计后端。

## 重建

开发者在 Windows x64 的独立环境安装 PyInstaller 6.22.3，然后从项目目录运行：

```powershell
python -m PyInstaller --noconfirm --distpath work/desktop_dist --workpath work/desktop_build packaging/windows.spec
```

产物在 work/desktop_dist/WeChatArchive。核心软件无需安装第三方运行依赖；构建工具仅用于开发环境。spec 仅收集 wechat_archive 包内资源，不收集 data、import_logs、用户导出、测试和工作目录。构建后二进制和源码各自生成摘要，验证通过后才交付。

Windows 目录保存遇到短暂拒绝时最多等待重试 1.5 秒，不改权限、不关闭其他进程、不覆盖目标；仍失败则显示错误并清理本次临时目录。

参考：[PyInstaller 分发与构建](https://pyinstaller.org/en/stable/usage.html)、[无控制台运行注意事项](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)。
