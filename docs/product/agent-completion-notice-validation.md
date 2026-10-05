# 助手完成通知验收

2026-10-02；用户要求 Agent 完成时在应用右上角显示一条通知。开始时 HEAD 为 `0e385df264fbc53cd904b26aebe796b42bccdf57`，分支 `codex/daily-experience`，仅有原研究文稿与 `screenshots/` 未跟踪。

采用现有 AgentPanel 运行轮询及控制响应观察终态，不增加后端请求轮询或数据库字段。通知位于页面右上角，5 秒自动关闭，支持手动关闭；新通知替换旧通知并重新计时。最终回复、回执、过程折叠和模型设置保持原行为。

## 独立后台交互验证

使用 Playwright CLI headless 独立会话与 `127.0.0.1:22787` 测试页，加载真实 AgentPanel、AgentCompletionToast 和应用样式。API 仅返回固定运行数据；无计划数据库、无模型调用、无真实应用服务写入。助手面板始终关闭，以验证后台完成也能提醒。没有前台浏览器或原生窗口操作。

证据保存在 `build/agent-completion-20261002/headless/`：`checks.log`、`run-checks.js`、`notice.png` 和页面快照。原始截图与文稿未改动。

| 场景 | 预期 | 实际及证据 | 状态 |
| --- | --- | --- | --- |
| 初次加载历史完成结果 | 不误报新的完成 | 没有通知；事件次数为 0，重复读取仍为 0；checks.log | 通过 |
| 执行中或暂停 | 不提示完成 | running/paused 均没有通知；checks.log | 通过 |
| 完成且面板关闭 | 右上角提醒，保持面板关闭 | 正确提示「计划助手已完成」，通知距顶部/右侧均 16px，面板仍 hidden；notice.png、checks.log | 通过 |
| 焦点 | 不抢输入焦点 | 通知出现后原按钮仍为 activeElement；checks.log | 通过 |
| 重复轮询 | 一次执行只提醒一次 | 多次轮询事件次数保持 1；checks.log | 通过 |
| 手动关闭 | 立即消失且不被轮询重新打开 | 关闭后下一轮轮询仍无通知；checks.log | 通过 |
| 快速执行 | 未观察到运行态也可提醒新执行结束 | 两轮轮询之间已完成的独立 run ID 提醒一次；checks.log | 通过 |
| 新通知计时 | 旧通知定时器不误清除新通知 | 旧通知原应过期时，新失败通知仍显示；checks.log | 通过 |
| 失败与部分完成 | 不误报成功；已有改动保留说明 | 正确显示「未完成」及「已有部分改动已保留」；checks.log | 通过 |
| 停止 | 明确已停止 | 显示「计划助手已停止」；checks.log | 通过 |
| 普通回复及规划 | 不把澄清/未保存草案称为已改动计划 | 无改动时「已回复」；规划提示「草案需保存后生效」；单元测试、checks.log | 通过 |
| 自动关闭 | 5 秒后消失，重复轮询不延长 | 等待 5.3 秒无通知，事件次数不变；checks.log | 通过 |
| 刷新已完成执行 | 不重放 | 刷新后保持无通知；checks.log | 通过 |
| 运行中刷新 | 结束时仍收到提醒 | 刷新后从 running 到 succeeded，收到一次通知；checks.log | 通过 |
| 恢复数据事件 | 清除失效通知 | planner:restored 后通知消失；checks.log | 通过 |
| 屏幕阅读器 | 礼貌播报新通知 | role=status、aria-live=polite、aria-atomic=true，状态区域持续挂载；源码检查，未实际使用屏幕阅读器 | **未验证（实际播报）** |
| 原生安装版完整模型执行 | 与测试页一致 | 为避免抢前台，未执行新的原生窗口/真实模型实测 | **未验证** |

## 检查和交付

- 前端 27 项测试通过，新增 4 项覆盖终态观察、去重、快速完成与结果措辞；`frontend-tests.log`。
- TypeScript/Vite 和 macOS 构建、签名检查通过；`frontend-build.log`、`macos-build.log`。本次只改前端显示，没有修改后端或领域逻辑，不重复运行已有 Python 全量检查。
- 安装包、归档路径与逐文件校验见 `installation.json`；数据和偏好保留，已保存的 GPT-6.1 Sol low 配置不变。为避免抢焦点，更新后不自动启动。
- 结束时 Git、原文件 SHA256、模型配置 SHA256 及进程/端口核对见 `final-check.json`。新测试端口与 headless 会话均清理，不保留测试 .app 副本。
- 原 Web 服务 PID 88080 保留，资源快照见 `final-check.json`；用户需要时可执行 `kill -TERM 88080`。本次未推送。

收尾状态：`PROCESS_CLEANUP_COMPLETE`。

安装结果：`~/Applications/Local Planner.app` 的 97 个文件/符号链接与本次构建 ZIP 一致，签名检查通过。ZIP SHA256：`457cc2df72b70a414a04bcbb51c0acf63f95f1580f759e0fcb2bd2aedb149173`。旧版归档为 `~/Library/Application Support/local-planner/app-archives/20261002/before-agent-completion-notice-140956.app.zip`，临时安装目录已删除；新版未自动启动。

安装前确认原助手执行已成功结束；正常退出旧主程序 28907 及后端 28908，无前台激活。测试服务 30537、headless 会话 30569 均已结束，18787/22787 已释放。原 Web 服务 88080 保持（CPU 0.0%，RSS 15408 KiB）。原研究文稿、5 张截图、模型配置 SHA256 均未变化；Git HEAD 保持为开始提交，工作区留有本轮代码和文档改动。

## 用户澄清后的 Dock 角标修正

同日用户说明：发起助手后会去使用其他应用，所需位置是 Dock 应用图标右上角。此前验收只证明页面通知可用，**不满足后台 Dock 提醒**。本轮新增原生状态监听及 NSDockTile 角标，应用内通知作为前台辅助反馈保留。

原生监听每秒只读自身后端 `/api/agent-runs`，不依赖网页计时器，不启动模型或写计划。后台结束显示未读数量，没有自动过期时间；主窗口成为当前可查看窗口后清除。设置、快速录入、隐藏、最小化、关闭主窗口及模态窗口均不被视为已查看。首次历史终态不重放，同一 run ID 不重复累计；恢复数据重置角标和历史基线；退出取消请求、计时器和执行活动。使用 Apple [NSDockTile.badgeLabel](https://developer.apple.com/documentation/appkit/nsdocktile/badgelabel) 原生接口，角标外观由系统绘制。

### 逐项验证

测试使用独立 Swift 可执行文件（禁止激活、无窗口、无 .app 注册）、URLSession 固定响应以及两个独立临时数据目录的真实桌面后端。执行使用受控脚本，未调用真实模型、未读写真实计划；监听端口由系统独立分配。没有切换任何前台窗口。

| 场景 | 预期 | 实际与证据 | 状态 |
| --- | --- | --- | --- |
| 后台成功结束 | 原生角标变为 1 | URLSession/Timer 收到终态后，实际 NSDockTile.badgeLabel 为 1；27 项 Swift 检查 | 通过 |
| 启动历史、运行、暂停、停止中 | 不误报完成 | 历史结果不重放；四种非终态无角标 | 通过 |
| 重复轮询、清除后再轮询 | 一次执行只累计一次 | label 不重复增长；已查看 ID 不再累计 | 通过 |
| 多次结束及失败、部分失败、停止 | 累计需查看的结束结果 | 全部终态累计，结果未生成时等待 | 通过 |
| 切回主窗口 / 其他窗口 | 主窗口可查看时清除，其他窗口保留 | 可查看状态清为 nil；不可查看状态保持 1 | 通过（状态模拟） |
| 保留时间 | 不随页面通知 5 秒计时消失 | 原生状态无过期定时器；重复轮询保持 1 | 通过（代码及状态检查） |
| 快速完成、断连重试、损坏响应 | 快速完成仍触发；无实际终态不伪造提醒 | 两次轮询间的新终态触发；HTTP 500 / 无 run 字段不更改状态 | 通过 |
| 恢复数据、退出 | 清除旧角标，停止自身监听 | reset 后当前终态视为历史；stop 后请求计数不再增长 | 通过 |
| 普通执行与规划草案的实际后端 | 没有 WebKit 窗口时也能触发角标 | 两个独立桌面后端、独立数据库：受控脚本成功结束，原生 GET 监听将实际 NSDockTile.badgeLabel 设为 1 | 通过 |
| 系统 Dock 实际视觉、切应用/隐藏/最小化/关闭/模态等窗口操作 | 图标右上角可见，返回主窗口清除，不抢前台 | 为遵守不打扰前台的要求，没有操作原生窗口或截取桌面；状态判定和原生接口已测试 | **未验证（真实窗口操作与视觉）** |
| 真实 Luna 结束后的 Dock 角标 | 与受控脚本相同 | 本轮未发起真实模型执行 | **未验证** |

证据：`build/agent-completion-20261002/native-tests.log`、`dock-python-tests.log`、`frontend-tests.log`、`dock-macos-build.log`。测试源为 `tests/desktop/agent_completion_checks.swift` 和 `tests/test_desktop.py`。安装及进程收尾另见本轮 `dock-installation.json`、`dock-final-check.json`。

### 修正交付与收尾

- Python 全量 **379 项通过**，包含 27 项 Swift 状态/原生接口检查及普通执行、规划草案两条实际后端链路；前端 **27 项通过**。TypeScript/Vite、原生 Swift、macOS 包构建与签名检查通过。
- 已更新 `~/Applications/Local Planner.app`，97 个文件/符号链接与 ZIP 完全一致。ZIP SHA256：`4ae6d958168848bc54734e376d6b6672e484ffb2810ae1eee35ef3bc132939b0`。更新前两次只读确认真实助手已结束，正常退出原主程序 31859 及后端 31860；没有激活窗口，新版本需用户自行重新打开。
- 旧应用已归档 `~/Library/Application Support/local-planner/app-archives/20261002/before-dock-completion-badge-144753.app.zip`。临时 `.noindex` 安装目录已清理，构建 .app 已移至唯一安装路径；没有留下会污染 Spotlight 的测试应用副本。
- 开始和结束 Git HEAD 均为 `0e385df`，本轮通知和 Dock 修正仍为未提交、未推送改动。原研究文稿、5 张截图和模型配置 SHA256 未变。所有本轮 Swift 检查、受控脚本及临时后端已退出，18787 已释放。
- 保留原 Web 服务 PID **88080**、端口 8787，CPU 0.0%，RSS 15408 KiB；停止方法 `kill -TERM 88080`。没有向其发送测试写入。

修正收尾状态：`PROCESS_CLEANUP_COMPLETE`。
