# 思绪 2.2.3 发行回执

2026-10-17。正式版本已发布，非草稿、非预发布。

- Release：[思绪 2.2.3](https://github.com/mxwq1313-collab/Reverie/releases/tag/v2.2.3)，ID `415728207`。
- 发行源码提交：[`9e26e337fe2a0dfe81f1cba26dd905eb0f932bfb`](https://github.com/mxwq1313-collab/Reverie/commit/9e26e337fe2a0dfe81f1cba26dd905eb0f932bfb)；标签 `v2.2.3` 指向该提交。
- 最终工作流：[Windows 2.2.3 release](https://github.com/mxwq1313-collab/Reverie/actions/runs/39023523114)，状态 success。
- [Windows x64 ZIP](https://github.com/mxwq1313-collab/Reverie/releases/download/v2.2.3/Sixu-2.2.3-Windows-x64.zip)，208316203 字节。
- [SHA256SUMS.txt](https://github.com/mxwq1313-collab/Reverie/releases/download/v2.2.3/SHA256SUMS.txt)。

ZIP SHA256：`6ce57fbabfb384da0a7e91484e00542ef9a78f711393d790918d06a3458f7eaa`。

正式 CI EXE SHA256：`61ee80dab3329199556bb3fcad7039898730d3a0006cccafa60de6a2e03cba33`；本机候选 EXE 摘要另记于本地验收，二者不混用。

## 验证

| 检查 | 结果 |
|---|---|
| 版本调整前功能源码完整回归 | 935/935，1054.106 秒，0 失败、0 跳过 |
| 改号后的版本专项与本机最终 EXE | 2/2，五项 5/5 |
| 1024×768 默认窗口上限下的本机发行矩阵 | 13 模块 115/115，无失败、无跳过 |
| 最终线上界面/身份/纹理等专项 | 115/115 |
| 最终线上管理及诊断 | 33/33 |
| 最终线上打包 EXE | desktop / codex / knowledge / sixu / workbench 全部通过 |
| 正式资产独立下载核验 | SHA256 与 GitHub 资产摘要及清单一致，ZIP 全部 1084 个条目 CRC 通过 |
| 版本、来源和运行时 | 文件/产品版本 2.2.3，manifest 绑定发行提交，固定 Codex 两个 EXE 哈希通过 |
| 私有文件与路径 | 无个人数据库、登录状态、路径越界条目 |

两轮早期线上失败分别是新增内部拖动用例与旧的 800 像素 AI 侧栏用例缺少宽屏前置条件。均在本机以 1024×768 最大窗口尺寸复现，补齐对应宽窗口设置并断言 docked 模式，窄屏用例继续覆盖抽屉。没有删除或跳过检查，应用代码未因云端测试失败而调整。失败日志保留在本机 build/r223，并可回查前两轮 Actions：39022640258、39023013746。

## 已知边界

连续拖动窗口边框或内部分栏仍可能明显卡顿，本版没有宣布全面解决闪烁或达到固定帧率。用户在知悉该状态后明确要求以 2.2.3 发布。出现过显示残缺的原生重绘合并仅留作诊断，没有安装到正常应用。

所有本轮测试使用合成数据，不读取真实微信，不发送模型请求。发行 ZIP 包含完整运行目录、固定 Codex 运行时和使用说明。完整解压后运行 Sixu/思绪.exe，保留 _internal。
