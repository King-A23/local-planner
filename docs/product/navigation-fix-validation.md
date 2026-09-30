# 原生导航中断修复与验证

2026-09-30，分支 `codex/daily-experience`，基于 `9db0d0c` 的修复。对应[继续验收记录](acceptance-20260930.md)中已确认的 `Frame load interrupted` 偏差。

## 原因与修复

修复前在独立原生副本中重复快速 `Cmd+2 → Cmd+1 → Cmd+R`，再次出现“Local Planner 无法打开”弹窗。仅在诊断副本加入错误日志，确认实际错误为 `WebKitErrorDomain / 102 / Frame load interrupted`。本机 SDK 的 `WebKitErrors.h` 将 102 定义为 `WebKitErrorFrameLoadInterruptedByPolicyChange`。此前主窗口只按编号忽略 `NSURLErrorCancelled`，把这类导航中断交给了要求退出的启动失败流程。

新增独立的 `NavigationFailure.isExpectedInterruption` 分类函数。只有 `NSURLErrorDomain / NSURLErrorCancelled` 和 `WebKitErrorDomain / 102` 会忽略，主窗口和设置窗口共用；连接失败、其他 WebKit 错误和无关错误域的同编号错误仍走原来的提示。识别不依赖本地化错误文案。已忽略的中断会输出错误域与编号，不记录计划内容或 URL。

macOS 构建脚本纳入新 Swift 文件。应用入口改为 `@main` 以支持多文件编译，用 `withExtendedLifetime` 保持 AppDelegate 在应用运行期间存活。

## 逐项验证

证据位于忽略目录 `build/navigation-fix-20260930/`，模型指令只包含人工验收需求。

| 验证 | 预期 | 实际与证据 |
| --- | --- | --- |
| 修复前复现 | 原偏差能够重现并确认错误类别 | 诊断副本重复快速切页/刷新后弹窗；`diagnostic.log` 明确 domain=WebKitErrorDomain、code=102；`before-error.txt`、`before-error.png` 保存失败界面 |
| Swift 分类回归 | 精确忽略两类中断，真实失败仍报告 | 编译实际生产 Swift 分类函数并执行 8 个断言：网络取消、策略中断、连接失败、不能展示 URL、内容进程终止、两个无关域同编号、仅文案相同的连接失败；全部通过 |
| 空闲时原生快速切页/刷新 | 不再弹出失败窗口，页面仍可用 | 20 轮 `Cmd+2 → Cmd+1 → Cmd+R` 后今天页正常；日志实际处理 17 次错误102；`after-20-rounds.txt`、`after-20-rounds.png` |
| 真实助手暂停时快速切页/刷新 | 保留同一 run、暂停计时和计划数据 | 既有 `Codex · GPT-6 Luna · medium` 执行只读等待指令，暂停后再重复 20 轮；仍是 paused，同一 ID、elapsedSeconds=25.2、数据库逻辑摘要均不变；两组主窗口测试累计实际处理37次错误102；`agent-paused-before.json`、`agent-paused-after.json`、`after-paused-20-rounds.txt`、`after-paused-20-rounds.png` |
| 恢复执行 | 原 run 可以继续并完成，无额外写入 | 原 run `4ee1b044-7007-4fb7-905d-c4d00fdea068` 完成，界面回复等待结束、没有发现计划改动，数据库逻辑摘要不变；`agent-result.json`、`agent-finished.txt` |
| 设置窗口连续刷新 | 共用分类逻辑，设置窗口仍可用 | 设置窗口连续10次 Cmd+R，六个分区正常显示；最终累计实际处理40次错误102；`settings-reloads.txt`、`fixed-native.log` |
| 构建与签名 | 新代码可生成完整安装包 | 前端 TypeScript/Vite、Python 后端打包和 Swift 编译成功，ad-hoc 签名验证通过；最终 native 源码重新编译后更新签名及 ZIP，ZIP 完整性检查通过且内含原生二进制与 `.app` 相同；`build.log`、`final-check.json` |

- `.venv/bin/python -m pytest -q`：363 项通过，包含新增 Swift 回归，以及真实后端父进程退出清理与忙端口隔离测试。日志 `pytest.log`。有一条 TestClient 依赖弃用警告，无测试失败。
- `.venv/bin/python -m pytest -q tests/test_desktop.py`：6 项通过，日志 `desktop-tests.log`。
- `npm test --prefix web`：20 项通过，日志 `frontend-tests.log`。
- `git diff --check` 通过。

没有因工具未能确认物理输入法、跨应用热键或拖动/把手焦点而修改这些交互；[原验收报告](acceptance-20260930.md)中的相关未验证状态保留。本次不将错误分类断言算作真实网络故障的原生弹窗验收，也不声称覆盖所有导航错误。

## 数据、Git 与收尾

诊断副本数据库为 `build/navigation-fix-20260930/diagnostic-data/planner.sqlite`，修复副本数据库为 `build/navigation-fix-20260930/fixed-data/planner.sqlite`，均新建。测试应用 bundle ID 为 `local.planner.navigationfix20260930`，仅监听 `127.0.0.1:18787`。启动后先核对日志数据路径及 PID，再连接界面工具，没有本轮默认数据目录启动异常。Luna 分组只复制配置并添加测试目录 `--cd`，不将真实计划传给模型。

隔离验收开始与结束 HEAD 仍为 `9db0d0c`，当时修复尚未提交、推送或安装。开始已有的两份验收记录、研究文稿与截图均保留；研究文稿和五张截图逐文件 SHA-256 保持相同。真实数据库逻辑 SHA-256 仍为 `4e699a9adbf1c4228796d099f7d75161cec8c1a42dc56a3e1a2af207c051b96c`，测试前后相同；验收期间已安装原生执行文件哈希也未变。

新版产物为 `dist/macos/Local Planner.app` 和 `dist/macos/Local-Planner-macOS-arm64.zip`，最低 macOS 26.0，与此前构建环境一致。

**PROCESS_CLEANUP_COMPLETE**：诊断副本退出后，才更新测试副本并启动修复验收。最后通过 Cmd+Q 退出修复副本，核实原生 PID `59330`、后端 `59335` 及其模型进程退出，18787 无监听。用户原有 8787 服务 PID `88080` 保留运行。开始与结束证据分别为 `baseline.json`、`final-check.json`。

## 后续安装与发布

同日用户授权“安装并推送”。安装前确认已安装应用未运行，通过 SQLite backup API 保存数据库，并将旧应用保留在 `build/install-navigation-fix-20260930-112911/Local Planner.before-navigation-fix.app`。数据库备份为同目录 `planner-before-install.sqlite`，安装证据为 `installation.json`。这些文件留在忽略目录。

新版安装到 `~/Applications/Local Planner.app`。先复制到临时应用目录并核对签名，再替换原应用；替换后签名验证通过，安装目录逐文件及符号链接与已验证构建产物一致。安装前后真实数据库逻辑摘要相同。没有启动真实数据目录的测试实例，原8787服务保持运行。

本次发布分支为 `codex/daily-experience`，包含修复、Swift 回归测试和三份验收记录。原有未跟踪研究文稿与截图不纳入提交。安装与推送过程不保留新增后台进程，收尾状态为 **PROCESS_CLEANUP_COMPLETE**。
