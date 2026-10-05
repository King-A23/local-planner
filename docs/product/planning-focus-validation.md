# 当前重点与草案字段对照验收

2026-10-03，分支 `codex/daily-experience`，开始和结束 HEAD 均为 `0e385df264fbc53cd904b26aebe796b42bccdf57`。开始时已有通知及 Dock 角标的未提交改动，本轮在其上增量实现并保留。范围见 [本轮需求](planning-focus.md)。

## 验证环境

全程没有操作前台窗口。使用 Playwright CLI headless 加载真实 App 构建页面、真实 FastAPI 后端，绑定 `127.0.0.1:23987`，数据库位于 `build/planning-focus-20261003/data/`，时钟固定在上海日期 2026-10-03。合成目标、阶段、行动与 Task 均为测试数据。没有向真实服务发送测试写入，没有调用真实模型。

证据保存在忽略目录 `build/planning-focus-20261003/`：`baseline.json`、`python-tests.log`、`frontend-tests.log`、`frontend-build.log`、`macos-build.log`、`final-check.json`、合成数据及 `headless/` 下的检查脚本、结果、快照和截图。第一次测试环境没有挂载 SPA，修正测试服务配置后使用真实页面验证；重启测试服务时出现过一次预期的轮询断连。完成操作的最初 Playwright check() 在异步响应前判断勾选状态，改用正常 click 并等待完成请求；实际数据操作成功，未为此改应用逻辑。

## 逐项预期与实际

| 场景 | 预期 | 实际与证据 | 状态 |
| --- | --- | --- | --- |
| 首次进入 | 当前重点默认空，选择权属于用户 | 不自动选目标；选择器只列进行中目标；checks.log | 通过 |
| 选择顺序与数据边界 | 按选择顺序呈现，不修改规划或 Task | 3 张卡片按用户点击顺序显示；选择前后目标 API JSON 完全一致；checks.log | 通过 |
| 阶段与下一步 | 同时看见阶段成果及实际行动状态 | 卡片显示当前阶段成果，区分候选、待办、今天和未来安排；focus-desktop.png | 通过 |
| 选择下一步 | 就地选择候选或已关联 Task | 已关联行动成为下一步，nextTaskId 等于原 ID；checks.log | 通过 |
| 加入待办 → 今天 | 只落地一次并复用 Task | nextActionId 转为 nextTaskId；加入今天前后 ID 一致，目标 Task 数量为 1；checks.log | 通过 |
| 未来下一步 | 明确显示原日期和「改到今天」 | 原 2026-10-05 改到 2026-10-03，ID 保留；checks.log | 通过 |
| 完成回流 | 完成同一行动，清空下一步，不自动选新行动 | 今天页真实点击完成，规划 nextTaskId 为 null；选择器不再列已完成行动；followup.log | 通过 |
| 快速重复操作 | 不产生两个任务 | 同步触发两次点击，只有一份新 Task；followup.log | 通过 |
| 其他窗口版本变化 | 拒绝过期安排，刷新后可重试 | 构造外部目标编辑后，第一次安排返回 Conflict，日期保持 null；刷新重试复用原 Task；followup.log | 通过 |
| Esc 与焦点 | 取消不保存，回到原入口 | 暂选取消后偏好未变、模态关闭、焦点回到「选择重点」；checks.log | 通过 |
| 暂停 / 恢复 | 隐藏暂停重点，恢复后重现原选择 | 暂停后卡片收起，恢复后按原顺序出现；checks.log | 通过 |
| 刷新与网页间同步 | 恢复偏好，其他同源页面即时更新 | 刷新恢复 3 张卡片，第二页面同步取消后变为 2 张；checks.log | 通过 |
| 损坏 / 失效偏好 | 不崩溃或误选 | 损坏 JSON 回到空选择；重复、空值、缺失及已结束 ID 有前端单元覆盖；followup.log、frontend-tests.log | 通过 |
| 地图与草案 | 地图可查看；未保存草案不可作为可执行重点 | 切换地图保留完整关系，草案编辑时隐藏重点卡并显示地图；checks.log | 通过 |
| 字段修改前后 | 展示已校验草案与基线的具体差异 | 成果原文及改后文字一致；名称、备注、引用、顺序、清空、新增、移除有 HTTP 测试；checks.log、python-tests.log | 通过 |
| 同名引用 | 更换同名对象仍能辨认 | 文本注明「另一项同名内容」；单目标外部父引用显示真实名称；python-tests.log | 通过 |
| 中文、多行、长文本、HTML | 保留文字，安全换行，不执行 HTML | script 内容仅是文本、DOM 无 script 元素；620px 下无页面横向溢出；review-mobile.png、checks.log | 通过 |
| 预览、撤销、保存、还原 | 预览不写正式规划，保存及还原保护 Task | 预览前后正式 API JSON 相同；撤销清空差异，保存修改成果且 Task ID 保留，还原恢复原成果；checks.log | 通过 |
| 窄窗口与深色主题 | 卡片、选择器和字段对照可读 | 620px 检查通过；主题截图检查发现切换时文字继承影响对比度，组件明确使用主题前景色，等待颜色过渡完成后截图可读；theme-checks.log、focus-mobile.png、focus-midnight.png、picker-midnight.png | 通过 |
| 原生重启 / 端口变化 | UserDefaults 按数据目录保存并恢复重点 | 原生写入、JSON 注入、来源验证和数据目录键的代码检查及 Swift 构建通过；为不打扰用户，未启动原生测试窗口或重启当前应用 | **未验证（实际交互）** |
| 新切片下真实 Luna 生成草案 | 新对照显示实际模型草案 | 本轮仅使用已校验的合成草案，无真实模型调用 | **未验证** |
| 物理中文输入法 / 屏幕阅读器 | 正常键盘和播报 | 本轮没有操作原生输入法或屏幕阅读器；新增操作没有文本输入框 | **未验证** |

主页面 26 条检查、完成／冲突等 8 条补充检查全部通过，另有深色主题颜色和截图核对。

## 自动化与构建

- Python 全量 **382 项通过**；新增字段差异、外部父引用、同名实体区别测试，原草案保存及任务保护测试继续通过。只有已有 Starlette/httpx 弃用提示。
- 前端 **29 项通过**；新增重点筛选、选择顺序及行动候选身份测试。TypeScript/Vite 通过。
- macOS 原生 Swift、后端打包及 codesign 验证通过。ZIP `dist/macos/Local-Planner-macOS-arm64.zip` 的 97 个文件／符号链接与构建 .app 逐项一致，SHA256：`6ef90ae87a770abc755f1eb32a4d3c9e6a801e9970e044b149bec9e026e4e382`。
- 构建 .app 在确认 ZIP 可完整恢复后移除，避免残留应用影响 Spotlight；保留 ZIP 作为交付。本轮没有覆盖安装版、没有提交或推送。

## Git、数据与进程收尾

原研究文稿、5 张截图的 SHA256 均与开始一致，真实 launchers.json SHA256 未变。没有读取或修改真实计划内容。Git 仍保留开始时的通知相关改动，本轮追加规划代码及需求、验收文档。

本轮后端 73298、73937、75294，headless 会话 73338、74800 已退出；23987 已释放，测试 worker 和 Swift 检查进程没有保留。原用户应用与服务保留，收尾快照如下：

| PID | 用途 | CPU | RSS | 停止方法 |
| --- | --- | --- | --- | --- |
| 41712 | 当前桌面应用 | 0.0% | 134912 KiB | 正常退出应用 / Cmd+Q |
| 41713 | 当前桌面后端 | 0.1% | 36416 KiB | 随父应用退出；不单独终止 |
| 88080 | 原网页服务，8787 | 0.0% | 15344 KiB | `kill -TERM 88080` |

收尾状态：`PROCESS_CLEANUP_COMPLETE`。完整快照见 `build/planning-focus-20261003/final-check.json`。

## 2026-10-03 安装

用户确认安装后，更新 `~/Applications/Local Planner.app`。97 个文件/符号链接逐项与交付 ZIP 一致，原生签名检查通过；ZIP SHA256 为 `6ef90ae87a770abc755f1eb32a4d3c9e6a801e9970e044b149bec9e026e4e382`。旧版本已归档到 `~/Library/Application Support/local-planner/app-archives/20261003/before-planning-focus-153334.app.zip`，归档内容逐文件核对。

更新前两次只读确认助手已结束，未发送测试写入。正常退出旧主程序 41712 和后端 41713；没有激活窗口，新版未自动启动，由用户自行打开。模型配置、原研究文稿和 5 张截图的 SHA256 保持一致。安装暂存目录已删除，没有留下测试应用副本。安装证据见 `build/planning-install-20261003/installation.json` 和 `final-check.json`。

`PROCESS_CLEANUP_COMPLETE`：本次安装进程结束，旧桌面应用及后端已退出，18787 已释放。原 Web 服务 88080 保留；CPU/RSS 快照和停止方法见安装收尾记录。未提交或推送，Git HEAD 保持不变。
