# 思绪 2.2.4 发行回执

日期：2026-10-18。

**v2.2.4 已正式发布，且为仓库最新正式版本。** [发行页面](https://github.com/mxwq1313-collab/Reverie/releases/tag/v2.2.4)；[Windows 工作流](https://github.com/mxwq1313-collab/Reverie/actions/runs/39115644152) 已完成且 success。

## 源码与发布

- GitHub main 发行源码提交：981d4c50e1a52eadc71f8eb98153635ad9dafb00；原父提交 1afe163f642280f5b032987e942980e96aee838f 保留，采用快进更新。
- 对应本地提交：acb67fecd0177f1227a8468e0ce6ba1c950e9dca，分支 feature/sixu-mbti-ui。完整源码树 3c1fff613e376022549ea077109aebc2e9796ec1 与上传后的 GitHub 源码树一致；原有推送保护及整个索引隐私检查通过。
- 标签 v2.2.4 指向上述发行源码提交；Release 不是草稿或预发布。
- 按用户明确发布指令纳入已通过功能回归的消息时间线、合并转发和管理页改动；性能门槛未全部通过的结论保留。
- 原有未跟踪卡顿审查计划保留且摘要未变，没有上传；未加入真实聊天、数据库、密钥或登录缓存。

## 已验证结果

- 功能源码在版本调整前完整业务 961/961，0 失败、0 跳过；长合并转发连续 40/40。原始证据见卡顿验收快照。
- 版本调整仅改变应用版本入口与冻结自检的版本字符串，其余功能源码摘要一致；测试末尾空行整理经编译字节比对不改变执行代码。
- 本机 2.2.4 发行专项 141/141（1024×768 默认最大尺寸）、管理 33/33、新 EXE 五项 5/5；文件与产品版本均为 2.2.4，构建期间功能源码未变。
- GitHub Windows：界面与卡顿专项 141/141、管理 33/33，共 174/174，0 失败、0 跳过；18 组 unittest 日志已逐项计数。
- 云端 desktop、codex、knowledge、sixu、workbench 五项 EXE 检查全部通过；固定运行时准备和摘要验证通过；ZIP 创建步骤的完整 CRC 检查通过。
- 正式 ZIP 与 SHA256SUMS.txt 资产均存在；清单已实际下载，其文件摘要与 GitHub API 资产摘要一致，清单中 ZIP 摘要也与 GitHub API 的 ZIP 摘要一致。
- 本机 EXE SHA256：e406bea5fe7f2480e9dc1bed75ffdf6bfd6ffd843fff965835a3619dea5dac75。这是本机构建摘要，不能冒充云端 EXE 摘要。

## 正式资产

- 文件：Sixu-2.2.4-Windows-x64.zip
- 长度：208328588 字节
- GitHub 正式资产 SHA256：a37a3319c437f646d7c7887ba8409a138546a16f101119f53aabf6f700838ce8
- SHA256SUMS.txt 文件摘要：d6dfed07240a8e32f28d4eaecae632dc38014612d69ec4e2e42033c92eede73c
- ZIP 与清单均位于上述 Release，下载后应完整解压并保留 _internal 文件夹。

## 本机下载核验边界

正式 ZIP 与同一成功工作流附件的本机下载都遇到持续低速；已主动停止本轮整包下载，保留部分文件用于审计。**本机没有完成整个线上 ZIP 的独立 SHA256/CRC、PE 版本、发行清单与运行时逐文件复核，这些项目不得记为本机通过。** 云端打包前的检查与实际发行成功已确认；它们与本机复下载是不同证据。

原始回执在忽略目录 build/r224/：ci_matrix_1024.json、management_tests.txt、build_receipt.json、version_source_changes.json、ci_success_summary.json、release_assets.json、publish_receipt.json。部分下载亦留在该忽略目录，未上传源码仓库。

## 剩余性能问题

连续拖动窗口或分隔条仍可能卡顿。500 联系人/300 消息整窗分栏心跳最大约 91.0 ms、p95 89.7 ms；100 条消息初载与管理页首次显示仍有超目标峰值。发布不代表上述性能门槛已通过。详见[卡顿验收快照](UI_LAG_FIX_ACCEPTANCE_20261018.md)和[发行说明](SIXU_2_2_4_RELEASE.md)。
