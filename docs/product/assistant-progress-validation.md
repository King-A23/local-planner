# 计划助手快捷键与操作过程验收

2026-10-01；对应 [已确认需求](assistant-progress.md)。开始时分支为 `codex/daily-experience`，HEAD 为 `1d12f3830943906f5933a770eb6ef0b63b53d991`。实现与验收阶段未替换安装版、未推送；用户后续要求的安装记录见文末。

## 隔离与证据

- 数据目录：`build/assistant-progress-20261001/data/`；数据库为其中的 `planner.sqlite`。所有 API 写入、测试草案保存、模型 CLI 均指向此目录。Python 用例分别使用 pytest 临时数据库。没有向真实计划或原有服务发送测试写入。
- 测试应用：`Local Planner Progress QA.app`，独立 bundle ID `local.planner.assistantprogress20261001`、独立 UserDefaults；测试副本源码仅额外指定测试端口。第一轮 `127.0.0.1:19787`，第二轮 `127.0.0.1:20787`。为避免影响原有全局录入键，测试副本关闭快速录入全局键。
- 模型只使用已有 `Codex · GPT-6 Luna · medium` 分组。仅在隔离副本中设置测试工作目录，保留模型与推理强度；正式启动器配置未改写。
- 证据集中在仓库忽略目录 `build/assistant-progress-20261001/`，包括 API JSON、无障碍文本、截图和构建日志。原有 `screenshots/` 与研究文稿未改动。相对证据路径以下均指此目录。
- 用户要求不要反复把窗口带到前台后，停止所有前台操作，只进行后台检查、文档及归档；缺少实测的项目明确标记为「未验证」。

## 快捷键与交互

| 场景 | 预期 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- |
| 今天页面 ⌘⇧L | 打开助手并聚焦输入；保持页面 | 原生菜单触发后助手可输入，页面仍为今天；桌面自动化记录及 `execution-result.txt` | 通过 |
| 待办页面 ⌘⇧L | 复用待办上下文，不切回今天 | 待办面板打开、输入框聚焦，保留“键盘草稿保留”；`shortcut-inventory.txt` | 通过 |
| 面板已开，重复快捷键；Esc | 重新聚焦，不关闭、不发送、不清空；Esc 收起 | 重复按键后草稿仍在；Esc 收起，再开仍保留；`shortcut-inventory.txt` 与本轮桌面自动化记录 | 通过 |
| 规划入口 | 进入现有草案流程，不直接创建正式任务 | 实际规划运行写入草案，未保存时正式目标和待办均为空；`planning-result.json`、`planning-result.txt` | 通过 |
| 目标详情入口 | 使用该目标的规划上下文 | 在隔离数据中手动保存测试草案后，从目标详情打开对应草案并聚焦输入；`goal-shortcut.txt` | 通过 |
| 执行中 | 打开已有执行；输入不可编辑，焦点在控制区 | 同一 run ID，运行控制区获得焦点；`final-live-process.txt` 及桌面自动化记录 | 通过 |
| 暂停后 | 打开已有执行，输入可编辑 | 普通执行、规划草案均暂停成功，快捷键聚焦输入；`final-real-paused.json`、`planning-paused.txt` | 通过 |
| 独立设置窗口 | 回到主窗口并打开助手 | 从原生设置窗口触发成功；原有页面和运行保留；桌面自动化记录 | 通过 |
| 关闭主窗口后 | 恢复主窗口，不新建执行 | ⌘W 后 ⌘⇧L 恢复主窗口，草稿/已有结果保留；桌面自动化记录（无单独截图文件） | 通过 |
| 网页搜索模态框 | 不抢焦点 | ⌘K 搜索对话框中按 ⌘⇧L，搜索框仍保持焦点；`search-modal-shortcut.txt` | 通过 |
| 原生备份文件选择器 | 不抢焦点、不选择文件 | 「选择 Local Planner 备份」面板中按 ⌘⇧L，原生面板保持，随后取消；未导入；`file-panel-shortcut.txt` | 通过 |
| 鼠标设置切换 | 点击开关即时影响当前过程视图 | 暂停执行中关闭/开启，原步骤隐藏/恢复，同一 run ID；`process-off-after-navigation.txt`、`final-live-process.txt` | 通过 |
| 指定日期页面快捷键 | 保留指定日期上下文 | 实现沿用已有 surface/date，但本轮未完成该页面的实际快捷键操作 | **未验证** |
| 隐藏主窗口后快捷键 | 恢复主窗口 | 已测关闭窗口；隐藏窗口的独立实测尚未执行 | **未验证** |
| 中文输入法组合输入 | 不抢焦点、不发送 | 自动测试覆盖 isComposing、keyCode 229、repeat；未完成系统中文输入法的完整实测 | **未验证** |
| 浏览器 Ctrl⇧L / macOS 浏览器 ⌘⇧L | 正确匹配平台并聚焦助手 | 键盘匹配自动测试通过，未完成浏览器的实际交互 | **未验证** |
| 手动向上查看历史及展开详情 | 不强制滚到底部；详情按需展开 | 实测截图中详情默认折叠；滚动跟随代码只在距底部 24px 内启用，未完成手动向上滚动及详情展开实测 | **未验证** |

## 设置与过程显示

| 场景 | 预期 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- |
| 默认值 | 默认关闭，注明只看结果（推荐） | 新 bundle 偏好下开关关闭；`settings-default.txt` | 通过 |
| 主窗口与设置窗口同步 | 立即同步 | 在独立设置窗口切换后，主窗口当前运行过程立即隐藏/恢复；`planning-paused.txt`、`final-live-process.txt` | 通过 |
| 重启并更换端口 | 桌面原生偏好保持 | 第一轮开启后退出，第二轮从 19787 改为 20787，开关仍开启；本轮桌面自动化记录 | 通过 |
| 关闭后页面重新加载 | 不恢复过期的文档注入值 | 修复原生偏好刷新后实测：关闭过程、跳待办重新加载、再次唤出，无过程区；`process-off-after-navigation.txt` | 通过 |
| 运行途中开启 | 读取已经采集的真实事件 | 暂停状态下重新开启，已有工具事件显示，未启动新执行；`final-real-paused.json`、`final-live-process.png` | 通过 |
| 最终回复分离 | 无 JSONL、中间说明或进程收尾标记 | 最终普通执行回复仅报告当天为空；过程区另有公开说明、工具状态；`final-real-result.json` | 通过 |
| 包装命令 | 不改写，提示不支持过程，正常执行 | 参数适配单元测试保留 env、shell、wrapper；原有自定义执行/结果回执测试通过。提示组件已实现，未单独实测包装命令 UI | 自动测试通过；UI **未验证** |
| 不可识别事件 | 忽略损坏事件，未识别任何公共事件时提示不支持过程 | 单元测试覆盖损坏/未知/超大行；流结束时 source=none，不把 JSON 作为回复 | 通过（自动） |
| 刷新恢复过程 | 服务内仍保留事件可重新读取 | 暂停执行跨页面重新加载仍保留相同 run ID；独立 API 增量读取通过 | 通过 |
| 网页 localStorage 持久化 | 刷新保持开关 | 实现完成；未在实际浏览器中完成持久化验收 | **未验证** |
| 备份范围与退出后历史 | 偏好不进数据库备份；过程只在服务内存 | 未增加数据库字段/迁移，偏好走 UserDefaults/localStorage，事件只存 RunControl 内存；源码核对 | 通过（代码检查） |

## 流式、进程控制与真实模型

| 场景 | 预期 | 实际结果与证据 | 状态 |
| --- | --- | --- | --- |
| 分段中文及并发 stdio | 正确解码；不因 stderr 大量输出堵塞 | 逐字节中文/emoji、并发 180KB stderr、600 条工具事件，执行可停止；`tests/http/test_agent_progress.py` | 通过（自动） |
| 限量与省略 | 最多 500 条/256KiB；详情最多 8KiB | 数量、UTF-8 字节、截断提示、游标增量断言通过；`tests/test_agent_events.py` | 通过（自动） |
| 同一工具事件更新 | started/completed 更新同一行 | 后端事件 ID 保持；前端 merge 测试覆盖去重与新序号；`web/tests/assistantProgress.test.mjs` | 通过（自动） |
| 工具失败/结构化错误 | 失败可见，不误报成功 | 工具非零退出显示失败；turn.failed 即使进程退出 0 也得到失败回执；Python 单元与 HTTP 测试 | 通过（自动） |
| 暂停、继续 | 暂停不累计超时，继续同一次执行 | 流式 HTTP 测试暂停后事件不增长；普通执行与规划真实运行暂停/继续后成功；相关 JSON | 通过 |
| 停止、超时、stdio 先关闭 | 清理所属进程组；继续监督已关闭管道的进程 | 停止/超时测试及原有进程控制测试通过，新增关闭 stdout/stderr 后仍运行的超时用例 | 通过（自动） |
| 内部推理 | 不显示 reasoning 事件 | Codex/OpenCode reasoning 输入白名单过滤测试通过；无 raw JSON 日志持久化新增 | 通过（自动） |
| OpenCode 格式 | 直接调用增加 --format json，保留已保存配置 | 官方格式协议样例测试通过；未调用真实 OpenCode 模型 | 协议自动测试通过；真实模型 **未验证** |
| 普通执行真实流式 | 结束前显示公开说明和工具操作 | `da64cb64-4113-422b-bca8-d8f2dea6eae8`：运行中 result=null 已有 4 条事件，结束成功，无计划改动；`execution-early.json`、`execution-result.json` | 通过 |
| 规划草案真实流式 | 结束前显示操作，不自动保存 | `12c048e4-1a53-40bd-bc4b-c2e51a409be0`：运行中已有 4 条事件，暂停/继续后产生一目标、一阶段、一候选行动草案；保存前正式数据为空；`planning-early.json`、`planning-result.json` | 通过 |
| 最终版普通执行、运行中切换过程 | 切换只改变展示，不改变执行 | `6fb40120-a9eb-4984-8c8b-d29cb6fe2d79`：暂停时已有 5 条事件，开关反复切换后继续同一执行；最终成功，changed=false，工具摘要「读取当天计划」；`final-real-paused.json`、`final-real-result.json` | 通过 |
| 开关两种状态的写入结果对照 | 同样指令得到相同计划结果 | 本轮实测为同一只读执行中切换显示，无计划变化；未以两份独立数据库完成相同写入指令的完整 A/B 验收 | **未验证** |

验收中修复了原生偏好文档注入值在重新加载时过期、目标草案上下文切换时显示旧执行过程、Shell 封装的计划 CLI 摘要、公开回复中的进程标记。最后补充了从共享执行恢复空本地输入草稿，以及没有可识别事件时的不支持提示；这两项最后改动经过后台测试和构建，未重新进行前台 UI 验收。

## 自动检查与交付

- 最终全量 Python：`376 passed`，既有 Starlette/httpx 弃用警告 1 条；`pytest.log`。
- 前端：`23 passed`；`frontend-tests.log`。
- TypeScript/Vite、PyInstaller、Swift、codesign 与 macOS 打包通过；`macos-build.log`。最低 macOS 26.0。
- 构建压缩包：`dist/macos/Local-Planner-macOS-arm64.zip`；测试副本归档 `first-pass-qa.zip`、`final-qa.zip`。校验压缩包内容后移除解压态测试/构建 .app，避免留下 Spotlight 候选项。
- 最终 Git 及 SHA256 核对、进程/端口状态见 `final-check.json`。研究文稿、5 张既有截图与当前安装版可执行文件均与开始记录一致。HEAD 未变；工作区保留本轮代码与文档修改。

## 进程收尾

本轮测试主进程/后端：714/720（19787）、1975/1977（20787）均结束；本轮模型执行及构建 worker 已结束，两个测试端口不再监听。状态：`PROCESS_CLEANUP_COMPLETE`。

原有长期进程保持，资源值以任务结束检查为准：

| PID | 用途 | 停止方法（仅记录，未执行） |
| --- | --- | --- |
| 88080 | 原有 Web 服务，127.0.0.1:8787 | 用户需要时执行 `kill -TERM 88080` |
| 95805 | 当前安装版 Local Planner 主程序 | 在该应用中 ⌘Q，或 `kill -TERM 95805` |
| 95806 | 当前安装版所属后端，127.0.0.1:18787 | 退出主程序，由父进程监督清理 |

CPU/RSS 快照记录在 `final-check.json`，未停止或替换上述应用与服务。

## 后续安装（用户要求安装最新版）

2026-10-01，用户明确要求「安装最新版本」。安装到 `~/Applications/Local Planner.app`，来自已通过构建检查的 `dist/macos/Local-Planner-macOS-arm64.zip`，SHA256 为 `1688fd8945c90074d9ece3b7d1ee1ee6d5a53778b9bbdc6bf0c4c49065ec9e9e`。

- 安装前只读核对原应用没有正在运行或暂停的助手任务，再通过 NSRunningApplication 请求正常退出，无前台激活。旧主程序 95805 和后端 95806 已退出，18787 不再监听。
- 旧版本归档为 `~/Library/Application Support/local-planner/app-archives/20261001/before-assistant-progress-154510.app.zip`；逐文件及符号链接校验后保留 ZIP，没有留下旧 .app 副本。
- 新安装包 97 个文件/符号链接与构建 ZIP 一致，`codesign --verify --deep --strict` 通过。保持 bundle ID `local.planner.desktop`、原数据目录和 UserDefaults；未改动计划数据库或偏好设置。
- 为尊重用户不抢前台的要求，未自动启动新版：当前原生程序启动代码会主动激活窗口。用户下次打开应用即使用新版。
- 保留原 Web 服务 PID 88080（8787）。资源与最终 Git 检查见 `build/assistant-progress-20261001/installation-final-check.json`；若用户需要停止该服务，可执行 `kill -TERM 88080`。本次没有提交或推送。
- 临时安装目录已清理。收尾状态：`PROCESS_CLEANUP_COMPLETE`。

## 操作过程结束后自动收起修正

2026-10-01，用户反馈执行结束后步骤区持续停留，要求 3 秒后自动收起。改为可手动展开/收起的原生 HTML details 区域；只折叠过程，最终回复及改动回执保持原行为。新执行自动展开，已结束执行重新打开时默认收起。

使用 Playwright CLI 的独立 headless 会话，在 `127.0.0.1:21787` 验证真实 `AgentProcess` 组件。测试页只用固定事件响应，没有计划数据库、模型调用或真实服务访问，没有前台浏览器窗口。证据在 `build/process-collapse-20261001/headless/`（测试时写在 `output/playwright/process-collapse-20261001/`，收尾后移入忽略目录）。

| 场景 | 预期 | 实际 | 状态 |
| --- | --- | --- | --- |
| 成功、失败、停止 | 结束 3 秒后收起 | 三种场景分别在 2.7 秒仍展开、3.3 秒已收起；`checks.log` | 通过 |
| 运行、暂停 | 不按 3 秒自动收起 | 等待超过 3 秒仍展开；`checks.log` | 通过 |
| 收起后请求 | 停止过程轮询 | 等待 1 秒请求计数未增长；`checks.log` | 通过 |
| 手动操作 | 可收起和重新展开，重新展开后保持 | 完成后重新展开超过 3 秒保持；倒计时内手动收起再展开取消倒计时；`checks.log` | 通过 |
| 执行切换 | 旧倒计时不影响新执行 | 结束后 1 秒启动下一次执行，3 秒后新过程仍展开；`checks.log` | 通过 |
| 已结束执行首次打开 | 默认收起，手动打开不再计时 | 首次收起、手动展开超过 3 秒仍展开；`checks.log` | 通过 |
| 最终回复 | 不因过程收起消失 | 折叠状态只在 AgentProcess 内，AgentPanel 结果区未改动；源码核对 | 通过（代码检查） |
| 安装版真实模型完整交互 | 与无界面组件测试一致 | 为避免抢前台未执行原生窗口实测，未新增真实模型调用 | **未验证** |

前端 23 项测试、TypeScript/Vite 和 macOS 打包检查通过。仅改动前端展示，未改动领域逻辑、数据库或执行器，本次未重跑已通过的 Python 全量测试。安装和进程收尾证据见 `build/process-collapse-20261001/installation.json`、`final-check.json`；保留真实计划、偏好和原 Web 服务。

已更新 `~/Applications/Local Planner.app`，97 个文件/符号链接与本次构建 ZIP 一致且签名检查通过；ZIP SHA256 为 `05a1266bda8e945fbb5f42778ccc44fbd8785c51696c462761c44d4be80f4c3b`。前一安装版归档为 `~/Library/Application Support/local-planner/app-archives/20261001/before-process-autocollapse-160808.app.zip`。没有留下解压态测试或旧应用副本，未自动启动新版。

旧主程序/后端 4968/4976、隔离测试服务 5427、headless 会话 5469 均已结束，18787/21787 不再监听，临时安装目录已删除。原 Web 服务 PID 88080 保留（检查时 CPU 0.0%，RSS 18384 KiB；用户需要时 `kill -TERM 88080`）。Git HEAD 未变，原研究文稿和 5 张截图 SHA256 保持一致。收尾状态：`PROCESS_CLEANUP_COMPLETE`。
