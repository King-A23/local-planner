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
import { ItemMenu, ItemRow, type ItemAction } from "./ItemActions";
import { NotesMark, openItemEditor } from "./ItemEditor";
import { Modal } from "./Modal";
import { ReorderList } from "./ReorderList";
import { handleNavClick, navigate } from "./route";
import { useEntryKeyboard } from "./useEntryKeyboard";

type GoalResponse = Goal & Pick<GoalList, "serverToday" | "recoveryGeneration">;
type GoalEditor = { item?: Goal; revision?: number; recoveryGeneration?: string | null } | null;
type PhaseEditor = { item?: GoalPhase; revision: number; recoveryGeneration: string | null } | null;
type TaskEditor = { phaseId: string | null; revision: number; recoveryGeneration: string | null } | null;
type AssignmentEditor = { task: GoalTask; revision: number; recoveryGeneration: string | null } | null;
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
  const openCreate = () => data && setEditor({ recoveryGeneration: data.recoveryGeneration });
  return <main className="page goals-page">
    <header className="goals-heading">
      <h1>目标</h1>
      {Boolean(data?.items.length) && <button type="button" className="button-primary goal-add-button" disabled={busy} onClick={openCreate}><span aria-hidden="true">＋</span> 新建目标</button>}
    </header>
    {error && <p className="error" role="alert">{error}</p>}
    {!data && <p className="goal-subtle-empty" role="status">加载中…</p>}
    {data && !error && data.items.length === 0 && <section className="goals-empty">
      <span className="goal-empty-symbol"><GoalIcon /></span>
      <h2>给长远的想法，一个起点</h2>
      <p>记下想实现的目标，从一个小行动开始。</p>
      <button type="button" className="button-primary" disabled={busy} onClick={openCreate}>新建目标</button>
    </section>}
    {active.length > 0 && <GoalGroup title="进行中" goals={active} today={data?.serverToday ?? ""} />}
    {paused.length > 0 && <GoalGroup title="已暂停" goals={paused} today={data?.serverToday ?? ""} />}
    {ended.length > 0 && <GoalGroup title="已结束" goals={ended} today={data?.serverToday ?? ""} />}
    {editor && <GoalEditorDialog item={editor.item} busy={busy} error={error} onClose={() => setEditor(null)} onRefresh={refreshEditor} onSave={(input) => save(input, editor)} />}
  </main>;
}

function GoalIcon() {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 21V4m0 1c4-5 10 5 14 0v10c-4 5-10-5-14 0" /></svg>;
}

function GoalGroup({ title, goals, today }: { title: string; goals: Goal[]; today: string }) {
  return <section className="goal-group"><h2>{title}<span>{goals.length}</span></h2><ul className="goal-list">
    {goals.map((goal) => {
      const next = goal.tasks.find((task) => task.taskId === goal.nextTaskId);
      const focus = phaseOf(goal, goal.focusPhaseId);
      return <li key={goal.id} className={`goal-card state-${goal.state}`}>
        <a className="goal-card-link" href={`/goals/${goal.id}`} onClick={(event) => handleNavClick(event, `/goals/${goal.id}`)}>
          <span className="goal-card-symbol"><GoalIcon /></span>
          <div className="goal-card-copy">
            <div className="goal-card-title"><h3>{goal.title}</h3>{goal.horizonText && <span className="goal-card-horizon">{goal.horizonText}</span>}</div>
            {focus && <p className="goal-card-phase">{focus.title}</p>}
            <p className={`goal-card-next${next ? "" : " is-empty"}`}><span aria-hidden="true">↳</span>{next ? next.title : goal.state === "ended" ? stateText(goal.state, goal.endReason) : "选择一个下一步"}{next && <span className="goal-card-location">{taskLocation(next, today)}</span>}</p>
          </div>
          <span className="goal-card-arrow" aria-hidden="true">›</span>
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
  const [assignment, setAssignment] = useState<AssignmentEditor>(null);
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
    const restoreFocus = document.activeElement instanceof HTMLInputElement && document.activeElement.type === "checkbox";
    const index = activeTasks.findIndex((item) => item.taskId === task.taskId);
    const focusTaskId = (activeTasks[index + 1] ?? activeTasks[index - 1])?.taskId;
    setBusy(true); setError(null);
    try {
      if (task.scheduledDate) await completeTodo(task.scheduledDate, task.taskId);
      else await completeInventoryTask(task.taskId);
      await reload();
      setNotice("行动已完成"); onChange?.();
      if (restoreFocus) window.requestAnimationFrame(() => {
        const selector = focusTaskId ? `.goal-task-row[data-item-id="${CSS.escape(focusTaskId)}"] input[type="checkbox"]` : ".goal-actions-add .linkish";
        document.querySelector<HTMLElement>(selector)?.focus({ preventScroll: true });
      });
    } catch (err: unknown) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  if (!goal && !error) return <main className="page"><p>加载中…</p></main>;
  if (!goal) return <main className="page"><p className="error">{error}</p><a href="/goals" onClick={(event) => handleNavClick(event, "/goals")}>返回目标</a></main>;
  const writable = goal.state !== "ended";
  const longNotes = goal.notes.length > 180 || goal.notes.split("\n").length > 3;
  const openPhase = (item?: GoalPhase) => setPhaseEditor({ item, revision: goal.revision, recoveryGeneration: goal.recoveryGeneration });
  const openTask = () => setAddTask({ phaseId: focused?.id ?? null, revision: goal.revision, recoveryGeneration: goal.recoveryGeneration });
  const editTask = (task: GoalTask) => openItemEditor({ id: task.taskId, kind: "task", title: task.title, notes: task.notes, writable });
  const goalActions: ItemAction[] = [
    { label: "编辑目标", disabled: busy, run: () => setEditor({ item: goal, revision: goal.revision, recoveryGeneration: goal.recoveryGeneration }) },
    ...(writable ? [{ label: "添加阶段", disabled: busy, run: () => openPhase() }] : []),
    { label: goal.state === "active" ? "暂停目标" : goal.state === "paused" ? "恢复目标" : "重新打开目标", disabled: busy, separator: true,
      run: () => void action("state", { state: goal.state === "active" ? "paused" : "active", endReason: null }, goal.state === "active" ? "目标已暂停" : "目标已恢复") },
    ...(writable ? [
      { label: "标记达成", disabled: busy, run: () => void action("state", { state: "ended", endReason: "achieved" }, "目标已标记为达成") },
      { label: "结束目标", disabled: busy, run: () => void action("state", { state: "ended", endReason: "abandoned" }, "目标已结束") },
    ] : []),
  ];
  function phaseActions(phase: GoalPhase): ItemAction[] {
    if (!writable) return [];
    const updateStatus = (status: GoalPhaseStatus) => void action("edit-phase", { phaseId: phase.id, title: phase.title, notes: phase.notes, status }, "阶段已更新");
    return [
      { label: "编辑阶段", disabled: busy, run: () => openPhase(phase) },
      ...(phase.status === "open" ? [
        { label: goal!.focusPhaseId === phase.id ? "取消当前阶段" : "设为当前阶段", disabled: busy, run: () => void action("focus-phase", { phaseId: goal!.focusPhaseId === phase.id ? null : phase.id }, "当前阶段已更新") },
        { label: "完成阶段", disabled: busy, separator: true, run: () => updateStatus("done") },
        { label: "跳过阶段", disabled: busy, run: () => updateStatus("skipped") },
      ] : [{ label: "重新打开阶段", disabled: busy, run: () => updateStatus("open") }]),
    ];
  }
  function taskActions(task: GoalTask): ItemAction[] {
    return [
      { label: "查看所在列表", run: () => navigate(taskHref(task)) },
      ...(writable ? [
        ...((!task.phaseId || phaseOf(goal!, task.phaseId)?.status === "open") ? [{ label: task.taskId === goal!.nextTaskId ? "取消下一步" : "设为下一步", disabled: busy, run: () => void action("next", { taskId: task.taskId === goal!.nextTaskId ? null : task.taskId }, "下一步已更新") }] : []),
        ...(goal!.phases.length ? [{ label: "调整所属阶段", disabled: busy, run: () => setAssignment({ task, revision: goal!.revision, recoveryGeneration: goal!.recoveryGeneration }) }] : []),
        { label: "解除目标关联", disabled: busy, separator: true, run: () => void action("unlink-task", { taskId: task.taskId }, "已解除关联") },
      ] : []),
    ];
  }
  return <main className="page goal-detail-page">
    <div className="goal-back"><a href="/goals" onClick={(event) => handleNavClick(event, "/goals")}><span aria-hidden="true">‹</span> 所有目标</a></div>
    <header className="goal-header">
      <div className="goal-header-copy">
        <div className="goal-title-row"><h1>{goal.title}</h1></div>
        <div className="goal-header-meta"><span className={`goal-state state-${goal.state}`}>{stateText(goal.state, goal.endReason)}</span>{goal.horizonText && <span>{goal.horizonText}</span>}</div>
        {goal.notes && <div className={`goal-notes${longNotes ? " is-collapsible" : ""}${notesOpen ? " is-open" : ""}`}><p>{goal.notes}</p>{longNotes && <button type="button" className="linkish quiet" aria-expanded={notesOpen} onClick={() => setNotesOpen((open) => !open)}>{notesOpen ? "收起备注" : "展开备注"}</button>}</div>}
      </div>
      <ItemMenu title="目标" actions={goalActions} />
    </header>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <div className="undo-toast goal-toast" role="status"><span>{notice}</span></div>}

    <section className={`goal-next-section${next ? " has-next" : ""}`} aria-labelledby="goal-next-heading">
      <div className="goal-section-heading"><h2 id="goal-next-heading"><span className="goal-next-arrow" aria-hidden="true">↗</span>下一步</h2>
        {writable && next && <ItemMenu title="下一步" actions={[
          { label: "更换下一步", disabled: busy, run: () => setTaskPicker("next") },
          { label: "取消下一步", disabled: busy, run: () => void action("next", { taskId: null }, "已取消下一步") },
        ]} />}
      </div>
      {next ? <div className="goal-next-content"><div className="goal-next-copy"><button type="button" className="goal-next-title" onClick={() => editTask(next)}>{next.title}</button><span className="goal-task-meta">{taskLocation(next, goal.serverToday)}{next.phaseId && phaseOf(goal, next.phaseId) ? ` · ${phaseOf(goal, next.phaseId)!.title}` : ""}</span></div>
        {next.scheduledDate === goal.serverToday ? <a className="goal-today-link" href={taskHref(next)} onClick={(event) => handleNavClick(event, taskHref(next))}>查看今天 <span aria-hidden="true">→</span></a> : goal.state === "active" && <button type="button" className="button-primary" disabled={busy} onClick={() => void action("schedule-next", { expectedTaskId: next.taskId, expectedScheduledDate: next.scheduledDate }, "下一步已加入今天")}>{next.scheduledDate ? "改排到今天" : "加入今天"}</button>}
      </div> : <div className="goal-next-content"><p className="goal-next-empty">{goal.state === "ended" ? "这个目标已告一段落。" : "从一件小事开始。"}</p>{writable && <button type="button" className="button-secondary" disabled={busy} onClick={() => activeTasks.some((task) => !task.phaseId || phaseOf(goal, task.phaseId)?.status === "open") ? setTaskPicker("next") : openTask()}>{activeTasks.some((task) => !task.phaseId || phaseOf(goal, task.phaseId)?.status === "open") ? "选择下一步" : "添加行动"}</button>}</div>}
    </section>

    <div className={`goal-workspace${goal.phases.length ? " has-phases" : ""}`}>
      {goal.phases.length > 0 && <section className="goal-route-section goal-panel" aria-labelledby="goal-route-heading">
        <div className="goal-section-heading"><h2 id="goal-route-heading">阶段</h2>{writable && <button type="button" className="goal-icon-add" aria-label="添加阶段" title="添加阶段" disabled={busy} onClick={() => openPhase()}>＋</button>}</div>
        <ReorderList items={goal.phases} getId={(phase) => phase.id} getLabel={(phase) => phase.title} writable={writable && !busy}
          onReorder={async (phaseIds) => Boolean(await action("reorder-phases", { phaseIds }, "阶段顺序已更新"))}>
          {(phase, row) => <ItemRow key={phase.id} {...row.attributes} id={phase.id} title={phase.title} actions={phaseActions(phase)} className={`goal-phase-row${goal.focusPhaseId === phase.id ? " is-current" : ""}`}>
            {row.handle}<span className={`goal-phase-marker phase-${phase.status}`} aria-hidden="true">{phase.status === "done" ? "✓" : phase.status === "skipped" ? "−" : goal.phases.indexOf(phase) + 1}</span>
            <div className="goal-phase-main"><button type="button" className="goal-phase-title" disabled={busy || !writable} onClick={() => openPhase(phase)}>{phase.title}</button>
              {phase.notes && <span className="goal-phase-notes" title={phase.notes}>{phase.notes}</span>}
              {goal.focusPhaseId === phase.id ? <span className="goal-phase-caption current">当前阶段</span> : phase.status !== "open" && <span className="goal-phase-caption">{phaseText(phase.status)}</span>}
            </div>
          </ItemRow>}
        </ReorderList>
      </section>}

      <section className="goal-actions-section goal-panel" aria-labelledby="goal-actions-heading">
        <div className="goal-section-heading"><h2 id="goal-actions-heading">行动<span className="goal-section-count">{activeTasks.length}</span></h2>
          {writable && <div className="goal-actions-add"><button type="button" className="linkish" disabled={busy} onClick={openTask}><span aria-hidden="true">＋</span> 添加行动</button><ItemMenu title="行动" actions={[
            { label: "关联已有待办", disabled: busy, run: () => setTaskPicker("link") },
            ...(!goal.phases.length ? [{ label: "添加阶段", disabled: busy, run: () => openPhase() }] : []),
          ]} /></div>}
        </div>
        {activeTasks.length === 0 ? <p className="goal-subtle-empty">{completedTasks.length > 0 ? "当前行动已完成。" : "还没有行动，添加一件想做的事。"}</p> : <ul className="goal-task-list">{activeTasks.map((task) => <ItemRow key={task.taskId} id={task.taskId} title={task.title} actions={taskActions(task)} className="goal-task-row">
          <input type="checkbox" aria-label={`完成：${task.title}`} checked={false} disabled={busy || !writable} onChange={() => void completeTask(task)} />
          <div className="goal-task-copy"><button type="button" className="goal-task-title" onClick={() => editTask(task)}>{task.title}<NotesMark notes={task.notes} /></button><span className="goal-task-meta">{taskLocation(task, goal.serverToday)}{task.phaseId && phaseOf(goal, task.phaseId) ? ` · ${phaseOf(goal, task.phaseId)!.title}` : ""}{task.taskId === goal.nextTaskId && <span className="goal-task-next">下一步</span>}</span></div>
        </ItemRow>)}</ul>}
        {completedTasks.length > 0 && <details className="goal-completed"><summary>已完成 <span>{completedTasks.length}</span></summary><ul className="goal-task-list">{completedTasks.map((task) => <li key={task.taskId} className="goal-task-row"><span className="goal-completed-check" aria-hidden="true">✓</span><span className="title">{task.title}</span></li>)}</ul></details>}
      </section>
    </div>
    {editor && <GoalEditorDialog item={editor.item} busy={busy} error={error} onClose={() => setEditor(null)} onRefresh={refreshGoalEditor} onSave={(input) => saveGoal(input, editor)} />}
    {phaseEditor && <PhaseEditorDialog item={phaseEditor.item} busy={busy} error={error} onClose={() => setPhaseEditor(null)} onRefresh={refreshPhaseEditor} onSave={savePhase} />}
    {addTask && <TaskEditorDialog phases={goal.phases} initialPhaseId={addTask.phaseId} busy={busy} error={error} onClose={() => setAddTask(null)} onRefresh={refreshTaskEditor} onSave={createTask} />}
    {assignment && <PhaseAssignmentDialog goal={goal} task={assignment.task} busy={busy} error={error} onClose={() => setAssignment(null)} onRefresh={async () => {
      try {
        const fresh = await reload();
        const task = fresh.tasks.find((item) => item.taskId === assignment.task.taskId);
        if (!task || fresh.state === "ended") {
          setAssignment(null); setNotice(!task ? "行动已不再关联此目标" : "目标已结束");
        } else setAssignment({ task, revision: fresh.revision, recoveryGeneration: fresh.recoveryGeneration });
      } catch (err) { setError(errorMessage(err)); }
    }} onSave={async (phaseId) => {
      const changed = await mutate((current) => changeGoal(current.id, { operation: "link-task", taskId: assignment.task.taskId, phaseId, expectedGoalId: current.id, expectedRevision: assignment.revision, recoveryGeneration: assignment.recoveryGeneration }), "行动阶段已更新");
      if (changed) setAssignment(null);
    }} />}
    {taskPicker && <GoalTaskPicker goal={goal} mode={taskPicker} busy={busy} operationError={error} onClose={() => setTaskPicker(null)} onPick={async (task) => {
      const changed = taskPicker === "next" ? await action("next", { taskId: task.taskId }, "下一步已更新") : await action("link-task", { taskId: task.taskId, phaseId: focused?.id ?? null, expectedGoalId: task.goalId }, "行动已关联");
      if (changed) setTaskPicker(null);
    }} />}
  </main>;
}

function GoalEditorDialog({ item, busy, error, onClose, onRefresh, onSave }: { item?: Goal; busy: boolean; error?: string | null; onClose: () => void; onRefresh?: () => Promise<void>; onSave: (input: { title: string; notes: string; horizonText: string }) => void }) {
  const [title, setTitle] = useState(item?.title ?? ""); const [notes, setNotes] = useState(item?.notes ?? ""); const [horizonText, setHorizonText] = useState(item?.horizonText ?? "");
  const keyboard = useEntryKeyboard(onClose);
  return <Modal className="goal-dialog" label={item ? "编辑目标" : "新建目标"} onClose={onClose}><div className="modal-heading"><span>{item ? "编辑目标" : "新建目标"}</span><button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button></div><form className="goal-editor" onSubmit={(event: FormEvent) => { event.preventDefault(); if (!keyboard.shouldIgnoreSubmit() && title.trim()) onSave({ title: title.trim(), notes: notes.trim(), horizonText: horizonText.trim() }); }}>
    {error && <p className="error" role="alert">{error}</p>}<label>目标名称<input data-autofocus {...keyboard.bind} value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} placeholder="例如：通过 CCF CSP 认证" /></label>
    <label>大致时间（可选）<input placeholder="例如：明年、下半年" {...keyboard.bind} value={horizonText} maxLength={100} onChange={(event) => setHorizonText(event.target.value)} /></label>
    <label>备注（可选）<textarea rows={4} value={notes} maxLength={10000} onChange={(event) => setNotes(event.target.value)} placeholder="写下你想记住的方向或标准" /></label>
    <div className="modal-footer">{error && onRefresh ? <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button> : null}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" type="submit" onClick={keyboard.allowSubmit} disabled={busy || !title.trim()}>{busy ? "正在保存…" : "保存"}</button></div>
  </form></Modal>;
}

function PhaseEditorDialog({ item, busy, error, onClose, onRefresh, onSave }: { item?: GoalPhase; busy: boolean; error?: string | null; onClose: () => void; onRefresh?: () => Promise<void>; onSave: (input: { title: string; notes: string; status: GoalPhaseStatus }) => void }) {
  const [title, setTitle] = useState(item?.title ?? ""); const [notes, setNotes] = useState(item?.notes ?? ""); const [status, setStatus] = useState<GoalPhaseStatus>(item?.status ?? "open");
  const keyboard = useEntryKeyboard(onClose);
  return <Modal className="goal-dialog" label={item ? "编辑阶段" : "添加阶段"} onClose={onClose}><div className="modal-heading"><span>{item ? "编辑阶段" : "添加阶段"}</span><button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button></div><form className="goal-editor" onSubmit={(event) => { event.preventDefault(); if (!keyboard.shouldIgnoreSubmit() && title.trim()) onSave({ title: title.trim(), notes: notes.trim(), status }); }}>
    {error && <p className="error" role="alert">{error}</p>}<label>阶段名称<input data-autofocus {...keyboard.bind} value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} placeholder="例如：基础准备" /></label>
    <label>说明（可选）<textarea rows={3} value={notes} maxLength={10000} onChange={(event) => setNotes(event.target.value)} /></label>
    {item && <label>状态<select value={status} onChange={(event) => setStatus(event.target.value as GoalPhaseStatus)}><option value="open">进行中</option><option value="done">已完成</option><option value="skipped">已跳过</option></select></label>}
    <div className="modal-footer">{error && onRefresh ? <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button> : null}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" type="submit" onClick={keyboard.allowSubmit} disabled={busy || !title.trim()}>{busy ? "正在保存…" : "保存"}</button></div>
  </form></Modal>;
}

function PhaseAssignmentDialog({ goal, task, busy, error, onClose, onRefresh, onSave }: { goal: GoalResponse; task: GoalTask; busy: boolean; error: string | null; onClose: () => void; onRefresh: () => Promise<void>; onSave: (phaseId: string | null) => void }) {
  const [phaseId, setPhaseId] = useState(task.phaseId ?? "");
  const current = phaseOf(goal, phaseId);
  return <Modal className="goal-dialog" label="调整所属阶段" onClose={onClose}>
    <div className="modal-heading"><span>调整所属阶段</span><button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button></div>
    <form className="goal-editor" onSubmit={(event) => { event.preventDefault(); onSave(phaseId || null); }}>
      <p className="goal-assignment-title">{task.title}</p>
      {error && <p className="error" role="alert">{error}</p>}
      <label>所属阶段<select data-autofocus value={phaseId} disabled={busy} onChange={(event) => setPhaseId(event.target.value)}>
        <option value="">不指定阶段</option>
        {current && current.status !== "open" && <option value={current.id} disabled>{current.title}（{phaseText(current.status)}）</option>}
        {goal.phases.filter((phase) => phase.status === "open").map((phase) => <option key={phase.id} value={phase.id}>{phase.title}</option>)}
      </select></label>
      <div className="modal-footer">{error && <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button>}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" disabled={busy || phaseId === (task.phaseId ?? "") || Boolean(current && current.status !== "open")}>保存</button></div>
    </form>
  </Modal>;
}

function TaskEditorDialog({ phases, initialPhaseId, busy, error, onClose, onRefresh, onSave }: { phases: GoalPhase[]; initialPhaseId: string | null; busy: boolean; error?: string | null; onClose: () => void; onRefresh?: () => Promise<void>; onSave: (input: { title: string; notes: string; phaseId: string | null }) => void }) {
  const [title, setTitle] = useState(""); const [notes, setNotes] = useState(""); const [phaseId, setPhaseId] = useState(initialPhaseId ?? "");
  const openPhases = phases.filter((phase) => phase.status === "open");
  const keyboard = useEntryKeyboard(onClose);
  return <Modal className="goal-dialog" label="添加行动" onClose={onClose}><div className="modal-heading"><span>添加行动</span><button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button></div><form className="goal-editor" onSubmit={(event) => { event.preventDefault(); if (!keyboard.shouldIgnoreSubmit() && title.trim()) onSave({ title: title.trim(), notes: notes.trim(), phaseId: phaseId || null }); }}>
    {error && <p className="error" role="alert">{error}</p>}<label>行动<input data-autofocus {...keyboard.bind} value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} placeholder="例如：完成一套真题" /></label>
    <label>备注（可选）<textarea rows={3} value={notes} maxLength={10000} onChange={(event) => setNotes(event.target.value)} /></label>
    {openPhases.length > 0 && <label>所属阶段<select value={phaseId} onChange={(event) => setPhaseId(event.target.value)}><option value="">不指定阶段</option>{openPhases.map((phase) => <option key={phase.id} value={phase.id}>{phase.title}</option>)}</select></label>}
    <div className="modal-footer">{error && onRefresh ? <button type="button" className="linkish" disabled={busy} onClick={() => void onRefresh()}>刷新并保留草稿</button> : null}<button type="button" className="linkish" disabled={busy} onClick={onClose}>取消</button><button className="button-primary" type="submit" onClick={keyboard.allowSubmit} disabled={busy || !title.trim()}>{busy ? "正在添加…" : "添加"}</button></div>
  </form></Modal>;
}

function GoalTaskPicker({ goal, mode, busy, operationError, onClose, onPick }: { goal: GoalResponse; mode: "link" | "next"; busy: boolean; operationError: string | null; onClose: () => void; onPick: (task: GoalTask) => void }) {
  const [items, setItems] = useState<GoalTask[] | null>(null); const [error, setError] = useState<string | null>(null); const [query, setQuery] = useState("");
  useEffect(() => { let cancelled = false; void listGoalCandidates().then((result) => { if (!cancelled) setItems(result.items); }).catch((err) => { if (!cancelled) setError(errorMessage(err)); }); return () => { cancelled = true; }; }, []);
  const candidates = useMemo(() => (items ?? []).filter((task) => {
    if (task.completed) return false;
    if (mode === "next") return task.goalId === goal.id && (!task.phaseId || phaseOf(goal, task.phaseId)?.status === "open");
    return task.goalId === null;
  }).filter((task) => `${task.title}\n${task.notes}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [items, mode, goal.id, goal.phases, query]);
  return <Modal className="goal-dialog" label={mode === "next" ? "选择下一步" : "关联已有待办"} onClose={onClose}><div className="modal-heading"><span>{mode === "next" ? "选择下一步" : "关联已有待办"}</span><button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button></div><div className="goal-picker"><input data-autofocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索事项" aria-label="搜索事项" />{(error || operationError) && <p className="error" role="alert">{error || operationError}</p>}{items === null && !error && <p>加载中…</p>}<ul>{candidates.map((task) => <li key={task.taskId}><div><strong>{task.title}</strong><span>{taskLocation(task, goal.serverToday)}</span></div><button type="button" className="button-secondary" disabled={busy} onClick={() => onPick(task)}>{mode === "next" ? "设为下一步" : "关联"}</button></li>)}</ul>{items && candidates.length === 0 && <p className="goal-subtle-empty">没有可选事项。</p>}</div></Modal>;
}
