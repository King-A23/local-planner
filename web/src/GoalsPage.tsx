import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import {
  changeGoal,
  completeInventoryTask,
  completeTodo,
  createGoal,
  errorMessage,
  getGoal,
  listGoalCandidates,
  listGoals,
  type Goal,
  type GoalEndReason,
  type GoalList,
  type GoalPhase,
  type GoalPhaseStatus,
  type GoalState,
  type GoalTask,
} from "./api";
import { Modal } from "./Modal";
import { ReorderList } from "./ReorderList";
import { handleNavClick, navigate } from "./route";
import { useEntryKeyboard } from "./useEntryKeyboard";

type GoalResponse = Goal & Pick<GoalList, "serverToday" | "recoveryGeneration">;
type GoalEditor = { item?: Goal; revision?: number; recoveryGeneration?: string | null } | null;
type PhaseEditor = { item?: GoalPhase; revision: number; recoveryGeneration: string | null } | null;
type TaskEditor = { phaseId: string | null; revision: number; recoveryGeneration: string | null } | null;
type TaskPicker = "link" | "next" | null;

function requestId(): string {
  return crypto.randomUUID();
}

function idFor(
  ref: { current: { fingerprint: string; id: string } | null },
  values: unknown,
): string {
  const fingerprint = JSON.stringify(values);
  if (!ref.current || ref.current.fingerprint !== fingerprint) ref.current = { fingerprint, id: requestId() };
  return ref.current.id;
}

function stateText(state: GoalState, reason: GoalEndReason): string {
  if (state === "active") return "进行中";
  if (state === "paused") return "已暂停";
  return reason === "achieved" ? "已达成" : "已结束";
}

function phaseText(status: GoalPhaseStatus): string {
  return status === "open" ? "进行中" : status === "done" ? "已完成" : "已跳过";
}

function taskLocation(task: GoalTask, today: string): string {
  if (task.completed) return "已完成";
  if (!task.scheduledDate) return "待办";
  if (task.scheduledDate === today) return "今天";
  return task.scheduledDate;
}

function taskHref(task: GoalTask): string {
  return task.scheduledDate ? `/d/${task.scheduledDate}` : "/inventory";
}

function phaseOf(goal: Goal, id: string | null): GoalPhase | undefined {
  return id ? goal.phases.find((phase) => phase.id === id) : undefined;
}

export function GoalsPage({ onChange, onRecoveryGeneration, refreshToken }: { onChange?: () => void; onRecoveryGeneration?: (generation: string | null) => void; refreshToken?: number }) {
  const [data, setData] = useState<GoalList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<GoalEditor>(null);
  const [busy, setBusy] = useState(false);
  const createRequest = useRef<{ fingerprint: string; id: string } | null>(null);

  async function reload(): Promise<GoalList> {
    const next = await listGoals();
    setData(next);
    onRecoveryGeneration?.(next.recoveryGeneration);
    setError(null);
    return next;
  }
  useEffect(() => { void reload().catch((err) => { setData({ items: [], serverToday: "", recoveryGeneration: null }); setError(errorMessage(err)); }); }, [refreshToken]);

  async function save(input: { title: string; notes: string; horizonText: string }, snapshot: NonNullable<GoalEditor>): Promise<void> {
    setBusy(true); setError(null);
    try {
      if (editor?.item) {
        const changed = await changeGoal(editor.item.id, {
          operation: "edit", expectedRevision: snapshot.revision ?? editor.item.revision,
          recoveryGeneration: snapshot.recoveryGeneration ?? null, ...input,
        });
        navigate(`/goals/${changed.id}`);
      } else {
        const created = await createGoal({ ...input, requestId: idFor(createRequest, input), recoveryGeneration: snapshot.recoveryGeneration ?? null });
        navigate(`/goals/${created.id}`);
        createRequest.current = null;
      }
      setEditor(null); onChange?.();
    } catch (err: unknown) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function refreshEditor(): Promise<void> {
    try {
      const next = await reload();
      setEditor((current) => current ? { ...current, recoveryGeneration: next.recoveryGeneration } : current);
    } catch (err: unknown) { setError(errorMessage(err)); }
  }

  const active = (data?.items ?? []).filter((goal) => goal.state === "active");
  const paused = (data?.items ?? []).filter((goal) => goal.state === "paused");
  const ended = (data?.items ?? []).filter((goal) => goal.state === "ended");
  return <main className="page goals-page">
    <div className="page-heading-row">
      <div><h1>目标</h1></div>
      <button type="button" className="button-primary" disabled={!data || busy} onClick={() => data && setEditor({ recoveryGeneration: data.recoveryGeneration })}>新建目标</button>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {!data ? <p>加载中…</p> : null}
    {data && data.items.length === 0 ? <section className="empty-state goals-empty"><h2>还没有目标</h2><p>例如「通过 CCF CSP 认证」。先记下方向，再选一个下一步。</p></section> : null}
    {active.length > 0 && <GoalGroup title="进行中" goals={active} today={data?.serverToday ?? ""} />}
    {paused.length > 0 && <GoalGroup title="已暂停" goals={paused} today={data?.serverToday ?? ""} />}
    {ended.length > 0 && <GoalGroup title="已结束" goals={ended} today={data?.serverToday ?? ""} />}
    {editor && <GoalEditorDialog item={editor.item} busy={busy} error={error} onClose={() => setEditor(null)} onRefresh={refreshEditor} onSave={(input) => save(input, editor)} />}
  </main>;
}

function GoalGroup({ title, goals, today }: { title: string; goals: Goal[]; today: string }) {
  return <section className="goal-group"><h2>{title}</h2><ul className="goal-list">
    {goals.map((goal) => {
      const next = goal.tasks.find((task) => task.taskId === goal.nextTaskId);
      const focus = phaseOf(goal, goal.focusPhaseId);
      return <li key={goal.id} className="goal-card">
        <a className="goal-card-link" href={`/goals/${goal.id}`} onClick={(event) => handleNavClick(event, `/goals/${goal.id}`)}>
          <div className="goal-card-title"><h3>{goal.title}</h3><span className={`goal-state state-${goal.state}`}>{stateText(goal.state, goal.endReason)}</span></div>
          {focus && <p className="goal-card-line">当前阶段：{focus.title}</p>}
          {next ? <p className="goal-card-line goal-next-line">下一步：{next.title}<span>{taskLocation(next, today)}</span></p> : <p className="goal-card-line muted">还没有选择下一步</p>}
        </a>
      </li>;
    })}
  </ul></section>;
}

export function GoalDetailPage({ id, onChange, onRecoveryGeneration, refreshToken }: { id: string; onChange?: () => void; onRecoveryGeneration?: (generation: string | null) => void; refreshToken?: number }) {
  const [goal, setGoal] = useState<GoalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [editor, setEditor] = useState<GoalEditor>(null);
  const [phaseEditor, setPhaseEditor] = useState<PhaseEditor>(null);
  const [taskPicker, setTaskPicker] = useState<TaskPicker>(null);
  const [addTask, setAddTask] = useState<TaskEditor>(null);
  const addTaskRequest = useRef<{ fingerprint: string; id: string } | null>(null);
  const addPhaseRequest = useRef<{ fingerprint: string; id: string } | null>(null);
  const latestGoal = useRef(goal);
  latestGoal.current = goal;

  async function reload(): Promise<GoalResponse> {
    const next = await getGoal(id);
    setGoal(next); setError(null);
    onRecoveryGeneration?.(next.recoveryGeneration);
    return next;
  }
  useEffect(() => { void reload().catch((err) => { setGoal(null); setError(errorMessage(err)); }); }, [id, refreshToken]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function mutate(work: (current: GoalResponse) => Promise<GoalResponse>, message?: string): Promise<GoalResponse | null> {
    const current = latestGoal.current;
    if (!current || busy) return null;
    setBusy(true); setError(null);
    try {
      const next = await work(current);
      setGoal(next);
      onRecoveryGeneration?.(next.recoveryGeneration);
      setNotice(message ?? null);
      onChange?.();
      return next;
    } catch (err: unknown) {
      setError(errorMessage(err));
      return null;
    } finally { setBusy(false); }
  }
  function action(operation: Parameters<typeof changeGoal>[1]["operation"], values: Record<string, unknown>, message?: string) {
    return mutate((current) => changeGoal(current.id, {
      operation, expectedRevision: current.revision, recoveryGeneration: current.recoveryGeneration, ...values,
    }), message);
  }
  async function saveGoal(input: { title: string; notes: string; horizonText: string }, snapshot: NonNullable<GoalEditor>) {
    const changed = await mutate((current) => changeGoal(current.id, {
      operation: "edit", expectedRevision: snapshot.revision ?? current.revision,
      recoveryGeneration: snapshot.recoveryGeneration ?? null, ...input,
    }), "目标已更新");
    if (changed) setEditor(null);
  }
  async function refreshGoalEditor(): Promise<void> {
    try {
      const fresh = await reload();
      setEditor((current) => current ? {
        ...current, item: fresh, revision: fresh.revision,
        recoveryGeneration: fresh.recoveryGeneration,
      } : current);
      setError(null);
    } catch (err: unknown) { setError(errorMessage(err)); }
  }
  async function refreshPhaseEditor(): Promise<void> {
    try {
      const fresh = await reload();
      setPhaseEditor((current) => current ? { ...current, revision: fresh.revision, recoveryGeneration: fresh.recoveryGeneration } : current);
      setError(null);
    } catch (err: unknown) { setError(errorMessage(err)); }
  }
  async function refreshTaskEditor(): Promise<void> {
    try {
      const fresh = await reload();
      setAddTask((current) => current ? { ...current, revision: fresh.revision, recoveryGeneration: fresh.recoveryGeneration } : current);
      setError(null);
    } catch (err: unknown) { setError(errorMessage(err)); }
  }
  async function savePhase(input: { title: string; notes: string; status: GoalPhaseStatus }) {
    if (!phaseEditor) return;
    const changed = await mutate((current) => changeGoal(current.id, {
      operation: phaseEditor.item ? "edit-phase" : "add-phase",
      expectedRevision: phaseEditor.revision, recoveryGeneration: phaseEditor.recoveryGeneration,
      ...(phaseEditor.item ? { phaseId: phaseEditor.item.id, ...input } : { title: input.title, notes: input.notes, requestId: idFor(addPhaseRequest, { title: input.title, notes: input.notes }) }),
    }), phaseEditor.item ? "阶段已更新" : "阶段已添加");
    if (changed) { setPhaseEditor(null); addPhaseRequest.current = null; }
  }
  async function createTask(input: { title: string; notes: string; phaseId: string | null }) {
    if (!addTask) return;
    const changed = await mutate((current) => changeGoal(current.id, {
      operation: "add-task", expectedRevision: addTask.revision, recoveryGeneration: addTask.recoveryGeneration,
      ...input, requestId: idFor(addTaskRequest, input),
    }), "行动已添加");
    if (changed) { setAddTask(null); addTaskRequest.current = null; }
  }
  const activeTasks = (goal?.tasks ?? []).filter((task) => !task.completed);
  const completedTasks = (goal?.tasks ?? []).filter((task) => task.completed);
  const next = goal?.tasks.find((task) => task.taskId === goal.nextTaskId) ?? null;
  const focused = goal ? phaseOf(goal, goal.focusPhaseId) : undefined;
  async function completeTask(task: GoalTask) {
    if (busy || task.completed) return;
    setBusy(true); setError(null);
    try {
      if (task.scheduledDate) await completeTodo(task.scheduledDate, task.taskId);
      else await completeInventoryTask(task.taskId);
      await reload();
      setNotice("行动已完成"); onChange?.();
    } catch (err: unknown) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  if (!goal && !error) return <main className="page"><p>加载中…</p></main>;
  if (!goal) return <main className="page"><p className="error">{error}</p><a href="/goals" onClick={(event) => handleNavClick(event, "/goals")}>返回目标</a></main>;
  const canSchedule = goal.state === "active" && Boolean(next) && !next?.completed;
  const longNotes = goal.notes.length > 180 || goal.notes.split("\n").length > 3;
  const scheduleLabel = next?.scheduledDate === goal.serverToday ? "已在今天" : next?.scheduledDate ? `改排到今天（原定 ${next.scheduledDate}）` : "加入今天";
  return <main className="page goal-detail-page">
    <div className="goal-back"><a href="/goals" onClick={(event) => handleNavClick(event, "/goals")}>← 目标</a></div>
    <header className="goal-header">
      <div><div className="goal-title-row"><h1>{goal.title}</h1><span className={`goal-state state-${goal.state}`}>{stateText(goal.state, goal.endReason)}</span></div>
        {goal.horizonText && <p className="goal-horizon">{goal.horizonText}</p>}
        {goal.notes && <div className={`goal-notes${longNotes ? " is-collapsible" : ""}${notesOpen ? " is-open" : ""}`}><p>{goal.notes}</p>{longNotes && <button type="button" className="linkish quiet" onClick={() => setNotesOpen((open) => !open)}>{notesOpen ? "收起备注" : "展开备注"}</button>}</div>}
      </div>
      <button className="button-secondary" type="button" disabled={busy} onClick={() => setEditor({ item: goal, revision: goal.revision, recoveryGeneration: goal.recoveryGeneration })}>编辑</button>
    </header>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p className="notice" role="status">{notice}</p>}

    <section className="goal-next-section" aria-labelledby="goal-next-heading">
      <div className="section-heading-row"><div><h2 id="goal-next-heading">下一步</h2></div>
        {goal.state !== "ended" && <button type="button" className="linkish" disabled={busy} onClick={() => setTaskPicker("next")}>选择下一步</button>}</div>
      {next ? <div className="goal-next-card"><div><strong>{next.title}</strong><span className="goal-task-meta">{taskLocation(next, goal.serverToday)}{next.phaseId && phaseOf(goal, next.phaseId) ? ` · ${phaseOf(goal, next.phaseId)!.title}` : ""}</span></div>
        <div className="goal-next-actions"><a href={taskHref(next)} onClick={(event) => handleNavClick(event, taskHref(next))}>查看</a>
          {canSchedule && <button type="button" className="button-primary" disabled={busy || next.scheduledDate === goal.serverToday} onClick={() => void action("schedule-next", { expectedTaskId: next.taskId, expectedScheduledDate: next.scheduledDate }, "下一步已加入今天")}>{scheduleLabel}</button>}
          {goal.state !== "ended" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("next", { taskId: null }, "已清除下一步")}>清除</button>}</div>
      </div> : <p className="goal-next-empty">选一件未完成的行动，让这个目标有清晰的起点。</p>}
    </section>

    <section className="goal-route-section" aria-labelledby="goal-route-heading">
      <div className="section-heading-row"><div><h2 id="goal-route-heading">阶段</h2></div><button type="button" className="linkish" disabled={busy || goal.state === "ended"} onClick={() => setPhaseEditor({ revision: goal.revision, recoveryGeneration: goal.recoveryGeneration })}>添加阶段</button></div>
      {goal.phases.length === 0 ? <p className="goal-subtle-empty">不需要阶段也可以直接推进。</p> : <ReorderList items={goal.phases} getId={(phase) => phase.id} getLabel={(phase) => phase.title} writable={goal.state !== "ended" && !busy}
        onReorder={async (phaseIds) => Boolean(await action("reorder-phases", { phaseIds }, "阶段顺序已更新"))}>
        {(phase, row) => <li {...row.attributes} className="goal-phase-row">
          {row.handle}<div className="goal-phase-main"><button type="button" className="goal-phase-title" disabled={busy || goal.state === "ended"} onClick={() => setPhaseEditor({ item: phase, revision: goal.revision, recoveryGeneration: goal.recoveryGeneration })}>{phase.title}</button>{phase.notes && <span className="goal-phase-notes">{phase.notes}</span>}</div>
          <span className={`phase-status phase-${phase.status}`}>{phaseText(phase.status)}</span>
          {goal.state !== "ended" && <div className="goal-phase-actions">
            {phase.status === "open" && goal.focusPhaseId !== phase.id && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("focus-phase", { phaseId: phase.id }, "已设为当前阶段")}>设为当前</button>}
            {goal.focusPhaseId === phase.id && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("focus-phase", { phaseId: null }, "已取消当前阶段")}>当前</button>}
            {phase.status === "open" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("edit-phase", { phaseId: phase.id, title: phase.title, notes: phase.notes, status: "done" }, "阶段已完成")}>完成</button>}
            {phase.status === "open" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("edit-phase", { phaseId: phase.id, title: phase.title, notes: phase.notes, status: "skipped" }, "阶段已跳过")}>跳过</button>}
            {phase.status !== "open" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("edit-phase", { phaseId: phase.id, title: phase.title, notes: phase.notes, status: "open" }, "阶段已重新打开")}>重新打开</button>}
          </div>}
        </li>}
      </ReorderList>}
    </section>

    <section className="goal-actions-section" aria-labelledby="goal-actions-heading">
      <div className="section-heading-row"><div><h2 id="goal-actions-heading">行动</h2></div>
        {goal.state !== "ended" && <div className="goal-actions-add"><button type="button" className="linkish" disabled={busy} onClick={() => setAddTask({ phaseId: focused?.id ?? null, revision: goal.revision, recoveryGeneration: goal.recoveryGeneration })}>添加行动</button><button type="button" className="linkish" disabled={busy} onClick={() => setTaskPicker("link")}>关联已有待办</button></div>}</div>
      {activeTasks.length === 0 ? <p className="goal-subtle-empty">{completedTasks.length > 0 ? "当前行动已完成。" : "还没有行动。先添加或关联一件待办。"}</p> : <ul className="goal-task-list">{activeTasks.map((task) => <li key={task.taskId} className={task.taskId === goal.nextTaskId ? "is-next" : ""}>
        <div><a href={taskHref(task)} onClick={(event) => handleNavClick(event, taskHref(task))}>{task.title}</a><span className="goal-task-meta">{taskLocation(task, goal.serverToday)}{task.phaseId && phaseOf(goal, task.phaseId) ? ` · ${phaseOf(goal, task.phaseId)!.title}` : ""}</span></div>
        {goal.state !== "ended" && <div className="goal-task-actions"><button type="button" className="linkish quiet" disabled={busy} onClick={() => void completeTask(task)}>完成</button>{task.taskId !== goal.nextTaskId && (!task.phaseId || phaseOf(goal, task.phaseId)?.status === "open") && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("next", { taskId: task.taskId }, "下一步已更新")}>设为下一步</button>}<PhaseAssignment goal={goal} task={task} busy={busy} onChange={(phaseId) => void action("link-task", { taskId: task.taskId, phaseId, expectedGoalId: goal.id }, "行动阶段已更新")} /><button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("unlink-task", { taskId: task.taskId }, "已解除关联")}>解除关联</button></div>}
      </li>)}</ul>}
      {completedTasks.length > 0 && <details className="goal-completed"><summary>已完成（{completedTasks.length}）</summary><ul className="goal-task-list">{completedTasks.map((task) => <li key={task.taskId}><div><span className="title">{task.title}</span><span className="goal-task-meta">已完成</span></div></li>)}</ul></details>}
    </section>

    <section className="goal-lifecycle"><h2>状态</h2><div className="goal-state-controls">
      {goal.state === "active" && <button type="button" className="button-secondary" disabled={busy} onClick={() => void action("state", { state: "paused", endReason: null }, "目标已暂停")}>暂停</button>}
      {goal.state === "paused" && <button type="button" className="button-secondary" disabled={busy} onClick={() => void action("state", { state: "active", endReason: null }, "目标已恢复")}>恢复</button>}
      {goal.state === "ended" && <button type="button" className="button-secondary" disabled={busy} onClick={() => void action("state", { state: "active", endReason: null }, "目标已恢复")}>重新打开</button>}
      {goal.state !== "ended" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("state", { state: "ended", endReason: "achieved" }, "目标已标记为达成")}>标记达成</button>}
      {goal.state !== "ended" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => void action("state", { state: "ended", endReason: "abandoned" }, "目标已结束")}>结束目标</button>}
    </div></section>
    {editor && <GoalEditorDialog item={editor.item} busy={busy} error={error} onClose={() => setEditor(null)} onRefresh={refreshGoalEditor} onSave={(input) => saveGoal(input, editor)} />}
    {phaseEditor && <PhaseEditorDialog item={phaseEditor.item} busy={busy} error={error} onClose={() => setPhaseEditor(null)} onRefresh={refreshPhaseEditor} onSave={savePhase} />}
    {addTask && <TaskEditorDialog phases={goal.phases} initialPhaseId={addTask.phaseId} busy={busy} error={error} onClose={() => setAddTask(null)} onRefresh={refreshTaskEditor} onSave={createTask} />}
    {taskPicker && <GoalTaskPicker goal={goal} mode={taskPicker} busy={busy} onClose={() => setTaskPicker(null)} onPick={async (task) => {
      const changed = taskPicker === "next" ? await action("next", { taskId: task.taskId }, "下一步已更新") : await action("link-task", { taskId: task.taskId, phaseId: focused?.id ?? null, expectedGoalId: task.goalId }, "行动已关联");
      if (changed) setTaskPicker(null);
    }} />}
  </main>;
}

function GoalEditorDialog({ item, busy, error, onClose, onRefresh, onSave }: { item?: Goal; busy: boolean; error?: string | null; onClose: () => void; onRefresh?: () => Promise<void>; onSave: (input: { title: string; notes: string; horizonText: string }) => void }) {
  const [title, setTitle] = useState(item?.title ?? ""); const [notes, setNotes] = useState(item?.notes ?? ""); const [horizonText, setHorizonText] = useState(item?.horizonText ?? "");
  const keyboard = useEntryKeyboard(onClose);
  return <Modal label={item ? "编辑目标" : "新建目标"} onClose={onClose}><div className="modal-heading"><span>{item ? "编辑目标" : "新建目标"}</span><button type="button" className="linkish quiet" onClick={onClose}>关闭</button></div><form className="goal-editor" onSubmit={(event: FormEvent) => { event.preventDefault(); if (!keyboard.shouldIgnoreSubmit() && title.trim()) onSave({ title: title.trim(), notes: notes.trim(), horizonText: horizonText.trim() }); }}>
    {error && <p className="error" role="alert">{error}</p>}<label>目标名称<input data-autofocus {...keyboard.bind} value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} placeholder="例如：通过 CCF CSP 认证" /></label>
    <label>大致时间<span className="settings-caption">可选，例如「明年」或「下半年」</span><input value={horizonText} maxLength={100} onChange={(event) => setHorizonText(event.target.value)} /></label>
    <label>备注<textarea rows={4} value={notes} maxLength={10000} onChange={(event) => setNotes(event.target.value)} placeholder="写下你想记住的方向或标准" /></label>
    <div className="modal-footer">{error && onRefresh ? <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button> : null}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" type="submit" onClick={keyboard.allowSubmit} disabled={busy || !title.trim()}>{busy ? "正在保存…" : "保存"}</button></div>
  </form></Modal>;
}

function PhaseEditorDialog({ item, busy, error, onClose, onRefresh, onSave }: { item?: GoalPhase; busy: boolean; error?: string | null; onClose: () => void; onRefresh?: () => Promise<void>; onSave: (input: { title: string; notes: string; status: GoalPhaseStatus }) => void }) {
  const [title, setTitle] = useState(item?.title ?? ""); const [notes, setNotes] = useState(item?.notes ?? ""); const [status, setStatus] = useState<GoalPhaseStatus>(item?.status ?? "open");
  const keyboard = useEntryKeyboard(onClose);
  return <Modal label={item ? "编辑阶段" : "添加阶段"} onClose={onClose}><div className="modal-heading"><span>{item ? "编辑阶段" : "添加阶段"}</span><button type="button" className="linkish quiet" onClick={onClose}>关闭</button></div><form className="goal-editor" onSubmit={(event) => { event.preventDefault(); if (!keyboard.shouldIgnoreSubmit() && title.trim()) onSave({ title: title.trim(), notes: notes.trim(), status }); }}>
    {error && <p className="error" role="alert">{error}</p>}<label>阶段名称<input data-autofocus {...keyboard.bind} value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} placeholder="例如：基础准备" /></label>
    <label>说明<textarea rows={3} value={notes} maxLength={10000} onChange={(event) => setNotes(event.target.value)} /></label>
    {item && <label>状态<select value={status} onChange={(event) => setStatus(event.target.value as GoalPhaseStatus)}><option value="open">进行中</option><option value="done">已完成</option><option value="skipped">已跳过</option></select></label>}
    <div className="modal-footer">{error && onRefresh ? <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button> : null}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" type="submit" onClick={keyboard.allowSubmit} disabled={busy || !title.trim()}>{busy ? "正在保存…" : "保存"}</button></div>
  </form></Modal>;
}

function PhaseAssignment({ goal, task, busy, onChange }: { goal: GoalResponse; task: GoalTask; busy: boolean; onChange: (phaseId: string | null) => void }) {
  const open = goal.phases.filter((phase) => phase.status === "open");
  if (open.length === 0) return null;
  const current = phaseOf(goal, task.phaseId);
  return <select className="goal-task-phase-select" value={task.phaseId ?? ""} aria-label={`调整「${task.title}」所属阶段`} disabled={busy} onChange={(event) => onChange(event.target.value || null)}>
    <option value="">未分阶段</option>
    {current && current.status !== "open" && <option value={current.id} disabled>{current.title}（已{phaseText(current.status).replace("已", "")}）</option>}
    {open.map((phase) => <option key={phase.id} value={phase.id}>{phase.title}</option>)}
  </select>;
}

function TaskEditorDialog({ phases, initialPhaseId, busy, error, onClose, onRefresh, onSave }: { phases: GoalPhase[]; initialPhaseId: string | null; busy: boolean; error?: string | null; onClose: () => void; onRefresh?: () => Promise<void>; onSave: (input: { title: string; notes: string; phaseId: string | null }) => void }) {
  const [title, setTitle] = useState(""); const [notes, setNotes] = useState(""); const [phaseId, setPhaseId] = useState(initialPhaseId ?? "");
  const openPhases = phases.filter((phase) => phase.status === "open");
  const keyboard = useEntryKeyboard(onClose);
  return <Modal label="添加行动" onClose={onClose}><div className="modal-heading"><span>添加行动</span><button type="button" className="linkish quiet" onClick={onClose}>关闭</button></div><form className="goal-editor" onSubmit={(event) => { event.preventDefault(); if (!keyboard.shouldIgnoreSubmit() && title.trim()) onSave({ title: title.trim(), notes: notes.trim(), phaseId: phaseId || null }); }}>
    {error && <p className="error" role="alert">{error}</p>}<label>行动<input data-autofocus {...keyboard.bind} value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} placeholder="例如：完成一套真题" /></label>
    <label>备注<textarea rows={3} value={notes} maxLength={10000} onChange={(event) => setNotes(event.target.value)} /></label>
    {openPhases.length > 0 && <label>所属阶段<select value={phaseId} onChange={(event) => setPhaseId(event.target.value)}><option value="">不指定阶段</option>{openPhases.map((phase) => <option key={phase.id} value={phase.id}>{phase.title}</option>)}</select></label>}
    <div className="modal-footer">{error && onRefresh ? <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button> : null}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" type="submit" onClick={keyboard.allowSubmit} disabled={busy || !title.trim()}>{busy ? "正在添加…" : "添加"}</button></div>
  </form></Modal>;
}

function GoalTaskPicker({ goal, mode, busy, onClose, onPick }: { goal: GoalResponse; mode: "link" | "next"; busy: boolean; onClose: () => void; onPick: (task: GoalTask) => void }) {
  const [items, setItems] = useState<GoalTask[] | null>(null); const [error, setError] = useState<string | null>(null); const [query, setQuery] = useState("");
  useEffect(() => { let cancelled = false; void listGoalCandidates().then((result) => { if (!cancelled) setItems(result.items); }).catch((err) => { if (!cancelled) setError(errorMessage(err)); }); return () => { cancelled = true; }; }, []);
  const candidates = useMemo(() => (items ?? []).filter((task) => {
    if (task.completed) return false;
    if (mode === "next") return task.goalId === goal.id && (!task.phaseId || phaseOf(goal, task.phaseId)?.status === "open");
    return task.goalId === null;
  }).filter((task) => `${task.title}\n${task.notes}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [items, mode, goal.id, query]);
  return <Modal label={mode === "next" ? "选择下一步" : "关联已有待办"} onClose={onClose}><div className="modal-heading"><span>{mode === "next" ? "选择下一步" : "关联已有待办"}</span><button type="button" className="linkish quiet" onClick={onClose}>关闭</button></div><div className="goal-picker"><input data-autofocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索事项" aria-label="搜索事项" />{error && <p className="error">{error}</p>}{items === null && !error && <p>加载中…</p>}<ul>{candidates.map((task) => <li key={task.taskId}><div><strong>{task.title}</strong><span>{taskLocation(task, goal.serverToday)}</span></div><button type="button" className="button-secondary" disabled={busy} onClick={() => onPick(task)}>{mode === "next" ? "设为下一步" : "关联"}</button></li>)}</ul>{items && candidates.length === 0 && <p className="goal-subtle-empty">没有可选事项。</p>}</div></Modal>;
}
