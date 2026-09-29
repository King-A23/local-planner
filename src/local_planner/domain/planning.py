"""Planning drafts never mutate Tasks. Only an explicit apply changes goal structure.

All operations participate in the caller's planner transaction. Documents retain
stable entity IDs across conversation turns and carry a baseline for optimistic
concurrency, including after a backup restore.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import replace

from local_planner.clock import format_utc
from local_planner.domain.errors import Conflict, NotFound, ValidationError
from local_planner.domain.models import Goal, GoalPhase, normalize_notes, normalize_title


def _now(clock):
    return format_utc(clock.now_utc())


def _raw(uow, draft_id):
    draft = uow.planning.get(draft_id)
    if draft is None:
        raise NotFound("找不到这份规划草案")
    return draft


def _generation(uow, supplied):
    if supplied != uow.meta.get("recovery_generation"):
        raise Conflict("数据已恢复，请重新打开规划并生成新草案")


def _editable(uow, draft, revision, generation, *, allow_running=False):
    _generation(uow, generation)
    if draft["recoveryGeneration"] != generation:
        raise Conflict("这份草案来自恢复前的数据，请生成新草案")
    if draft["revision"] != revision:
        raise Conflict("草案已发生变化，请刷新后重试")
    if not allow_running and draft["runStatus"] == "running":
        raise Conflict("助手正在调整草案，请先等待完成或停止执行")


def _snapshot(uow, goal_id=None):
    from local_planner.domain.goals import goal_payload, require_goal
    goals = [require_goal(uow, goal_id)] if goal_id else uow.list_goals()
    return {"goals": [goal_payload(uow, goal) for goal in goals]}


def _index(document):
    return {goal["id"]: goal for goal in document["goals"]}


def _changes(before, after):
    rows = []
    for kind in ("goal", "phase", "action"):
        def flatten(document):
            return {item["id"]: (goal["id"], item) for goal in document["goals"]
                    for item in ([goal] if kind == "goal" else goal.get(kind + "s", []))}
        old, new = flatten(before), flatten(after)
        for entity_id in dict.fromkeys([*old, *new]):
            a, b = old.get(entity_id), new.get(entity_id)
            if a is not None and b is not None:
                # Parent badges reflect scalar changes; child changes get their own badges.
                aa = {k: v for k, v in a[1].items() if k not in {"phases", "actions", "tasks", "revision", "updatedAt"}}
                bb = {k: v for k, v in b[1].items() if k not in {"phases", "actions", "tasks", "revision", "updatedAt"}}
                if aa == bb:
                    continue
            goal_id, item = b or a
            rows.append({"kind": kind, "id": entity_id, "goalId": goal_id,
                         "type": "added" if a is None else "removed" if b is None else "modified",
                         "title": item["title"]})
    return rows


def get_draft(uow, draft_id):
    draft = _raw(uow, draft_id)
    public = {k: v for k, v in draft.items() if k not in {"history", "application", "runBaselineRevision"}}
    public["changes"] = _changes(draft["baseDocument"], draft["document"])
    public["canUndo"] = bool(draft["history"]) and draft["status"] == "editing" and draft["runStatus"] != "running"
    public["canRevert"] = bool(draft.get("application")) and draft["status"] == "applied" and uow.meta.get("latest_planning_save") == draft_id
    return public


def list_drafts(uow, goal_id=None):
    return [get_draft(uow, d["id"]) for d in uow.planning.list()
            if d["scopeGoalId"] == goal_id and d["status"] != "discarded"]


def _request(uow, request_id, values):
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 100:
        raise ValidationError("需要有效的 requestId")
    digest = hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    prior = uow.planning.get_request(request_id)
    if prior and prior[0] != digest:
        raise Conflict("同一 requestId 已用于不同操作")
    return digest, get_draft(uow, prior[1]) if prior else None


def create_draft(clock, uow, *, goal_id=None, phase_id=None, request_id, recovery_generation):
    _generation(uow, recovery_generation)
    digest, prior = _request(uow, request_id, {"operation": "create", "goalId": goal_id, "phaseId": phase_id})
    if prior:
        return prior
    document = _snapshot(uow, goal_id)
    if phase_id and (not goal_id or phase_id not in {p["id"] for p in document["goals"][0]["phases"]}):
        raise ValidationError("所选阶段不属于当前目标")
    draft = {"id": str(uuid.uuid4()), "scopeGoalId": goal_id, "selectedPhaseId": phase_id,
             "status": "editing", "runStatus": "idle", "revision": 1,
             "document": document, "baseDocument": copy.deepcopy(document),
             "baseGoalRevisions": {g["id"]: g["revision"] for g in document["goals"]},
             "conversation": [], "history": [], "application": None,
             "runRequestId": None, "lastError": None, "recoveryGeneration": recovery_generation,
             "createdAt": _now(clock), "updatedAt": _now(clock)}
    uow.planning.save(draft)
    uow.planning.save_request(request_id, digest, draft["id"])
    return get_draft(uow, draft["id"])


def _identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValidationError("规划内容需要有效且稳定的 ID")
    return value


def _text(value, limit=200):
    if not isinstance(value, str) or len(value) > limit:
        raise ValidationError(f"规划字段最长 {limit} 字")
    return value.strip()


def _validate_graph(uow, document):
    parents = {g.id: g.parent_goal_id for g in uow.list_goals()}
    parents.update({g["id"]: g["parentGoalId"] for g in document["goals"]})
    for gid in parents:
        chain = set()
        current = gid
        while current is not None:
            if current in chain:
                raise ValidationError("目标支持关系不能形成循环")
            chain.add(current)
            if current not in parents:
                raise ValidationError("主要支持目标不存在")
            current = parents[current]


def normalize_document(uow, draft, document):
    """Validate model output against its immutable baseline, not model assurances."""
    if not isinstance(document, dict) or set(document) != {"goals"} or not isinstance(document["goals"], list):
        raise ValidationError("规划结果必须包含 goals 数组")
    if len(document["goals"]) > 100 or len(json.dumps(document, ensure_ascii=False)) > 1_000_000:
        raise ValidationError("规划内容过大，请分次调整")
    baseline = _index(draft["baseDocument"])
    result, seen_goals, seen_phases, seen_actions = [], set(), set(), set()
    live = {g.id: g for g in uow.list_goals()}
    for raw in document["goals"]:
        if not isinstance(raw, dict):
            raise ValidationError("目标格式无效")
        gid = _identifier(raw.get("id"))
        if gid in seen_goals or (gid in live and gid not in baseline):
            raise ValidationError("目标 ID 重复或超出当前草案范围")
        if draft["scopeGoalId"] and gid != draft["scopeGoalId"]:
            raise ValidationError("请在全局规划中添加其他目标")
        seen_goals.add(gid)
        base = baseline.get(gid, {})
        state = base.get("state", "active")
        if raw.get("state", state) != state or raw.get("endReason", base.get("endReason")) != base.get("endReason"):
            raise ValidationError("请通过目标状态操作完成、暂停或恢复目标")
        parent = raw.get("parentGoalId", base.get("parentGoalId"))
        if parent is not None:
            _identifier(parent)
        goal = {**base, "id": gid, "title": normalize_title(raw.get("title")),
                "notes": normalize_notes(raw.get("notes", "")), "horizonText": _text(raw.get("horizonText", "")),
                "parentGoalId": parent, "state": state, "endReason": base.get("endReason"),
                "revision": base.get("revision", 0), "nextTaskId": base.get("nextTaskId"),
                "nextActionId": raw.get("nextActionId", base.get("nextActionId")),
                "focusPhaseId": raw.get("focusPhaseId", base.get("focusPhaseId")),
                "phases": [], "actions": [], "tasks": base.get("tasks", [])}
        if raw.get("nextTaskId", base.get("nextTaskId")) != base.get("nextTaskId") or raw.get("tasks", base.get("tasks", [])) != base.get("tasks", []):
            raise ValidationError("规划草案不能直接修改正式任务")
        phases = raw.get("phases", [])
        actions = raw.get("actions", [])
        if not isinstance(phases, list) or not isinstance(actions, list) or len(phases) > 100 or len(actions) > 500:
            raise ValidationError("阶段或行动格式无效，或数量过多")
        old_phases = {p["id"]: p for p in base.get("phases", [])}
        for pos, p in enumerate(phases):
            if not isinstance(p, dict):
                raise ValidationError("阶段格式无效")
            pid = _identifier(p.get("id"))
            existing = uow.get_phase(pid)
            if pid in seen_phases or (existing and (pid not in old_phases or existing.goal_id != gid)):
                raise ValidationError("阶段 ID 重复或属于其他目标")
            seen_phases.add(pid)
            if p.get("goalId", gid) != gid:
                raise ValidationError("阶段不属于这个目标")
            status = p.get("status", old_phases.get(pid, {}).get("status", "open"))
            if status not in {"open", "done", "skipped"}:
                raise ValidationError("阶段状态无效")
            phase = {"id": pid, "goalId": gid, "title": normalize_title(p.get("title")),
                     "notes": normalize_notes(p.get("notes", "")), "position": pos, "status": status,
                     "outcome": normalize_notes(p.get("outcome", "")), "horizonText": _text(p.get("horizonText", ""))}
            previous = old_phases.get(pid)
            if previous and previous["status"] == "done" and any(phase[k] != previous.get(k, "") for k in ("title", "notes", "outcome", "horizonText", "status")):
                raise ValidationError("已完成阶段保留原记录，请在路线图中明确编辑")
            goal["phases"].append(phase)
        phase_ids = {p["id"] for p in goal["phases"]}
        for pid, phase in old_phases.items():
            if pid not in phase_ids and (phase["status"] == "done" or any(a.get("taskId") and a.get("phaseId") == pid for a in base.get("actions", []))):
                raise ValidationError("不能移除已完成或包含正式任务的阶段")
        old_actions = {a["id"]: a for a in base.get("actions", [])}
        for pos, a in enumerate(actions):
            if not isinstance(a, dict):
                raise ValidationError("行动格式无效")
            aid = _identifier(a.get("id"))
            existing = uow.get_goal_action(aid)
            if aid in seen_actions or (existing and aid not in old_actions):
                raise ValidationError("行动 ID 重复或属于其他目标")
            seen_actions.add(aid)
            if a.get("goalId", gid) != gid or (a.get("phaseId") is not None and a["phaseId"] not in phase_ids):
                raise ValidationError("行动引用了其他目标或不存在的阶段")
            previous = old_actions.get(aid, {})
            task_id = previous.get("taskId")
            if a.get("taskId") != task_id:
                raise ValidationError("请使用关联或加入今天操作创建正式任务关系")
            action = {"id": aid, "goalId": gid, "phaseId": a.get("phaseId"),
                      "title": normalize_title(a.get("title")), "notes": normalize_notes(a.get("notes", "")),
                      "position": pos, "taskId": task_id,
                      "scheduledDate": previous.get("scheduledDate"), "completed": previous.get("completed", False),
                      "discarded": previous.get("discarded", False)}
            if task_id and any(action[k] != previous.get(k) for k in ("title", "notes", "phaseId")):
                raise ValidationError("正式任务的内容和阶段请在任务操作中修改")
            if any(a.get(k, action[k]) != action[k] for k in ("scheduledDate", "completed", "discarded")):
                raise ValidationError("规划草案不能安排、完成或删除正式任务")
            goal["actions"].append(action)
        if any(a.get("taskId") and a["id"] not in {x["id"] for x in goal["actions"]} for a in old_actions.values()):
            raise ValidationError("草案不能移除正式任务关联")
        open_ids = {p["id"] for p in goal["phases"] if p["status"] == "open"}
        if goal["focusPhaseId"] not in open_ids:
            goal["focusPhaseId"] = None
        candidate = next((a for a in goal["actions"] if a["id"] == goal["nextActionId"]), None)
        if candidate is None or candidate["taskId"] or (candidate["phaseId"] and candidate["phaseId"] not in open_ids):
            goal["nextActionId"] = None
        if goal["nextTaskId"] and goal["nextActionId"]:
            raise ValidationError("一个目标只能有一个下一步")
        if goal["nextTaskId"]:
            selected = next((a for a in goal["actions"] if a["taskId"] == goal["nextTaskId"]), None)
            if selected and selected["phaseId"] and selected["phaseId"] not in open_ids:
                goal["nextTaskId"] = None
        # Ended goals deliberately retain their historical text, but the
        # ordinary goal API only allows their text/state to change. A draft
        # must not become a back door for moving its route or support link.
        if base and state == "ended":
            structural_keys = ("parentGoalId", "nextTaskId", "nextActionId", "focusPhaseId", "phases", "actions")
            if any(goal[key] != base.get(key) for key in structural_keys):
                raise Conflict("目标已结束，请先恢复目标")
        result.append(goal)
    if draft["scopeGoalId"] and draft["scopeGoalId"] not in seen_goals:
        raise ValidationError("当前目标不能从自己的草案中移除")
    for gid, old in baseline.items():
        if gid not in seen_goals and (old.get("tasks") or any(a.get("taskId") for a in old.get("actions", [])) or old["state"] == "ended"):
            raise ValidationError("保留有正式任务或已结束目标的记录；请通过目标状态操作收起")
    _validate_graph(uow, {"goals": result})
    return {"goals": result}


def _save(clock, uow, draft):
    draft["revision"] += 1
    draft["updatedAt"] = _now(clock)
    uow.planning.save(draft)
    return get_draft(uow, draft["id"])


def _push(draft):
    draft["history"].append(copy.deepcopy(draft["document"]))
    draft["history"] = draft["history"][-20:]


def begin_draft_run(clock, uow, draft_id, *, expected_revision, recovery_generation, prompt, request_id, selected_phase_id=None):
    draft = _raw(uow, draft_id)
    _editable(uow, draft, expected_revision, recovery_generation)
    if draft["status"] != "editing":
        raise Conflict("请新建草案继续调整已保存的规划")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10000:
        raise ValidationError("请写下要调整的规划")
    if selected_phase_id:
        if selected_phase_id not in {p["id"] for g in draft["document"]["goals"] for p in g["phases"]}:
            raise ValidationError("当前草案中没有所选阶段")
    draft["selectedPhaseId"] = selected_phase_id
    draft["conversation"].append({"role": "user", "content": prompt.strip()})
    draft["runStatus"], draft["runRequestId"], draft["lastError"] = "running", request_id, None
    return _save(clock, uow, draft)


def finish_draft_run(clock, uow, draft_id, *, request_id, recovery_generation, document=None, question=None, message=None, error=None, stopped=False):
    _generation(uow, recovery_generation)
    draft = _raw(uow, draft_id)
    if draft["recoveryGeneration"] != recovery_generation or draft["runRequestId"] != request_id or draft["runStatus"] != "running":
        raise Conflict("这次助手结果已过期，保留当前草案")
    if stopped or error:
        draft["runStatus"] = "stopped" if stopped else "failed"
        draft["lastError"] = str(error or "已停止，原草案已保留")[:10000]
    else:
        if document is not None and question is not None:
            raise ValidationError("助手应返回规划或问题，不能同时返回两者")
        if document is not None:
            normalized = normalize_document(uow, draft, document)
            _push(draft)
            draft["document"] = normalized
        elif not isinstance(question, str) or not question.strip():
            raise ValidationError("助手未返回有效规划或问题")
        draft["conversation"].append({"role": "assistant", "content": _text(question or message or "规划草案已更新，可继续调整或保存。", 10000)})
        draft["runStatus"], draft["lastError"] = "succeeded", None
    return _save(clock, uow, draft)


def interrupt_draft_runs(clock, uow):
    for draft in uow.planning.list():
        if draft["runStatus"] == "running":
            draft["runStatus"] = "interrupted"
            draft["lastError"] = "上次执行已中断，最近有效草案已保留。"
            _save(clock, uow, draft)


def _verify_baseline(uow, revisions):
    for gid, revision in revisions.items():
        live = uow.get_goal(gid)
        if live is None or live.revision != revision:
            raise Conflict("相关目标已经变化，草案已保留；请刷新并基于当前规划重新调整")


def _write_document(clock, uow, document, previous):
    """Replace only validated goal structure; never call task creation or scheduling."""
    from local_planner.domain.models import GoalAction
    from local_planner.domain.goals import refresh_task_snapshots
    wanted, old = _index(document), _index(previous)
    changed = {row["goalId"] for row in _changes(previous, document)}
    now = _now(clock)
    # Clear pointers first, then insert all parents before their children/links.
    for gid in changed:
        g = uow.get_goal(gid)
        if g:
            uow.save_goal(replace(g, next_task_id=None, next_action_id=None, focus_phase_id=None))
    for gid, raw in wanted.items():
        if gid not in changed:
            continue
        current = uow.get_goal(gid)
        if current is None:
            current = Goal(
                gid, raw["title"], raw["notes"], raw["horizonText"], "active",
                None, None, None, None, None, 0, now, now,
            )
        uow.save_goal(replace(current, title=raw["title"], notes=raw["notes"], horizon_text=raw["horizonText"],
                              state=raw["state"], end_reason=raw.get("endReason"), ended_at=raw.get("endedAt"),
                              parent_goal_id=None, revision=current.revision + 1, updated_at=now))
    for gid, raw in wanted.items():
        if gid not in changed:
            continue
        phase_ids = {p["id"] for p in raw["phases"]}
        action_ids = {a["id"] for a in raw["actions"]}
        for action in uow.list_goal_actions(gid):
            if action.id not in action_ids:
                uow.delete_goal_action(action.id)
        for p in raw["phases"]:
            uow.save_phase(GoalPhase(p["id"], gid, p["title"], p["notes"], p["position"], p["status"], p["outcome"], p["horizonText"]))
        for a in raw["actions"]:
            uow.save_goal_action(GoalAction(a["id"], gid, a["phaseId"], a["title"], a["notes"], a["position"], a["taskId"]))
        for phase in uow.list_phases(gid):
            if phase.id not in phase_ids:
                uow.delete_phase(phase.id)
        g = uow.get_goal(gid)
        uow.save_goal(replace(g, parent_goal_id=raw["parentGoalId"], next_action_id=raw["nextActionId"],
                              next_task_id=raw["nextTaskId"], focus_phase_id=raw["focusPhaseId"]))
        for task in uow.list_goal_tasks(gid):
            refresh_task_snapshots(clock, uow, task)
    # Existing goal removal is archival, preserving identity and recovery history.
    for gid in old.keys() - wanted.keys():
        g = uow.get_goal(gid)
        uow.save_goal(replace(g, state="ended", end_reason="abandoned", ended_at=now,
                              next_task_id=None, next_action_id=None, focus_phase_id=None,
                              revision=g.revision + 1, updated_at=now))
    return changed


def change_draft(clock, uow, draft_id, operation, *, expected_revision, recovery_generation, request_id, document=None):
    _generation(uow, recovery_generation)
    digest, prior = _request(uow, request_id, {"draftId": draft_id, "operation": operation,
                                              "expectedRevision": expected_revision, "document": document})
    if prior:
        return prior
    draft = _raw(uow, draft_id)
    _editable(uow, draft, expected_revision, recovery_generation)
    if operation == "revert":
        application = draft.get("application")
        if draft["status"] != "applied" or not application or uow.meta.get("latest_planning_save") != draft_id:
            raise Conflict("没有可撤销的规划保存")
        _verify_baseline(uow, application["revisions"])
        try:
            _validate_graph(uow, application["before"])
        except ValidationError as exc:
            raise Conflict("目标支持关系已变化，不能撤销这次保存") from exc
        # Revisions include task changes, materialization, and relation edits.
        _write_document(clock, uow, application["before"], application["after"])
        draft["status"] = "discarded"
        draft["application"] = None
        uow.meta.set("latest_planning_save", "")
    elif draft["status"] != "editing":
        raise Conflict("这份草案已保存或放弃，请新建草案")
    elif operation == "update":
        normalized = normalize_document(uow, draft, document)
        _push(draft)
        draft["document"] = normalized
    elif operation == "undo":
        if not draft["history"]:
            raise Conflict("没有可撤销的草案修改")
        draft["document"] = draft["history"].pop()
    elif operation == "discard":
        draft["status"] = "discarded"
    elif operation == "apply":
        _verify_baseline(uow, draft["baseGoalRevisions"])
        normalized = normalize_document(uow, draft, draft["document"])
        changed = _write_document(clock, uow, normalized, draft["baseDocument"])
        from local_planner.domain.goals import goal_payload
        after = {"goals": [goal_payload(uow, uow.get_goal(gid)) for gid in sorted(changed)]}
        before = {"goals": [g for g in draft["baseDocument"]["goals"] if g["id"] in changed]}
        draft["application"] = {"before": before, "after": after,
                                "revisions": {g["id"]: g["revision"] for g in after["goals"]}}
        draft["document"] = normalized
        draft["status"] = "applied"
        uow.meta.set("latest_planning_save", draft_id)
    else:
        raise ValidationError("不支持的草案操作")
    result = _save(clock, uow, draft)
    uow.planning.save_request(request_id, digest, draft_id)
    return result
