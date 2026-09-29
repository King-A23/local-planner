# 规划地图、路线图与行动落地

2026-09-29。用户确认本轮完整实现：全局目标地图 → 单目标阶段路线图 → 按需将行动加入今天。本约定替代目标首版中“不包含关系、批量路线生成”的限制；其余同步、提醒、自动排程等非目标继续保持。

## 使用方式

导航显示“规划”，原 `/goals`、`/goals/{id}` 链接和 Cmd+4 保留。目标支持另一个主要目标，或独立存在；大致时间标签与支持关系分别编辑。阶段路线呈现成果、当前阶段和候选行动，日期可以留空。

规划行动不会因为保存路线图进入待办。“加入今天”或“加入待办”时才创建正式 Task；关联已有任务则复用其 ID。正式任务的标题、安排、完成和删除状态始终以 Task 为准。完成、暂停或结束目标不会级联修改任务。

自然语言规划在隔离工作目录中生成结构化草案。用户可以继续调整、撤销草案修改、保存或放弃。保存只更新目标结构，不创建 Task。包含正式任务的关系、已完成记录受到保护；需要修改任务时使用原有任务操作。移除无正式任务的已有目标采用归档，保留其身份和历史。

## 数据与接口

- 数据库迁移 009 增加目标的 `parent_goal_id`、`next_action_id`、阶段成果与时间、候选行动及任务映射；现有目标任务回填为关联行动。010 增加草案与持久请求记录。
- Goal JSON 增加 `parentGoalId`、`nextActionId`、`actions`；Phase 增加 `outcome`、`horizonText`。Action 字段为 `id, goalId, phaseId, title, notes, position, taskId, scheduledDate, completed, discarded`。
- `/api/goals/{id}/actions` 扩展 `set-parent`、`add-action`、`edit-action`、`remove-action`、`next-action`、`materialize-action`、`link-action`。`materialize-action` 接受 `destination: today|inventory`，使用持久 `requestId` 去重；同一行动最多关联一个 Task。旧 `add-task` 等命令语义不变。
- `GET/POST /api/planning/drafts`、`GET /api/planning/drafts/{id}`、`POST /api/planning/drafts/{id}/actions`。操作包括 `update/undo/apply/discard/revert`，携带 `expectedRevision/recoveryGeneration/requestId`。更新提交整个结构化 `document: {goals: [...]}`，实体 ID 必须稳定。
- CLI 新增 `planning list/show/create/update/undo/apply/discard/revert`。`update --document-file PATH` 读取 `{goals: [...]}` JSON；写入都要求 `--expected-revision/--recovery-generation/--request-id`（create 无 revision）。仅最近一次规划保存可撤销；与 HTTP 共用领域校验。
- 草案保存基线版本、对话、最近有效文档、撤销历史及应用前后版本。已有目标变更或恢复数据后，旧草案不能直接覆盖新状态。已落地行动或后续编辑会阻止撤销旧保存。
- Agent run 增加 `mode: planning`、`draftId`、`expectedDraftRevision`、`selectedPhaseId`。规划输出为 `{document: {...}, message?: string}` 或 `{question: string}`。运行、停止、失败均保留最近有效草案，重启标记中断。

## 范围

单主要支持关系、自动排版、可下钻地图；扁平且可排序的阶段；无强制依赖、完成百分比、四象限、甘特图、自动日期安排。未配置助手时手动流程完整可用。

## 兼容与验证

旧目标作为独立目标，保留任务 ID、安排和历史日期快照。新增备份包含草案，旧备份恢复时运行迁移。真实 Agent 测试使用既有 Luna 分组与独立测试目录，不把真实数据库传给助手。最终自动化、浏览器与真实模型测试结果记录在 `planning-validation.md`。
