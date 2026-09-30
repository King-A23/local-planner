# 2026-09-30 继续验收记录

验收分支 `codex/daily-experience`，开始与结束 HEAD 均为 `9db0d0c`。本轮只新增验收记录，不修改应用代码，不构建、不安装、不提交或推送。

## 结论与偏差

发现一项原生偏差：普通助手执行期间，连续发送 `Esc → Cmd+1 → Cmd+R`，主窗口弹出 **“Local Planner 无法打开 / 页面加载失败：Frame load interrupted”**，只有退出或查看日志并退出入口。预期是切页、刷新仍能使用窗口并保留执行状态。本轮实际发生一次；页面稳定后单独刷新通过，不将后者作为前者的修复或否定。已立即报告，未修改代码。

证据：[错误截图](../../build/acceptance-20260930/native-navigation-load-failure.png)、[窗口可访问文本](../../build/acceptance-20260930/native-navigation-load-failure.txt)、[当时的执行结果](../../build/acceptance-20260930/clarify-after-load-error.json)。出现弹窗时后端仍可访问，助手最终完成澄清且无数据改动。源码 `desktop/macos/LocalPlanner.swift` 的 `didFailProvisionalNavigation` 会将主窗口的非 `NSURLErrorCancelled` 错误送入失败窗口；尚未证明该次 WebKit 错误的数值和完整触发条件。

物理中文输入法、跨应用全局热键、原生拖动排序与把手键盘排序等尚未完成可靠验收，见下表。自动化通过不替代这些未验证项目。

## 环境与隔离

- 原生应用复制到 `build/acceptance-20260930/Local Planner QA.app`，仅修改测试副本的显示名、bundle ID 并重新 ad-hoc 签名。bundle ID 为 `local.planner.acceptance20260930`。
- 测试副本所用原生执行文件与后端执行文件，与用户已安装应用的对应文件 SHA-256 相同；证据：[产物比较](../../build/acceptance-20260930/artifact-comparison.json)。
- 原生数据库新建于 `build/acceptance-20260930/native-data/planner.sqlite`，测试工作目录为 `build/acceptance-20260930/model-work/`。实际启动日志确认此路径，仅监听 `127.0.0.1:18787`。
- 应用内真实模型测试仅使用现有 `Codex · GPT-6 Luna · medium` 分组，保留模型、medium 和 fast 配置，仅在测试配置中添加独立 `--cd`。所有模型指令从隔离应用内发送，CLI 前缀指向隔离数据目录。
- 并行领域验收只使用一个 `gpt-6-luna` 子 agent；其全新数据库为 `build/acceptance-20260930/domain-unit/acceptance.sqlite`，不调用应用内模型、不启动服务器。详见[领域验收记录](acceptance-20260930-domain.md)。
- 真实 `8787` 服务（开始 PID `88080`）未接收测试 HTTP 请求或测试写入，始终保留运行。

### 启动过程的隔离异常

最初由短命 shell 启动的测试副本没有存活；界面工具的 `getApp` 自动重新启动它时未继承 `LOCAL_PLANNER_DATA_DIR`，因此曾启动了使用默认数据目录的测试副本后端。发现独立目录没有启动日志后立即关闭（原生 PID `57099`、后端 `57100`），未进行测试操作，也未启动模型。随后改用 `start_new_session=True` 启动，核对日志、端口和路径后才开始验收。

该次意外启动后以及整轮结束时，真实数据库的只读 SQLite 逻辑摘要都与开始一致。不能将本轮描述为“测试副本从未打开真实数据目录”；可以确认未向真实计划发送测试写入，数据库逻辑内容未变。该操作异常不记为产品偏差。

## 逐项验收

证据根目录为 `build/acceptance-20260930/`。表内文件名均相对此目录。文中的“本轮操作记录”指[原生操作证据摘录](../../build/acceptance-20260930/native-actions.md)，整理自本轮界面工具返回值。通过项仅覆盖实际列出的操作，不代表任意自然语言或所有键盘组合均正确。

| 项目 | 预期 | 实际结果 | 状态与证据 |
| --- | --- | --- | --- |
| 候选行动加入待办再加入今天 | 首次落地才创建 Task，之后复用同一身份 | 原生行动菜单用方向键/回车加入待办，再点击加入今天；两次 Task ID 均为 `8c581e7c-4d17-4c9e-a85c-fe8511be2d3b`，界面显示已在今天 | 通过；`native-materialized-inventory.json`、`native-materialized-today.json` |
| 重复落地请求 | 同一 requestId 不重复创建 Task | 独立数据库断言通过，两个目的地均核对身份和数量 | 通过；`domain-unit/evidence.json` |
| 关联已有正式任务 | 行动加入今天复用已有 Task ID | 独立数据库关联、落地后 ID 保持相同 | 通过；`domain-unit/evidence.json` |
| 正式任务完成回流 | Action 使用正式 Task 完成状态，不重复创建 | 原生勾选完成，短暂确认反馈后进入折叠的已完成区；Action 同 ID 且 completed=true | 通过；`native-completion.json`、`native-completed-collapsed.txt` |
| 取消完成、删除与撤销 | 状态回流，撤销恢复原 Action/Task 身份 | 独立数据库中完成/取消完成通过；删除 Task 后行动行移除，撤销恢复原 Action ID 与 Task ID | 通过，领域/API 验收；`domain-unit/evidence.json`，本轮未重复原生删除操作 |
| 全局用助手规划入口 | 准备全局持久草案，以 planning 模式运行 | 空规划页点用助手规划，准备草案后发送；run.mode=planning、surface=goals、绑定全局 draftId | 通过；`planning-run-start.json`、`planning-draft-start.json` |
| 全局真实规划生成 | 草案产生结构，正式目标和 Task 不变 | Luna 生成 1 个目标、2 个阶段、2 个候选行动；正式目标及待办仍为空 | 通过；`planning-generated.json`、`formal-generated.json`、`inventory-generated.json`、`planning-generated-native.png` |
| 草案刷新保留 | Cmd+R 后仍能预览同一草案 | 原生刷新后仍显示 5 项待保存调整、目标与阶段 | 通过；`planning-generated-native.txt` 与本轮操作记录；独立持久化断言在 `domain-unit/evidence.json` |
| 保存规划 | 保存只更新目标结构，不创建 Task | 原生保存后显示已保存及还原入口；待办保持为空 | 通过；`after-save-inventory.json`，领域独立计数在 `domain-unit/evidence.json` |
| 还原保存 | 最近一次保存可还原；保留历史语义 | 原生还原后新目标归档为 ended/abandoned，仍无 Task；草案列表为空 | 通过；`after-revert-goals.json`、`after-revert-drafts.json` |
| 目标详情助手入口 | 准备当前目标草案，不进入普通执行 | 恢复测试目标后点用助手调整；run.mode=planning、surface=goal、goalId 与 scopeGoalId 对应当前目标 | 通过；`scoped-run-start.json`、`scoped-after.json` |
| 局部调整及任务保护 | 只修改指定阶段成果，ID 和正式任务保留 | Luna 只改变 `/goals/0/phases/0/outcome`，正式成果和任务保持原值 | 通过；`scoped-diff.json`、`scoped-formal-unchanged.json`、`scoped-adjustment-native.txt` |
| 撤销修改、放弃草案 | 撤销恢复草案基线；放弃不改正式规划 | 原生撤销后成果恢复原文，再放弃关闭草案和助手；独立数据库逐操作断言通过 | 通过；`domain-unit/evidence.json` 与本轮原生操作记录 |
| 草案并发冲突 | 过期 revision 拒绝覆盖 | 独立数据库过期版本返回 HTTP 409 | 通过；`domain-unit/evidence.json` |
| 普通助手澄清 | 同名事项先询问，不猜测写入，回复直接展示 | 待办与明天各有同名周报；两次 Luna 都问选择哪一个。第一次整库逻辑摘要不变，第二次界面显示助手已回复/没有发现计划改动 | 通过；`clarify-before.sha256`、`clarify-after.sha256`、`clarification-native.txt`、`clarification-native.png` |
| 普通助手暂停 | 挂起本机进程，暂停时间不计入，数据不写入 | 点击暂停后 Codex PID `57689` 为 `Ts`；两次观测 run ID、elapsedSeconds=23.7、数据库摘要相同 | 通过；`paused-proof-1.json`、`paused-proof-2.json`、`paused-native.txt` |
| 暂停状态切页、刷新、收起 | 顶部保留暂停状态，重新打开可继续 | Esc 收起、Cmd+2 切页，页面稳定后单独 Cmd+R；顶部仍显示助手已暂停，打开后仍能继续 | 通过；`paused-proof-2.json` 与本轮原生操作记录 |
| 同指令继续 | 恢复同一个 run，使用原发送上下文 | run ID 保持 `0ecb30ed-6122-4ba9-9889-236696f298d1`；当时在待办页，继续后只在原来的今天新增一项 | 通过；`pause-resume-start.json`、`pause-resume-result.json`、`pause-resume-day.json`、`pause-resume-native.txt` |
| 暂停后修改指令 | 结束旧 run，保留已提交改动，新 run 读取当前数据 | 按新指令继续按钮和说明出现；旧 run stopped、新 run succeeded；只出现新标题，旧标题未创建 | 通过；`replace-old-stopped.json`、`replace-new-result.json`、`replace-inventory.json`、`replace-prompt-native.txt`、`replace-result-native.txt` |
| 停止本次 | 终止当前 run，不虚报回滚 | 写入前点击停止，本次 stopped；没有创建预定测试标题 | 通过；`stop-result.json`、`stop-inventory.json` |
| 快速切页并立即刷新 | 保持窗口可用、执行状态不丢 | `Esc → Cmd+1 → Cmd+R` 出现 Frame load interrupted 失败弹窗，必须退出该窗口流程 | **偏差**；`native-navigation-load-failure.png`、`native-navigation-load-failure.txt` |
| 鼠标菜单与完成 | 右键和菜单入口可操作，完成后收纳 | 右键打开事项菜单；目标与行动菜单可操作；完成后已完成区折叠显示 1 项 | 通过；`native-menu-end.txt`、`native-completed-collapsed.txt` |
| 菜单键盘导航 | 方向键/回车执行；Home/End 定位，Esc 关闭并可重开 | 用方向键/回车恢复目标及行动加入待办；End 选删除、Home 选编辑详情；Esc 后 Shift+F10 重开同一事项菜单 | 通过；`native-menu-end.txt`、`native-menu-home.txt`、`native-menu-shift-f10.txt` |
| 事项/阶段鼠标拖动排序 | 拖动把手改变顺序并保留其他成员 | 工具一次返回 noWindowsAvailable；另一尝试选中文字，未完成可靠把手拖动 | **未验证**；不能据此判定产品拖动失败。纯排序逻辑测试通过，但不替代原生拖动 |
| 把手 Option+方向键排序 | 聚焦把手后移动事项/阶段 | 尝试 AX 点击及 Tab 导航，未可靠聚焦目标把手，顺序未变化 | **未验证**；不能据此判定产品排序失败 |
| 设置分区方向键/Home/End | 键盘选择分区 | 本轮鼠标选分区正常；AX 点击后发送 End 未确认分区焦点，未完成可靠键盘验收 | **未验证** |
| 原生页面快捷键 | Cmd+1/2/3/4 切页；Cmd+, 设置，Cmd+W 仅关设置 | 四个页面快捷键均到对应路由；独立设置关闭后主窗口及助手保持 | 通过；本轮可访问操作记录、`native-final-state.txt`；快速连续切页刷新偏差另列 |
| 新增、编辑与搜索快捷键 | Cmd+N 聚焦新增；Cmd+A/X/V 编辑；Esc 清草稿；Cmd+K 搜索 | 待办新增草稿剪切后粘贴恢复原文，Esc 后输入为空；Cmd+K 打开搜索，Esc 关闭 | 通过；`native-edit-shortcuts.txt` 与本轮操作记录。Cmd+C、详情 Cmd+Enter 本轮未单独验证 |
| 原生快速录入窗口 | 菜单打开，Esc 保留草稿，切换目的地，Enter 添加并收起 | 文件菜单打开；Esc 后再次打开原文保留；选择今天并 Enter 后只新增一项，窗口收起 | 通过；`quick-entry-draft-native.txt`、`native-final-day.json` |
| 跨应用全局快速录入热键 | 其他应用前台时 Ctrl+Option+Space 唤出 | 对访达发送模拟按键未唤出；此前记录已有同类模拟限制，无物理键盘确认 | **未验证**；包括物理按键、替代组合及冲突提示 |
| 中文输入法 | 确认文字的 Enter 不发送；取消不关面板；下一次发送正常 | 本轮未获得物理中文输入法组合过程。既有 20 项前端测试全通过，涵盖 IME、WebKit compositionend 顺序、原生标志、Esc、长按及发送偏好 | **未验证（物理输入法）**；自动化证据 `frontend-tests.log`，不能记为原生 IME 通过 |
| 原生备份保存器 | 下载在发起设置窗口打开 NSSavePanel，另存文件有效 | 原生保存面板选择验收目录；成功落盘 212 KB SQLite，integrity_check=ok | 通过；`native-save-picker.txt`、`manual-20260930-023249-3f994932.sqlite` |
| 原生备份文件选择器 | NSOpenPanel 选择外部文件，检查后才要求确认恢复 | 先验证取消；再次只选择上行生成的文件，显示已检查/当前数据未改变及确认恢复/取消；随后取消恢复 | 通过；`native-open-picker.txt`、`native-import-confirmation.txt`。本轮未执行最终恢复 |

## 自动化与未验证边界

本轮运行 `npm test --prefix web`：20 项通过。独立领域验收 4 组真实 SQLite/API 断言通过，脚本和逐请求证据保留。没有修改代码，因此没有重新运行完整 Python 回归、前端构建或 macOS 打包。

本轮没有重新验收主题重启（用户说明已修复安装），没有把以前通过的场景全部重跑。规划草案的真实模型暂停后恢复、物理 IME、跨应用物理热键、原生拖动/把手键盘排序、设置分区键盘导航、详情 Cmd+Enter、单独 Cmd+C 和最终备份恢复，均未获得本轮完整证据。

## Git、数据与进程收尾

开始工作树只有原有未跟踪 `docs/product/pro-roadmap-research-prompt.md` 与 `screenshots/` 的五张主题截图。结束新增本记录及 `acceptance-20260930-domain.md`，应用代码与 HEAD 不变；原有六个文件 SHA-256 逐一保持一致。无提交或推送。

真实数据库开始、启动异常后和结束的逻辑 SHA-256 为 `4e699a9adbf1c4228796d099f7d75161cec8c1a42dc56a3e1a2af207c051b96c`，保持一致。测试快照、原生截图和模型输出仅保存在忽略目录，不复制真实计划给模型。

**PROCESS_CLEANUP_COMPLETE**：通过 Cmd+Q 退出隔离应用，核实最终原生 PID `57562`、后端 `57563` 和本轮 Luna 进程均已退出，`18787` 无监听；子 agent 未启动服务或长期 worker。保留磁盘证据。用户既有 `8787` 服务 PID `88080` 始终运行，不属于本轮清理对象。证据：[结束核对](../../build/acceptance-20260930/final-check.json)、[开始基线](../../build/acceptance-20260930/baseline.json)。
