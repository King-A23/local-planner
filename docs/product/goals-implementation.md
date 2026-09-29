# 目标与轻量阶段：首版实施约定

> 2026-09-29 更新：规划地图、候选行动及 Agent 草案模式已实现。当前范围与接口见 [规划实现](planning-implementation.md)，最新验证见 [规划验收](planning-validation.md)。下文保留原阶段记录。

2026-09-28，用户已确认按照讨论方案分步骤完成开发。本文件记录本次确定范围，覆盖旧冻结范围中不包含长期目标的限制；不引入项目树、同步、提醒或自动 AI 排程。

## 交付顺序与产品行为

1. 目标、一个明确的下一步、复用已有 Task、加入今天；覆盖任务完成/删除/撤销/跨日、历史快照、迁移备份和 Agent。
2. 可选的扁平阶段：添加、编辑、排序、设为当前、完成/跳过/重新打开。完成两步再交付首版。

仅目标名称必填。备注与大致时间为选填文本；大致时间没有到期或逾期语义。目标状态 active / paused / ended，结束原因 achieved / abandoned，可恢复。暂停、结束不改变已有任务的安排与完成状态。每个任务最多属于一个目标及该目标的一个阶段；不直接绑定定期事项系列，关联已有周期任务仅影响本次。一个目标最多指定一个未完成、未删除的下一步；完成/删除/解除关联清空下一步，撤销不抢回后来选择的下一步。

阶段不必设置；只允许一个当前阶段。结束/跳过阶段清空其当前标记及属于该阶段的下一步，不改变任务。没有层级、百分比、依赖、强制日期、批量路线生成。

首页保留清单结构，目标关联只作轻量入口。新“目标”页面突出名称、当前阶段、下一步。帮助说明同步更新。

## 跨层实现契约

领域模块 `domain/goals.py`，由调用方已有 planner_txn 管理事务：
- `create_goal(clock, uow, title, *, notes='', horizon_text='', request_id)` 返回 Goal。
- `change_goal(clock, uow, goal_id, operation, *, expected_revision, **values)` 返回 Goal。
- `goal_payload(uow, goal)` 返回下述 camelCase 对象（位于领域模块，纯读取）。
- `list_goal_payloads(uow)` 返回列表；`goal_candidates(clock, uow)` 返回尚未完成、未删除的已有 Task 选项。

Goal JSON: id, title, notes, horizonText, state, endReason, nextTaskId, focusPhaseId, revision, createdAt, updatedAt, endedAt, phases[], tasks[].
Phase JSON: id, goalId, title, notes, position, status(open/done/skipped).
Task JSON: taskId, title, notes, goalId, phaseId, scheduledDate, completed, targetDate, seriesId.
Candidates 包含上述 Task 字段及 goalTitle，列出待办、今天、已存在未来安排，不生成未来周期事项。
列表响应 `{items: Goal[], serverToday, recoveryGeneration}`；详情 `{...Goal, serverToday, recoveryGeneration}`；candidates 响应 `{items: Task[]}`。

HTTP:
- GET /api/goals；GET /api/goals/candidates；GET /api/goals/{id}
- POST /api/goals: title, notes?, horizonText?, requestId
- POST /api/goals/{id}/actions: operation, expectedRevision, recoveryGeneration, 及操作字段。
- 创建和所有动作都必须显式传 recoveryGeneration（初始值为 null）；页面持有的 generation 变化必须拒绝旧写入。

操作及参数（HTTP camelCase，领域 snake_case）：
- edit: title, notes, horizonText（完整三个字段）
- state: state, endReason（结束必填 achieved/abandoned，其余 null）
- add-task: title, notes?, phaseId?, requestId（持久幂等）
- link-task: taskId, phaseId?, expectedGoalId（null 表示未关联；不同目标拒绝，须先从原目标解除）
- unlink-task: taskId
- next: taskId（null 清空）
- schedule-next: expectedTaskId, expectedScheduledDate（null 为待办）；排到 clock.today，已在今天则幂等，保留时段
- add-phase: title, notes?, requestId（持久幂等）
- edit-phase: phaseId, title, notes, status（完整字段）
- focus-phase: phaseId（null 清空，只允许 open）
- reorder-phases: phaseIds（完整无重复列表）

所有变更使用 expectedRevision 防覆盖；完成/删除/解除任务及相关下一步变动同事务更新 Goal revision。创建类操作 requestId 相同且参数相同返回原目标，不重复创建；参数不同报 Conflict。已结束目标只允许编辑和恢复，暂停目标可整理路线，但不允许 schedule-next。历史关联名称从 DayTaskEntry 的快照读取；不追溯写旧数据。关联快照允许在未封存日更新。

Agent：CLI 明确提供 goal list/show/create/edit/state/add-task/link-task/unlink-task/next/schedule-next 及 phase 操作；CLI goal 写入要求 `--expected-revision`（创建目标除外）、`--recovery-generation`（context 值为空时传 `none`），创建类要求 `--request-id`。context 包含 goals 与 recoveryGeneration。页面 surface 支持 goals/goal + goalId，绝不默认为今天。已有任务命令通过领域钩子维护目标关系。提示词强调只按请求修改、使用稳定 ID、读新 revision、暂停/结束无级联、阶段不自动完成任务。回执覆盖目标/阶段/关联变化。

## 验证

临时数据库验证：旧数据升级、旧备份恢复、新备份恢复、下一步完成/删除/撤销、未来改排保留时间、跨日、封存快照、冲突与幂等、阶段状态、Agent 接口。浏览器用独立测试目录，真实日程不参与测试。构建桌面安装包并验证签名。AI 生成路线仍后置。
