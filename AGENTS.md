# 聊天归档项目：Codex 开发与 Git 工作约定

本目录是实际聊天归档源码和 Git 根目录。先确认位置，不要把同名导出目录、打包目录或其他应用工作区当作源码。遵守用户当前指令、用户级知识库 Hook 和本文件；不要重复手工写入已由 Hook 自动记录的问答。

## 任务开始

1. 阅读 PROJECT_CONTEXT.md、TODO.md、CHANGELOG.md、README.md；按任务读取相关模块和 docs/GIT_WORKFLOW.md。
2. 执行 `git rev-parse --show-toplevel`、`git status --short --branch`、`git branch --show-current`、`git log -5 --oneline`、检查远程与本地暂存区。远程 URL 如含凭据，先脱敏，不能打印令牌。
3. 记录用户已有未提交/已暂存修改与未跟踪文件。保留它们，不能覆盖、清理、丢弃或混入本次提交；需要编辑重叠文件时先读差异并保留用户内容。
4. 按一个可验证的功能组织任务。复杂功能或并行维护需要隔离时，可创建 `feature/<短英文主题>`、`fix/<主题>`、`docs/<主题>`、`chore/<主题>` 分支。不要擅自移动或删除已有分支；不要通过 stash 掩盖未知修改。

## 实现、验证和提交

1. 继续使用项目既有数据/业务管线。不得把真实聊天、来源数据库、账号缓存、解密密钥、凭据、私有报告、打包产物写入 Git。审查暂存内容，不能只依赖 .gitignore。
2. 首次干净检出先运行 `python -X utf8 tools/prepare_fixtures.py`。它只使用现有 tests/android_fixture.py 自建数据，不读取真实微信，也不覆盖已有夹具。
3. 完成一个可验证的单元，运行与风险相符的测试并记录命令/结果。全量基线/重要兼容变更运行 `python -X utf8 -m unittest discover -s tests -v`；管理脚本运行 `python -X utf8 -m unittest discover -s tools/tests -v`。只读文档修改做对应校验，不无意义地重复全部测试。
4. 重要变更同步 CHANGELOG.md、PROJECT_CONTEXT.md、TODO.md 与相关使用/接口文档，区分已实现、已验证、待验证和计划。普通功能 Commit **不自动提高正式软件版本号**。
5. 经验证后自动创建清晰中文 Commit，如 `feat: 增加会话日期筛选`、`fix: 修复分页阅读位置`、`docs: 更新导出说明`、`chore: 完善本地 Git 检查`。无需对已授权的普通本地提交重复询问。
6. 仅显式暂存本任务涉及且验证过的路径/差异；禁止无差别 `git add .`、`git add -A`、`git commit -a`。先检查 `git diff`、`git diff --cached`、`git diff --cached --check`，运行 `python -X utf8 tools/git_privacy_check.py --staged`。若用户已有暂存文件，不把它们带入自动提交；采用独立索引/明确路径或先与用户协调，禁止擅自取消其暂存。
7. 不提交失败、验证不明或含敏感内容的改动。内容检测是防误提交，不替代人工审查；新样例的豁免需确认确为自建数据后更新审查清单。

## 必须先获得用户明确批准

- 强制推送、历史重写（含 amend/rebase/filter/reset 历史）、丢弃修改、清理未跟踪文件、删除分支。
- 发布正式 Release、创建正式版本标签或上传发行包。
- 添加/改动远程和任何推送，尤其推送到新远程。不得把配置许可当作推送许可。
- 更改全局 Git 身份/配置、绕过本地隐私检查或推送保护。

本地 pre-push 默认拒绝推送。用户明确批准具体远程/分支后，可仅在该次命令设置 `WECHAT_ARCHIVE_APPROVED_PUSH=1`；变量本身不是授权，不能为了通过检查而自行设置。不得使用 `--no-verify` 绕过钩子。

## 任务结束必报

当前分支、Commit 完整或可辨识 ID/中文摘要、测试通过/失败/跳过及原因、Git 工作区与用户原有修改状态、远程同步情况（没有 push 就明确未同步）。若不能提交，说明具体阻塞和已保留的文件，不虚构 Commit。

本次首次基线只记录当前已验证的真实 v0.8.0 快照；原 CHANGELOG 历史文本保留，但不得补造旧版本 Commit 或发布标签。
