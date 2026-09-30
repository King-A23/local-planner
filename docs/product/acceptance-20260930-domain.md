# 2026-09-30 领域验收：规划行动与持久草案

验收对象为当前 HEAD `9db0d0c`。通过 FastAPI `TestClient` 对全新数据库执行，不启动服务；数据库为 `build/acceptance-20260930/domain-unit/acceptance.sqlite`。可用脚本 `build/acceptance-20260930/domain-unit/accept.py` 重跑，逐项请求与 JSON 断言证据在同目录 `evidence.json`。

验收结果：4 组断言全部通过。

- 候选行动加入待办，再加入今天后保留同一 Task ID；重复 `requestId` 返回同一行动/Task 关联，不重复创建任务。
- 关联已有 Task ID 的行动加入今天后仍使用原 Task ID。
- 完成和取消完成即时回流到 Action 的 `completed` 状态。删除正式任务会移除对应关联行动行；撤销删除后以原 Action ID 和 Task ID 恢复，完成状态也保持。
- 草案 preview、update、undo、apply、revert、discard 均通过。草案在关闭并重新打开数据库连接后仍可读取；apply 只写入目标结构，没有创建 Task；过期 revision 返回 HTTP 409。

revert 会恢复保存前的规划状态；对草案新增目标按归档语义保留记录，状态为 `ended`。本次验收数据库和脚本均在 `build/acceptance-20260930/domain-unit/`，未使用真实数据库或真实模型。
