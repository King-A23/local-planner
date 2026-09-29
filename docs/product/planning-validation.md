# 规划模块验收记录

2026-09-29，分支 `codex/daily-experience`。本轮构建产物未推送，未覆盖已安装应用。功能范围与接口见 [规划实现](planning-implementation.md)。

## 自动化

- `.venv/bin/python -m pytest -q`：355 项通过。覆盖旧数据迁移、恢复 generation、Task 身份与删除撤销、幂等落地、关系循环、结束状态限制、阶段成果、草案持久化、局部修改、版本冲突、非法输出、停止与重启中断、保存及安全撤销。
- `npm test --prefix web`：20 项通过。包括中文输入法确认回车、WKWebView 事件顺序、发送快捷键、目标地图保留暂停祖先上下文、候选行动转为 Task 后的下一步身份。
- `npm run build --prefix web`：TypeScript 和 Vite 构建通过。
- 新 CLI `planning create/show/update/apply/revert` 在临时数据库中完成端到端验证；草案预览和保存不会产生待办。过期恢复 generation 返回 Conflict。
- 只允许撤销最近一次保存；后续相关修改、落地 Task 或新支持关系造成冲突时拒绝撤销。

## 真实 Luna 测试

使用既有 `Codex · GPT-6 Luna · medium` 配置，在 `build/planning-qa/data` 与独立浏览器窗口运行。运行时工作目录与模型上下文进一步隔离。没有向模型提供真实数据库路径。

1. 首次生成返回不合法阶段状态 `active/upcoming`，应用拒绝结果且不改变正式规划。随后补充预设中的枚举 `open/done/skipped`、当前阶段字段与结构示例。
2. 重试成功生成三个目标：CSP 认证、支持它的基础算法目标、独立的个人应用目标；时间没有被当成上下级。生成前后正式目标和 Task 均为零。
3. 在全局草案中选中“专题训练”，要求只改该阶段成果。首次请求暴露了过严的全局阶段校验，修复并增加回归测试后重试成功；深度比较仅 `/goals/0/phases/1/outcome` 变化，全部 ID 与其他内容保留。
4. 通过界面保存，正式目标变为三个，但待办仍为零。“加入今天”产生且只产生一个 Task，界面显示“已在今天”。在今天完成该任务，路线图显示同一行动已完成，并清空下一步。
5. 在单目标草案选中“模拟冲刺”，要求只改成果并保留已完成练习。真实模型执行成功，深度比较仅 `/goals/0/phases/2/outcome` 变化；保存前正式目标不变。保存再还原后成果恢复，已完成 Task 的 ID、完成记录保持不变。

真实模型累计一次无效结果、三次成功生成／调整。暂停、停止和中断保护有自动化验证；本轮没有完成一次真实模型的暂停后恢复，不将该项计为真实模型验收。模型输出通过结构、身份、Task 保护和版本校验后才更新草案；这些结果不代表任意自然语言都能被模型正确理解。

原始结果与差异证据保存在忽略目录 `build/planning-qa/`：`generation-retry.json`、`refinement-proof.json`、`scoped-refinement-proof.json`、`materialized.json`、`completion-proof.json`、`final-proof.json`。

## 界面与 macOS

- 浏览器验证：草案内查看路线图、选择阶段、保存与还原；手动添加阶段与成果；行动进入今天及完成状态回流。
- 620px 窄窗口阶段转为纵向，无页面横向溢出；助手输入从单行自动伸展为多行。模拟 compositionstart／compositionend 与确认 Enter，未发起 Agent 请求。物理中文输入法的全系统组合仍以既有键盘测试覆盖为主。
- 检查了目标地图、横向路线图及窄窗口截图，保存在 `output/playwright/`。
- `.venv/bin/python scripts/build_macos.py` 成功，包含原生 Swift 编译、独立 Python 后端打包和 codesign 验证。产物：`dist/macos/Local Planner.app` 与 `dist/macos/Local-Planner-macOS-arm64.zip`。当前构建环境决定最低 macOS 为 26.0。
- 为避开已安装应用的单实例保护，复制构建产物到测试目录，仅修改测试副本的 bundle ID 并重新签名。独立数据目录实际打开原生窗口，验证规划空状态、手动创建目标、独立设置窗口及新增规划帮助内容。交付包未修改 bundle ID。

## 数据与收尾

真实数据库只读逻辑快照在测试前后的 SHA-256 完全一致；真实今天的计划未改变。用户原有未提交文稿和截图保留。测试服务器、浏览器会话与原生测试副本在交付前关闭，保留磁盘上的验收证据，不保留后台测试进程。

## 后续安装验证

同日用户要求安装并推送。安装前使用 SQLite 在线备份保存数据库，并保留旧应用。升级后按旧表的原字段逐表比较，已有数据无变化。首次启动发现 WKWebView 复用旧 HTML 缓存；桌面入口请求改为忽略本地缓存，手动重新载入改为 `reloadFromOrigin()`，避免升级后仍显示旧导航。重新构建的 macOS 包再次通过原生编译与签名验证。
