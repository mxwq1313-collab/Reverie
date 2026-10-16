# 本地 Git 与 Codex 开发工作流

2026-10-13。实际项目版本 v0.8.0；本次只建立管理体系，不改变业务功能或软件版本，不上传、不建正式 Release、不补造历史提交。

## 第一次使用和正确工作目录

在实际聊天归档源码根目录开启后续 Codex 项目/聊天，根目录 AGENTS.md 才能作为本项目指令入口。不要从文栖目录或 Windows 打包副本开展聊天归档开发。Codex 按项目根目录到当前目录读取指导文件，见 [官方 AGENTS.md 文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。当前文件创建不等于已经验证新的 Codex 会话自动加载。

初始化后的本地配置：main 分支、用户批准的仓库级作者身份、UTF-8 提交编码、core.hooksPath=.githooks、core.autocrlf=false。不改用户全局配置。Git 作者邮箱写入本地提交元数据；GitHub 账户认证和远程仓库是独立配置，注册邮箱不会自动创建连接。

新检出先配置本地钩子，再生成被排除的自建夹具：

```powershell
git config --local core.hooksPath .githooks
git config --local core.autocrlf false
python -X utf8 tools/prepare_fixtures.py
python -X utf8 tools/git_privacy_check.py --staged
```

作者身份只使用自己确认的姓名/邮箱；不要复制其他开发者的仓库级身份。Windows .cmd/.ps1 在正常检出时使用 CRLF，Python/Markdown/钩子使用 LF。源码里的既有 Android 生成器创建虚构数据；夹具目录不完整时拒绝覆盖。数据库及其元信息保持在被忽略的 android_mock 目录。

## 每项开发

1. 查看 git status、当前分支、最近提交和用户已有差异/暂存内容。
2. 按功能组织，必要时 `git switch -c feature/主题`；不自动删除旧分支或丢弃修改。
3. 实施和验证。通常运行相关业务测试；重要兼容修改执行完整 `python -X utf8 -m unittest discover -s tests -v`。管理脚本测试为 `python -X utf8 -m unittest discover -s tools/tests -v`。
4. 更新重要变更记录和相关文档。普通提交不修改 pyproject.toml、__version__ 或 Windows 正式版本。
5. 明确暂存本任务路径，例如 `git add -- AGENTS.md docs/GIT_WORKFLOW.md`。检查 git diff --cached 和 --check，再运行暂存内容隐私检查。用户原有暂存内容必须隔离，不混入自动提交。
6. `git commit -m "fix: 修复具体问题"`，主题写清实际变化与目的。普通已授权本地提交自动完成。
7. 报告分支、Commit ID、测试结果、工作区/原有修改状态和远程是否同步。

首次基线是当前已验证 v0.8.0 的一个快照，含本次管理文件。CHANGELOG 原有 0.1–0.8 开发记录只是保留的文档，不对应新造的历史 Commit。不会因为建立 Git 而自动打版本标签或创建 Release。

## 隐私与钩子

.gitignore 排除真实数据库/日志/来源、密钥/环境变量/登录缓存、私有验收、缓存与打包产物。它不移除已经被跟踪的文件；`tools/git_privacy_check.py` 检查整个实际索引的 blob，发现已有受限文件同样阻止提交，并只报告路径/类别，不打印敏感值。

pre-commit 检查路径、已知密钥/令牌/微信标识模式、未审查导出与二进制。已审查自建样例在 tools/privacy_fixtures.json 登记索引 blob 的 SHA-256；夹具内容变化需重新审查。未暂存的清单修改不能放行索引里的聊天导出。即使登记清单也不允许数据库或凭据路径。

这是防误提交机制，不能代替人工内容审查或用户授权；不要用 --no-verify 绕过。发现已跟踪敏感内容时先报告，保护原文件，按具体授权决定解除跟踪/后续处理；不自动重写历史。

pre-push 默认拒绝推送。取得具体远程/分支的明确批准后，仅该次命令可以设置 WECHAT_ARCHIVE_APPROVED_PUSH=1；普通许可仍不允许删除引用或非快进覆盖。变量不是授权本身。当前任务未配置远程，也未发送 Git 文件。

## GitHub 是否必须

本地版本管理、分支和 Commit 不需要 GitHub。若以后需要异地备份或协作，再由用户选择并授权具体仓库、认证方式、添加远程和首次推送；先复核拟上传的整个历史和隐私。强制推送、历史重写、清理/丢弃、分支删除和正式 Release 均需单独批准。


## 本轮验收

管理机制 15 项通过；索引干净检出不含任何数据库，自建夹具生成后业务回归 440 项：439 通过、0 失败、1 个原有 Windows 符号链接权限跳过。业务与打包文件指纹逐文件一致。Git 隐私检查覆盖实际索引；详情见 GIT_WORKFLOW_ACCEPTANCE.md。

现有 Markdown 硬换行和 operation_actions.py 的历史 EOF 空行采取窄范围 whitespace 属性例外，原文件没有被清理。以后实际修改该代码时可单独处理 EOF 并撤销对应例外。
