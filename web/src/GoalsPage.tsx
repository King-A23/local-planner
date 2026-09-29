import {
  useEffect,
  useMemo,
  useRef,
  type HTMLAttributes,
  useState,
  type FormEvent,
  type ReactElement,
} from "react";
import {
  changeGoal,
  createGoal,
  createPlanningDraft,
  errorMessage,
  getGoal,
  getPlanningDraft,
  listGoalCandidates,
  listGoals,
  listPlanningDrafts,
  updatePlanningDraft,
  type Goal,
  type GoalAction,
  type GoalList,
  type GoalPhase,
  type GoalPhaseStatus,
  type GoalTask,
  type PlanningDraft,
} from "./api";
import { ItemMenu, type ItemAction } from "./ItemActions";
import { Modal } from "./Modal";
import { ComposerKeyboard } from "./composerKeyboard";
import { openItemEditor } from "./ItemEditor";
import { goalPath, visibleGoalIds, nextGoalAction } from "./planningView";
import { handleNavClick, navigate } from "./route";

type GoalResponse = Goal & Pick<GoalList, "serverToday" | "recoveryGeneration">;
const uid = () => crypto.randomUUID();
const stageName = (s: GoalPhaseStatus) =>
  s === "done" ? "已完成" : s === "skipped" ? "已跳过" : "后续阶段";
const phase = (g: Goal, id: string | null) => g.phases.find((p) => p.id === id);

function usePlannerFormKeyboard(): HTMLAttributes<HTMLFormElement> {
  const keyboard = useRef(new ComposerKeyboard());
  return {
    onCompositionStart: () => keyboard.current.compositionStart(),
    onCompositionEnd: () => keyboard.current.compositionEnd(performance.now()),
    onKeyUp: (event) => keyboard.current.keyUp(event.key),
    onKeyDown: (event) => {
      const action = keyboard.current.keyDown(event.nativeEvent, "enter", performance.now());
      if (action === "ime") event.stopPropagation();
      if (action === "suppress") { event.preventDefault(); event.stopPropagation(); }
    },
  };
}

function usePlanningEntry(describe: () => Promise<void>) {
  const handler = useRef(describe);
  handler.current = describe;
  useEffect(() => {
    const open = () => { void handler.current(); };
    window.addEventListener("planner:planning-request", open);
    return () => window.removeEventListener("planner:planning-request", open);
  }, []);
}

function useStageReveal(selection: string | null | undefined) {
  const track = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = track.current;
    const node = container?.querySelector<HTMLElement>('[aria-pressed="true"]');
    if (!container || !node) return;
    const bounds = container.getBoundingClientRect();
    const stage = node.getBoundingClientRect();
    if (stage.left < bounds.left || stage.right > bounds.right)
      container.scrollLeft += stage.left - bounds.left - (bounds.width - stage.width) / 2;
  }, [selection]);
  return track;
}

function DraftBanner({
  draft,
  onDone,
  onRefresh,
  onContinue,
}: {
  draft: PlanningDraft;
  onDone: () => void;
  onRefresh: () => Promise<void>;
  onContinue: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (operation: "apply" | "discard" | "undo" | "revert") => {
    setBusy(true);
    try {
      await updatePlanningDraft(draft.id, {
        operation,
        expectedRevision: draft.revision,
        recoveryGeneration: draft.recoveryGeneration,
        requestId: uid(),
      });
      if (operation === "apply" || operation === "discard" || operation === "revert") {
        window.dispatchEvent(new Event("planner:planning-context-clear"));
        onDone();
      } else await onRefresh();
      window.dispatchEvent(new Event("planner:items-changed"));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  if (draft.status === "discarded") return null;
  const locked = busy || draft.runStatus === "running";
  return (
    <aside className="planning-draft-banner">
      <div>
        <span className="page-eyebrow">
          {draft.status === "applied" ? "已保存的规划" : "规划草案"}
        </span>
        <strong>
          {draft.status === "applied"
            ? (draft.canRevert ? "规划已保存，仍可撤销这一次保存" : "规划已保存")
            : draft.runStatus === "running"
              ? "正在整理你的想法"
              : "先看看这次规划的变化"}
        </strong>
        <p>
          {draft.status === "applied"
            ? (draft.changes?.some((change) => change.kind === "goal" && change.type === "removed")
              ? "移除的目标已收起，已有任务和完成记录保留。"
              : "行动仍留在路线图，准备好时再加入今天。")
            : draft.lastError || (draft.changes?.length ? `包含 ${draft.changes.length} 项待保存调整` : "描述你的方向，也可以继续调整。") }
        </p>
      </div>
      <div className="planning-draft-actions">
        {draft.status === "editing" && draft.runStatus !== "running" && (
          <button className="linkish" disabled={locked} onClick={onContinue}>
            继续调整
          </button>
        )}
        {draft.canUndo && (
          <button
            className="linkish"
            disabled={locked}
            onClick={() => void run("undo")}
          >
            撤销修改
          </button>
        )}
        {draft.canRevert && (
          <button
            className="linkish"
            disabled={locked}
            onClick={() => void run("revert")}
          >
            还原保存
          </button>
        )}
        {draft.status === "editing" && (
          <>
            <button
              className="button-secondary"
              disabled={locked}
              onClick={() => void run("discard")}
            >
              放弃
            </button>
            <button
              className="button-primary"
              disabled={locked}
              onClick={() => void run("apply")}
            >
              保存规划
            </button>
          </>
        )}
      </div>
      {draft.status === "editing" && draft.changes?.length ? (
        <details className="planning-draft-change-details"><summary>查看变更明细</summary><div className="planning-draft-changes">
          {draft.changes.map((c) => (
            <span
              className={`draft-change ${c.type}`}
              key={`${c.kind}-${c.id}`}
            >
              {c.type === "added"
                ? "新增"
                : c.type === "removed"
                  ? "移除"
                  : "调整"}{" "}
              · {c.title}
            </span>
          ))}
        </div></details>
      ) : null}
      {error && <p className="error">{error}</p>}
    </aside>
  );
}

function GoalMap({
  goals,
  selectedId,
  onSelect,
  changes,
}: {
  goals: Goal[];
  selectedId?: string | null;
  onSelect: (id: string) => void;
  changes?: PlanningDraft["changes"];
}) {
  const [expanded, setExpanded] = useState(new Set<string>());
  const [showInactive, setShowInactive] = useState(false);
  const [focused, setFocused] = useState<string | null>(null);
  const visible = visibleGoalIds(goals, showInactive);
  const collapsedCount = goals.length - visibleGoalIds(goals).size;
  const relatedIds = new Set(goalPath(goals, selectedId || focused || "").map((g) => g.id));
  const grouped = useMemo(() => {
    const m = new Map<string | null, Goal[]>();
    const ids = new Set(goals.map((g) => g.id));
    goals.forEach((g) => {
      const key =
        g.parentGoalId && ids.has(g.parentGoalId) ? g.parentGoalId : null;
      m.set(key, [...(m.get(key) ?? []), g]);
    });
    return m;
  }, [goals]);
  const changed = new Set(changes?.map((c) => c.goalId) ?? []);
  const node = (g: Goal, depth: number): ReactElement => {
    const children = (grouped.get(g.id) ?? []).filter((child) => visible.has(child.id));
    const focus = phase(g, g.focusPhaseId);
    const next = nextGoalAction(g);
    const related = relatedIds.has(g.id) || g.parentGoalId === (selectedId || focused);
    return (
      <div
        className={`goal-map-node depth-${depth}${related ? " related" : ""}${selectedId === g.id ? " selected" : ""}`}
        key={g.id}
      >
        <button className="goal-map-card" onFocus={() => setFocused(g.id)} onMouseEnter={() => setFocused(g.id)} onClick={() => onSelect(g.id)}>
          <span className="goal-map-dot" data-state={g.state} />
          <span>
            <b>
              {g.title}
              {changed.has(g.id) && <i>草案</i>}
            </b>
            <small>{g.horizonText || "时间未定"}</small>
            <em>
              {g.state === "paused" ? "已暂停 · " : g.state === "ended" ? "已结束 · " : ""}{focus?.title || "尚未设置阶段"}
              {next ? ` · ${next.title}` : ""}
            </em>
          </span>
          <span>›</span>
        </button>
        {children.length > 0 && (depth < 1 || expanded.has(g.id)) && (
          <div className="goal-map-children">
            {children.map((child) => node(child, depth + 1))}
          </div>
        )}
        {children.length > 0 && depth >= 1 && !expanded.has(g.id) && (
          <button
            className="goal-map-expand"
            onClick={() => setExpanded((now) => new Set(now).add(g.id))}
          >
            展开 {children.length} 个支持目标
          </button>
        )}
      </div>
    );
  };
  const roots = grouped.get(null) ?? [];
  return (
    <section className="goal-map">
      <div className="goal-map-legend">
        <span>● 目标支持关系</span>
        <span>点击目标查看路线</span>
      </div>
      <div className="goal-map-roots">{roots.filter((g) => visible.has(g.id)).map((g) => node(g, 0))}</div>
      {collapsedCount > 0 && <button className="linkish map-inactive-toggle" aria-expanded={showInactive} onClick={() => setShowInactive(!showInactive)}>{showInactive ? "收起暂停与已结束目标" : `暂停与已结束 · ${collapsedCount}`}</button>}
    </section>
  );
}

export function GoalsPage({
  onChange,
  onRecoveryGeneration,
  refreshToken,
}: {
  onChange?: () => void;
  onRecoveryGeneration?: (generation: string | null) => void;
  refreshToken?: number;
}) {
  const [data, setData] = useState<GoalList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<Goal | undefined | null>(null);
  const [draft, setDraft] = useState<PlanningDraft | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewPhaseId, setPreviewPhaseId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    const value = await listGoals();
    setData(value);
    onRecoveryGeneration?.(value.recoveryGeneration);
    return value;
  };
  useEffect(() => {
    void load().catch((e) => setError(errorMessage(e)));
  }, [refreshToken]);

  useEffect(() => {
    void listPlanningDrafts()
      .then((value) => {
        const editing = value.items.find((item) => item.status === "editing") ?? value.items.find((item) => item.status === "applied");
        setDraft(editing ?? null);
      })
      .catch(() => undefined);
    const refreshDraft = (event: Event) => {
      const id = (event as CustomEvent<{ draftId?: string }>).detail?.draftId;
      if (id)
        void getPlanningDraft(id)
          .then((item) => { if (!item.scopeGoalId) setDraft(item); })
          .catch(() => undefined);
    };
    window.addEventListener("planner:planning-draft-updated", refreshDraft);
    return () =>
      window.removeEventListener(
        "planner:planning-draft-updated",
        refreshDraft,
      );
  }, []);
  const describe = async () => {
    if (!data) return;
    setBusy(true);
    try {
      const existing = draft?.status === "editing" ? draft : (await listPlanningDrafts()).items.find((item) => item.status === "editing");
      const next = existing ? await getPlanningDraft(existing.id) : await createPlanningDraft({
        requestId: uid(),
        recoveryGeneration: data.recoveryGeneration,
      });
      setDraft(next);
      window.dispatchEvent(
        new CustomEvent("planner:planning-context", {
          detail: {
            draftId: next.id,
            goalId: null,
            selectedPhaseId: null,
            expectedDraftRevision: next.revision,
          },
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  usePlanningEntry(describe);
  const save = async (input: GoalInput) => {
    if (!data) return;
    setBusy(true);
    try {
      if (draft?.status === "editing") {
        const id = uid();
        const next = await updatePlanningDraft(draft.id, { operation: "update", expectedRevision: draft.revision,
          recoveryGeneration: draft.recoveryGeneration, requestId: uid(), document: { goals: [...draft.document.goals,
            { id, ...input, state: "active", endReason: null, nextTaskId: null, nextActionId: null, focusPhaseId: null, phases: [], actions: [] }] } });
        setDraft(next); setPreviewId(id); setEditor(null);
        window.dispatchEvent(new CustomEvent("planner:planning-draft-updated", { detail: { draftId: next.id, revision: next.revision } }));
        return;
      }
      const { parentGoalId, ...createInput } = input;
      let created = await createGoal({
        ...createInput,
        requestId: uid(),
        recoveryGeneration: data.recoveryGeneration,
      });
      if (parentGoalId)
        created = await changeGoal(created.id, {
          operation: "set-parent",
          parentGoalId,
          expectedRevision: created.revision,
          recoveryGeneration: created.recoveryGeneration,
        });
      setEditor(null);
      onChange?.();
      navigate(`/goals/${created.id}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const shown =
    draft?.status === "editing"
      ? (draft.document.goals as Goal[])
      : (data?.items ?? []);
  const preview =
    draft?.status === "editing"
      ? shown.find((item) => item.id === previewId)
      : null;
  return (
    <main className="page goals-page planning-page">
      <header className="planning-heading">
        <div>
          <span className="page-eyebrow">规划</span>
          <h1>让方向变成下一步</h1>
          <p>目标相互支持，行动只在你决定时进入今天。</p>
        </div>
        <div>
          <button
            className="button-secondary"
            disabled={busy}
            onClick={() => setEditor(undefined)}
          >
            新建目标
          </button>
          <button
            className="button-primary"
            disabled={busy}
            onClick={() => void describe()}
          >
            ✦ 描述规划
          </button>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {draft && (
        <DraftBanner
          draft={draft}
          onRefresh={async () => { setDraft(await getPlanningDraft(draft.id)); await load(); }}
          onContinue={() =>
            window.dispatchEvent(
              new CustomEvent("planner:planning-context", {
                detail: {
                  draftId: draft.id,
                  goalId: null,
                  selectedPhaseId: previewPhaseId,
                  expectedDraftRevision: draft.revision,
                },
              }),
            )
          }
          onDone={() => {
            setPreviewId(null);
            void getPlanningDraft(draft.id).then(setDraft);
            void load().then(() => onChange?.());
          }}
        />
      )}
      {!data && !error && <p>加载中…</p>}
      {data && shown.length === 0 && (
        <section className="planning-empty">
          <span>✦</span>
          <h2>从一个想去的方向开始</h2>
          <p>例如“明年通过 CCF CSP 认证”。</p>
          <button className="button-primary" onClick={() => void describe()}>
            描述我的规划
          </button>
        </section>
      )}
      {shown.length > 0 && !preview && (
        <GoalMap
          goals={shown}
          changes={draft?.status === "editing" ? draft.changes : undefined}
          selectedId={previewId}
          onSelect={(id) =>
            draft?.status === "editing"
              ? (setPreviewId(id), setPreviewPhaseId(shown.find((g) => g.id === id)?.focusPhaseId ?? null))
              : navigate(`/goals/${id}`)
          }
        />
      )}
      {preview && (
        <DraftGoalPreview
          key={preview.id}
          goal={preview}
          goals={shown}
          draft={draft!}
          onClose={() => { setPreviewId(null); setPreviewPhaseId(null); }}
          onSelect={setPreviewPhaseId}
          onChanged={setDraft}
        />
      )}
      {editor !== null && (
        <GoalEditor
          goal={editor}
          goals={data?.items ?? []}
          busy={busy}
          onClose={() => setEditor(null)}
          onSave={save}
        />
      )}
    </main>
  );
}

function DraftGoalPreview({ goal, draft, goals, onClose, onChanged, onSelect }: {
  goal: Goal; draft: PlanningDraft; goals: Goal[]; onClose: () => void;
  onChanged: (draft: PlanningDraft) => void;
  onSelect?: (id: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(draft.selectedPhaseId ?? goal.focusPhaseId);
  const [goalEditor, setGoalEditor] = useState(false);
  const [phaseEditor, setPhaseEditor] = useState<GoalPhase | null | undefined>(undefined);
  const [actionEditor, setActionEditor] = useState<{ action?: GoalAction; phaseId?: string | null } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = saving || draft.runStatus === "running";
  const stages = [...goal.phases].sort((a, b) => a.position - b.position);
  const selected = phase(goal, selectedId) ?? phase(goal, goal.focusPhaseId) ?? stages[0];
  const trackRef = useStageReveal(selected?.id);
  const shownActions = goal.actions.filter((a) => !a.discarded && (a.phaseId === (selected?.id ?? null) || a.phaseId === null));
  const save = async (updated: Goal) => {
    setSaving(true); setError(null);
    try {
      const next = await updatePlanningDraft(draft.id, {
        operation: "update", expectedRevision: draft.revision, recoveryGeneration: draft.recoveryGeneration,
        requestId: uid(), document: { goals: draft.document.goals.map((g) => g.id === goal.id ? updated : g) },
      });
      onChanged(next);
      window.dispatchEvent(new CustomEvent("planner:planning-draft-updated", { detail: { draftId: next.id, revision: next.revision } }));
      return true;
    } catch (e) { setError(errorMessage(e)); return false; }
    finally { setSaving(false); }
  };
  const selectPhase = (id: string) => {
    setSelectedId(id);
    onSelect?.(id);
    window.dispatchEvent(new CustomEvent("planner:planning-phase-selected", { detail: { draftId: draft.id, selectedPhaseId: id } }));
  };
  const stageChange = (patch: Partial<GoalPhase>) => selected && void save({ ...goal, phases: stages.map((p) => p.id === selected.id ? { ...p, ...patch } : p) });
  const stageMove = (offset: number) => {
    if (!selected) return;
    const list = [...stages]; const index = list.findIndex((p) => p.id === selected.id);
    if (index + offset < 0 || index + offset >= list.length) return;
    [list[index], list[index + offset]] = [list[index + offset], list[index]];
    void save({ ...goal, phases: list.map((p, position) => ({ ...p, position })) });
  };
  return <section className="draft-goal-preview roadmap-draft" aria-label="草案路线图">
    <header className="roadmap-heading">
      <div><span className="page-eyebrow">草案路线图</span><h2>{goal.title}</h2><p>{goal.horizonText || "时间未定"}</p>{goal.notes && <p>{goal.notes}</p>}</div>
      <div><button className="linkish" disabled={busy} onClick={() => setGoalEditor(true)}>编辑目标</button><button className="linkish" onClick={onClose}>返回目标地图</button></div>
    </header>
    {error && <p role="alert" className="error">{error}</p>}
    <section className="roadmap-track-section">
      <div className="section-caption"><span>阶段路线</span><button className="linkish" disabled={busy || goal.state === "ended"} onClick={() => setPhaseEditor(null)}>＋ 添加阶段</button></div>
      <div className="roadmap-track" ref={trackRef}>{stages.map((p, index) => <button key={p.id} className={`roadmap-stage ${p.status}${selected?.id === p.id ? " selected" : ""}`} onClick={() => selectPhase(p.id)} aria-pressed={selected?.id === p.id}>
        <i>{p.status === "done" ? "✓" : p.status === "skipped" ? "−" : index + 1}</i><b>{p.title}</b><small>{p.horizonText || (p.id === goal.focusPhaseId ? "当前阶段" : stageName(p.status))}</small>
      </button>)}</div>
      {!stages.length && <p className="roadmap-actions-empty">可以先记下行动，阶段稍后再补。</p>}
    </section>
    <section className="roadmap-focus">
      <div className="roadmap-focus-head"><div><span className="page-eyebrow">{selected ? selected.id === goal.focusPhaseId ? "当前阶段" : stageName(selected.status) : "下一步行动"}</span><h2>{selected?.title || "从一件小事开始"}</h2>{selected?.outcome && <p className="roadmap-outcome">完成后：{selected.outcome}</p>}{selected?.notes && <p className="roadmap-notes">{selected.notes}</p>}</div>
      <div><button className="button-secondary" disabled={busy || goal.state === "ended"} onClick={() => setActionEditor({ phaseId: selected?.id ?? null })}>添加行动</button>{selected && <ItemMenu title="草案阶段" actions={[
        { label: "编辑阶段", disabled: busy || selected.status === "done", run: () => setPhaseEditor(selected) },
        { label: "设为当前阶段", disabled: busy || selected.status !== "open", run: () => void save({ ...goal, focusPhaseId: selected.id }) },
        { label: "向前移动", disabled: busy || stages[0]?.id === selected.id, run: () => stageMove(-1) },
        { label: "向后移动", disabled: busy || stages.at(-1)?.id === selected.id, run: () => stageMove(1) },
        { label: selected.status === "skipped" ? "重新打开阶段" : "跳过阶段", disabled: busy || selected.status === "done", run: () => stageChange({ status: selected.status === "skipped" ? "open" : "skipped" }) },
      ]} />}</div></div>
      {!shownActions.length && <p className="roadmap-actions-empty">远期阶段可以先只保留成果。</p>}
      <ul className="roadmap-action-list">{shownActions.map((a) => <li key={a.id} className={nextGoalAction(goal)?.id === a.id ? "is-next" : ""}><div><i>{a.completed ? "✓" : "○"}</i><button disabled={!!a.taskId || busy} onClick={() => setActionEditor({ action: a })}>{a.title}</button>{a.notes && <p>{a.notes}</p>}<small>{a.completed ? "已完成" : a.taskId ? "已关联任务" : "规划行动"}{nextGoalAction(goal)?.id === a.id ? " · 下一步" : ""}</small></div><ItemMenu title="草案行动" actions={[
        { label: "编辑行动", disabled: busy || !!a.taskId, run: () => setActionEditor({ action: a }) },
        { label: a.id === goal.nextActionId ? "取消下一步" : "设为下一步", disabled: busy || !!a.taskId || !!goal.nextTaskId, run: () => void save({ ...goal, nextActionId: a.id === goal.nextActionId ? null : a.id }) },
        { label: "移除行动", disabled: busy || !!a.taskId, danger: true, run: () => void save({ ...goal, actions: goal.actions.filter((item) => item.id !== a.id) }) },
      ]} /></li>)}</ul>
    </section>
    {goalEditor && <GoalEditor goal={goal} goals={goals} busy={busy} onClose={() => setGoalEditor(false)} onSave={async (v) => { if (await save({ ...goal, ...v })) setGoalEditor(false); }} />}
    {phaseEditor !== undefined && <PhaseEditor phase={phaseEditor ?? undefined} busy={busy} onClose={() => setPhaseEditor(undefined)} onSave={async (v) => {
      const updated = phaseEditor ? { ...phaseEditor, ...v } : { id: uid(), goalId: goal.id, position: stages.length, ...v };
      if (await save({ ...goal, phases: phaseEditor ? stages.map((p) => p.id === updated.id ? updated : p) : [...stages, updated] })) { setPhaseEditor(undefined); selectPhase(updated.id); }
    }} />}
    {actionEditor && <ActionEditor action={actionEditor.action} phases={stages} phaseId={actionEditor.phaseId} busy={busy} onClose={() => setActionEditor(null)} onSave={async (v) => {
      const updated: GoalAction = actionEditor.action ? { ...actionEditor.action, ...v } : { ...v, id: uid(), goalId: goal.id, position: goal.actions.length, taskId: null, scheduledDate: null, completed: false, discarded: false };
      if (await save({ ...goal, actions: actionEditor.action ? goal.actions.map((a) => a.id === updated.id ? updated : a) : [...goal.actions, updated] })) setActionEditor(null);
    }} />}
  </section>;
}

export function GoalDetailPage({
  id,
  onChange,
  onRecoveryGeneration,
  refreshToken,
}: {
  id: string;
  onChange?: () => void;
  onRecoveryGeneration?: (generation: string | null) => void;
  refreshToken?: number;
}) {
  const [goal, setGoal] = useState<GoalResponse | null>(null);
  const [all, setAll] = useState<Goal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const trackRef = useStageReveal(selectedId ?? goal?.focusPhaseId ?? goal?.phases[0]?.id);
  const [goalEditor, setGoalEditor] = useState<Goal | undefined | null>(null);
  const [phaseEditor, setPhaseEditor] = useState<GoalPhase | null | undefined>(
    undefined,
  );
  const [actionEditor, setActionEditor] = useState<{
    action?: GoalAction;
    phaseId?: string | null;
  } | null>(null);
  const [link, setLink] = useState<GoalAction | null>(null);
  const [draft, setDraft] = useState<PlanningDraft | null>(null);
  const load = async () => {
    const [g, list] = await Promise.all([getGoal(id), listGoals()]);
    setGoal(g);
    setAll(list.items);
    onRecoveryGeneration?.(g.recoveryGeneration);
    return g;
  };
  useEffect(() => {
    void load().catch((e) => setError(errorMessage(e)));
  }, [id, refreshToken]);
  useEffect(() => {
    setDraft(null); setSelectedId(null); setError(null);
    setGoalEditor(null); setPhaseEditor(undefined); setActionEditor(null); setLink(null);
  }, [id]);

  useEffect(() => {
    void listPlanningDrafts(id)
      .then((value) => {
        const editing = value.items.find((item) => item.status === "editing") ?? value.items.find((item) => item.status === "applied");
        setDraft(editing ?? null);
      })
      .catch(() => undefined);
    const refreshDraft = (event: Event) => {
      const detail = (event as CustomEvent<{ draftId?: string }>).detail;
      if (detail?.draftId)
        void getPlanningDraft(detail.draftId)
          .then((item) => {
            if (item.scopeGoalId === id) setDraft(item);
          })
          .catch(() => undefined);
    };
    window.addEventListener("planner:planning-draft-updated", refreshDraft);
    return () =>
      window.removeEventListener(
        "planner:planning-draft-updated",
        refreshDraft,
      );
  }, [id]);
  const mutate = async (operation: string, body: Record<string, unknown>) => {
    if (!goal) return null;
    setBusy(true);
    setError(null);
    try {
      const g = await changeGoal(goal.id, {
        operation: operation as never,
        expectedRevision: goal.revision,
        recoveryGeneration: goal.recoveryGeneration,
        ...body,
      });
      setGoal(g);
      onChange?.();
      window.dispatchEvent(new Event("planner:items-changed"));
      return g;
    } catch (e) {
      setError(errorMessage(e));
      return null;
    } finally {
      setBusy(false);
    }
  };
  const describe = async () => {
    if (!goal) return;
    setBusy(true);
    try {
      const existing = draft?.status === "editing" ? draft : (await listPlanningDrafts(goal.id)).items.find((item) => item.status === "editing");
      const d = existing ? await getPlanningDraft(existing.id) : await createPlanningDraft({
        goalId: goal.id,
        selectedPhaseId: selectedId,
        requestId: uid(),
        recoveryGeneration: goal.recoveryGeneration,
      });
      setDraft(d);
      window.dispatchEvent(
        new CustomEvent("planner:planning-context", {
          detail: {
            draftId: d.id,
            goalId: goal.id,
            selectedPhaseId: selectedId,
            expectedDraftRevision: d.revision,
          },
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  usePlanningEntry(describe);
  if (!goal && !error)
    return (
      <main className="page">
        <p>加载中…</p>
      </main>
    );
  if (!goal)
    return (
      <main className="page">
        <p className="error">{error}</p>
      </main>
    );
  const visibleGoal =
    draft?.status === "editing"
      ? ((draft.document.goals.find((item) => item.id === goal.id) as
          Goal | undefined) ?? goal)
      : goal;
  const removedFromDraft = draft && !draft.document.goals.some((item) => item.id === goal.id);
  if (draft && (draft.status === "editing" || (draft.status === "applied" && removedFromDraft))) return <main className="page roadmap-page">
    <div className="goal-back"><a href="/goals" onClick={(e) => handleNavClick(e, "/goals")}>‹ 全部规划</a></div>
    <DraftBanner draft={draft} onRefresh={async () => { setDraft(await getPlanningDraft(draft.id)); await load(); }}
      onDone={() => { void getPlanningDraft(draft.id).then(setDraft); void load(); }}
      onContinue={() => window.dispatchEvent(new CustomEvent("planner:planning-context", { detail: { draftId: draft.id, goalId: goal.id, selectedPhaseId: selectedId, expectedDraftRevision: draft.revision } }))} />
    {!removedFromDraft
      ? <DraftGoalPreview key={visibleGoal.id} goal={visibleGoal} goals={all} draft={draft} onChanged={setDraft} onSelect={setSelectedId} onClose={() => navigate("/goals")} />
      : <section className="planning-empty">
          <h2>{draft.status === "applied" ? "已移除" : "将移除"}「{goal.title}」</h2>
          <p>{draft.status === "applied" ? "可以返回全部规划，开始新的规划。" : "保存后从进行中的规划收起。已有任务和完成记录会保留。"}</p>
        </section>}
  </main>;
  const stages = [...visibleGoal.phases].sort(
    (a, b) => a.position - b.position,
  );
  const selected =
    phase(visibleGoal, selectedId) ??
    phase(visibleGoal, visibleGoal.focusPhaseId) ??
    stages.find((p) => p.status === "open") ??
    stages[0];
  const actions = visibleGoal.actions
    .filter(
      (a) =>
        !a.discarded &&
        (a.phaseId === (selected?.id ?? null) || a.phaseId === null),
    )
    .sort((a, b) => a.position - b.position);
  const goalMenu: ItemAction[] = [
    { label: "编辑目标", disabled: busy, run: () => setGoalEditor(goal) },
    {
      label: goal.state === "active" ? "暂停目标" : "恢复目标",
      disabled: busy,
      separator: true,
      run: () =>
        void mutate("state", {
          state: goal.state === "active" ? "paused" : "active",
          endReason: null,
        }),
    },
    ...(goal.state !== "ended"
      ? [
          {
            label: "标记已达成",
            disabled: busy,
            run: () =>
              void mutate("state", { state: "ended", endReason: "achieved" }),
          },
        ]
      : []),
  ];
  return (
    <main className="page goal-detail-page roadmap-page">
      <div className="goal-back">
        <a href="/goals" onClick={(e) => handleNavClick(e, "/goals")}>
          ‹ 全部规划
        </a>
        {goalPath(all, goal.id).slice(0, -1).map((ancestor) => <span key={ancestor.id}> / <a href={`/goals/${ancestor.id}`} onClick={(e) => handleNavClick(e, `/goals/${ancestor.id}`)}>{ancestor.title}</a></span>)}
      </div>
      <header className="roadmap-heading">
        <div>
          <span className="page-eyebrow">路线图</span>
          <h1>{goal.title}</h1>
          <p className="roadmap-meta">
            <span data-state={goal.state}>
              {goal.state === "active"
                ? "进行中"
                : goal.state === "paused"
                  ? "已暂停"
                  : "已结束"}
            </span>
            {goal.horizonText && <span>{goal.horizonText}</span>}
            {goal.parentGoalId && (
              <a
                href={`/goals/${goal.parentGoalId}`}
                onClick={(e) =>
                  handleNavClick(e, `/goals/${goal.parentGoalId!}`)
                }
              >
                支持的目标 ↗
              </a>
            )}
          </p>
          {goal.notes && <p className="roadmap-notes">{goal.notes}</p>}
        </div>
        <div>
          <button
            className="button-secondary"
            disabled={busy}
            onClick={() => void describe()}
          >
            ✦ 调整规划
          </button>
          <ItemMenu title="目标" actions={goalMenu} />
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {draft && (
        <DraftBanner
          draft={draft}
          onRefresh={async () => { setDraft(await getPlanningDraft(draft.id)); await load(); }}
          onContinue={() =>
            window.dispatchEvent(
              new CustomEvent("planner:planning-context", {
                detail: {
                  draftId: draft.id,
                  goalId: id,
                  selectedPhaseId: selected?.id ?? draft.selectedPhaseId ?? null,
                  expectedDraftRevision: draft.revision,
                },
              }),
            )
          }
          onDone={() => {
            void getPlanningDraft(draft.id).then(setDraft);
            void load();
          }}
        />
      )}
      <section className="roadmap-track-section">
        <div className="section-caption">
          <span>阶段路线</span>
          <button
            className="linkish"
            disabled={busy}
            onClick={() => setPhaseEditor(null)}
          >
            ＋ 添加阶段
          </button>
        </div>
        {stages.length ? (
          <div className="roadmap-track" ref={trackRef}>
            {stages.map((p, i) => (
              <button
                className={`roadmap-stage ${p.status}${selected?.id === p.id ? " selected" : ""}`}
                onClick={() => {
                  setSelectedId(p.id);
                  window.dispatchEvent(
                    new CustomEvent("planner:planning-phase-selected", {
                      detail: { goalId: id, selectedPhaseId: p.id },
                    }),
                  );
                }}
                key={p.id}
                aria-pressed={selected?.id === p.id}
              >
                <i>
                  {p.status === "done"
                    ? "✓"
                    : p.status === "skipped"
                      ? "−"
                      : i + 1}
                </i>
                <b>{p.title}</b>
                <small>{p.horizonText || (p.id === visibleGoal.focusPhaseId ? "当前阶段" : stageName(p.status))}</small>
              </button>
            ))}
          </div>
        ) : (
          <div className="roadmap-empty">
            路线还没有阶段。
            <button
              className="button-secondary"
              onClick={() => setPhaseEditor(null)}
            >
              添加第一个阶段
            </button>
          </div>
        )}
      </section>
      {selected && (
        <section className="roadmap-focus">
          <div className="roadmap-focus-head">
            <div>
              <span className="page-eyebrow">
                {selected.id === goal.focusPhaseId
                  ? "当前阶段"
                  : stageName(selected.status)}
              </span>
              <h2>{selected.title}</h2>
              {selected.outcome && (
                <p className="roadmap-outcome">完成后：{selected.outcome}</p>
              )}
              {selected.notes && (
                <p className="roadmap-notes">{selected.notes}</p>
              )}
            </div>
            <div>
              <button
                className="button-secondary"
                disabled={busy || goal.state === "ended"}
                onClick={() => setActionEditor({ phaseId: selected.id })}
              >
                添加行动
              </button>
              <ItemMenu
                title="阶段"
                actions={[
                  {
                    label: "编辑阶段",
                    disabled: busy,
                    run: () => setPhaseEditor(selected),
                  },
                  {
                    label:
                      selected.id === goal.focusPhaseId
                        ? "取消当前阶段"
                        : "设为当前阶段",
                    disabled: busy,
                    run: () =>
                      void mutate("focus-phase", {
                        phaseId:
                          selected.id === goal.focusPhaseId
                            ? null
                            : selected.id,
                      }),
                  },
                  {
                    label:
                      selected.status === "done"
                        ? "重新打开阶段"
                        : "标记阶段完成",
                    disabled: busy,
                    separator: true,
                    run: () =>
                      void mutate("edit-phase", {
                        phaseId: selected.id,
                        title: selected.title,
                        notes: selected.notes,
                        outcome: selected.outcome,
                        horizonText: selected.horizonText,
                        status: selected.status === "done" ? "open" : "done",
                      }),
                  },
                  {
                    label:
                      selected.status === "skipped"
                        ? "重新打开阶段"
                        : "跳过阶段",
                    disabled: busy,
                    run: () =>
                      void mutate("edit-phase", {
                        phaseId: selected.id,
                        title: selected.title,
                        notes: selected.notes,
                        outcome: selected.outcome,
                        horizonText: selected.horizonText,
                        status: selected.status === "skipped" ? "open" : "skipped",
                      }),
                  },
                  {
                    label: "前移阶段",
                    disabled: busy || stages.indexOf(selected) === 0,
                    separator: true,
                    run: () => {
                      const ids = stages.map((item) => item.id);
                      const index = ids.indexOf(selected.id);
                      [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]];
                      void mutate("reorder-phases", { phaseIds: ids });
                    },
                  },
                  {
                    label: "后移阶段",
                    disabled: busy || stages.indexOf(selected) === stages.length - 1,
                    run: () => {
                      const ids = stages.map((item) => item.id);
                      const index = ids.indexOf(selected.id);
                      [ids[index], ids[index + 1]] = [ids[index + 1], ids[index]];
                      void mutate("reorder-phases", { phaseIds: ids });
                    },
                  },
                ]}
              />
            </div>
          </div>
          <ActionList
            actions={actions}
            canSchedule={goal.state === "active"}
            nextId={nextGoalAction(goal)?.id ?? null}
            today={goal.serverToday}
            busy={busy}
            onEdit={(a) => a.taskId ? openItemEditor({ id: a.taskId, kind: "task", title: a.title, notes: a.notes, writable: true }) : setActionEditor({ action: a })}
            onToday={(a) =>
              void mutate("materialize-action", {
                actionId: a.id,
                destination: "today",
                requestId: uid(),
              })
            }
            onInventory={(a) =>
              void mutate("materialize-action", {
                actionId: a.id,
                destination: "inventory",
                requestId: uid(),
              })
            }
            onLink={setLink}
            onNext={(a) =>
              void mutate("next-action", {
                actionId: nextGoalAction(goal)?.id === a.id ? null : a.id,
              })
            }
            onRemove={(a) => void mutate("remove-action", { actionId: a.id })}
          />
        </section>
      )}
      {!selected && (
        <section className="roadmap-focus">
          <div className="roadmap-focus-head">
            <div><span className="page-eyebrow">行动</span><h2>先从一件小事开始</h2></div>
            <button className="button-secondary" disabled={busy || goal.state === "ended"} onClick={() => setActionEditor({ phaseId: null })}>添加行动</button>
          </div>
          <ActionList actions={actions} canSchedule={goal.state === "active"} nextId={nextGoalAction(goal)?.id ?? null} today={goal.serverToday} busy={busy}
            onEdit={(item) => item.taskId ? openItemEditor({ id: item.taskId, kind: "task", title: item.title, notes: item.notes, writable: true }) : setActionEditor({ action: item })}
            onToday={(item) => void mutate("materialize-action", { actionId: item.id, destination: "today", requestId: uid() })}
            onInventory={(item) => void mutate("materialize-action", { actionId: item.id, destination: "inventory", requestId: uid() })}
            onLink={setLink}
            onNext={(item) => void mutate("next-action", { actionId: nextGoalAction(goal)?.id === item.id ? null : item.id })}
            onRemove={(item) => void mutate("remove-action", { actionId: item.id })}
          />
        </section>
      )}
      {goalEditor !== null && (
        <GoalEditor
          goal={goalEditor}
          goals={all}
          busy={busy}
          onClose={() => setGoalEditor(null)}
          onSave={async (v) => {
            const { parentGoalId, ...edit } = v;
            const saved = await mutate("edit", edit);
            if (saved) {
              try {
                const linked = parentGoalId === saved.parentGoalId ? saved : await changeGoal(saved.id, {
                  operation: "set-parent", parentGoalId, expectedRevision: saved.revision,
                  recoveryGeneration: saved.recoveryGeneration,
                });
                setGoal(linked); setGoalEditor(null);
                window.dispatchEvent(new Event("planner:items-changed"));
              } catch (e) { setError(errorMessage(e)); }
            }
          }}
        />
      )}
      {phaseEditor !== undefined && (
        <PhaseEditor
          phase={phaseEditor ?? undefined}
          busy={busy}
          onClose={() => setPhaseEditor(undefined)}
          onSave={async (v) => {
            if (
              await mutate(
                phaseEditor ? "edit-phase" : "add-phase",
                phaseEditor
                  ? { phaseId: phaseEditor.id, ...v }
                  : { title: v.title, notes: v.notes, outcome: v.outcome, horizonText: v.horizonText, requestId: uid() },
              )
            )
              setPhaseEditor(undefined);
          }}
        />
      )}
      {actionEditor && (
        <ActionEditor
          action={actionEditor.action}
          phases={stages}
          phaseId={actionEditor.phaseId}
          busy={busy}
          onClose={() => setActionEditor(null)}
          onSave={async (v) => {
            if (
              await mutate(
                actionEditor.action ? "edit-action" : "add-action",
                actionEditor.action
                  ? { actionId: actionEditor.action.id, ...v }
                  : { ...v, requestId: uid() },
              )
            )
              setActionEditor(null);
          }}
        />
      )}
      {link && (
        <LinkDialog
          action={link}
          busy={busy}
          onClose={() => setLink(null)}
          onPick={async (task) => {
            if (
              await mutate("link-action", {
                actionId: link.id,
                taskId: task.taskId,
                expectedTaskId: link.taskId,
              })
            )
              setLink(null);
          }}
        />
      )}
    </main>
  );
}

function ActionList({
  actions,
  nextId,
  today,
  busy,
  canSchedule = true,
  onEdit,
  onToday,
  onInventory,
  onLink,
  onNext,
  onRemove,
}: {
  actions: GoalAction[];
  nextId: string | null;
  today: string;
  busy: boolean;
  canSchedule?: boolean;
  onEdit: (a: GoalAction) => void;
  onToday: (a: GoalAction) => void;
  onInventory: (a: GoalAction) => void;
  onLink: (a: GoalAction) => void;
  onNext: (a: GoalAction) => void;
  onRemove: (a: GoalAction) => void;
}) {
  if (!actions.length)
    return (
      <p className="roadmap-actions-empty">
        这里还没有行动。远期阶段可以先只保留成果。
      </p>
    );
  return (
    <ul className="roadmap-action-list">
      {actions.map((a) => (
        <li
          className={`${a.completed ? "completed" : ""}${a.id === nextId ? " is-next" : ""}`}
          key={a.id}
        >
          <div>
            <i>{a.completed ? "✓" : "○"}</i>
            <button onClick={() => onEdit(a)}>{a.title}</button>
            {a.notes && <p>{a.notes}</p>}
            <small>
              {a.completed
                ? "已完成"
                : a.scheduledDate === today
                  ? "已在今天"
                  : a.scheduledDate || (a.taskId ? "待办" : "尚未加入待办")}
              {a.id === nextId && " · 下一步"}
            </small>
          </div>
          <div>
            {a.scheduledDate === today ? (
              <a href="/" onClick={(e) => handleNavClick(e, "/")}>
                查看今天
              </a>
            ) : (
              !a.completed && (
                <button
                  className="button-primary small"
                  disabled={busy || !canSchedule}
                  onClick={() => onToday(a)}
                >
                  加入今天
                </button>
              )
            )}
            <ItemMenu
              title="行动"
              actions={[
                { label: "编辑行动", disabled: busy, run: () => onEdit(a) },
                {
                  label: a.id === nextId ? "取消下一步" : "设为下一步",
                  disabled: busy || a.completed,
                  run: () => onNext(a),
                },
                {
                  label: "加入待办",
                  disabled: busy || a.completed || !!a.taskId,
                  separator: true,
                  run: () => onInventory(a),
                },
                {
                  label: "关联已有待办",
                  disabled: busy || a.completed || !!a.taskId,
                  run: () => onLink(a),
                },
                {
                  label: "移除行动",
                  disabled: busy || !!a.taskId,
                  danger: true,
                  run: () => onRemove(a),
                },
              ]}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

type GoalInput = {
  title: string;
  notes: string;
  horizonText: string;
  parentGoalId: string | null;
};
function GoalEditor({
  goal,
  goals,
  busy,
  onClose,
  onSave,
}: {
  goal?: Goal;
  goals: Goal[];
  busy: boolean;
  onClose: () => void;
  onSave: (v: GoalInput) => void;
}) {
  const formKeys = usePlannerFormKeyboard();
  const [title, setTitle] = useState(goal?.title ?? "");
  const [notes, setNotes] = useState(goal?.notes ?? "");
  const [horizonText, setHorizon] = useState(goal?.horizonText ?? "");
  const [parentGoalId, setParent] = useState(goal?.parentGoalId ?? "");
  return (
    <Modal label="目标" className="goal-dialog" onClose={onClose}>
      <div className="modal-heading">
        <span>{goal ? "编辑目标" : "新建目标"}</span>
        <button className="icon-button" onClick={onClose}>
          ×
        </button>
      </div>
      <form {...formKeys}
        className="goal-editor"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (title.trim())
            onSave({
              title: title.trim(),
              notes: notes.trim(),
              horizonText: horizonText.trim(),
              parentGoalId: parentGoalId || null,
            });
        }}
      >
        <label>
          目标名称
          <input
            data-autofocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          大致时间（可选）
          <input
            value={horizonText}
            onChange={(e) => setHorizon(e.target.value)}
            placeholder="例如：明年 / 本学期"
          />
        </label>
        <label>
          主要支持哪个目标（可选）
          <select
            value={parentGoalId}
            onChange={(e) => setParent(e.target.value)}
          >
            <option value="">独立目标</option>
            {goals
              .filter((g) => g.id !== goal?.id)
              .map((g) => (
                <option value={g.id} key={g.id}>
                  {g.title}
                </option>
              ))}
          </select>
        </label>
        <label>
          说明（可选）
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="modal-footer">
          <button className="linkish" type="button" onClick={onClose}>
            取消
          </button>
          <button className="button-primary" disabled={busy}>
            保存
          </button>
        </div>
      </form>
    </Modal>
  );
}
function PhaseEditor({
  phase,
  busy,
  onClose,
  onSave,
}: {
  phase?: GoalPhase;
  busy: boolean;
  onClose: () => void;
  onSave: (v: {
    title: string;
    notes: string;
    outcome: string;
    horizonText: string;
    status: GoalPhaseStatus;
  }) => void;
}) {
  const formKeys = usePlannerFormKeyboard();
  const [title, setTitle] = useState(phase?.title ?? "");
  const [notes, setNotes] = useState(phase?.notes ?? "");
  const [outcome, setOutcome] = useState(phase?.outcome ?? "");
  const [horizonText, setHorizon] = useState(phase?.horizonText ?? "");
  const [status, setStatus] = useState<GoalPhaseStatus>(
    phase?.status ?? "open",
  );
  return (
    <Modal label="阶段" className="goal-dialog" onClose={onClose}>
      <div className="modal-heading">
        <span>{phase ? "编辑阶段" : "添加阶段"}</span>
        <button className="icon-button" onClick={onClose}>
          ×
        </button>
      </div>
      <form {...formKeys}
        className="goal-editor"
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim())
            onSave({
              title: title.trim(),
              notes: notes.trim(),
              outcome: outcome.trim(),
              horizonText: horizonText.trim(),
              status,
            });
        }}
      >
        <label>
          阶段名称
          <input
            data-autofocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          完成后会怎样
          <input
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            placeholder="例如：完成一次模拟"
          />
        </label>
        <label>
          大致时间（可选）
          <input
            value={horizonText}
            onChange={(e) => setHorizon(e.target.value)}
          />
        </label>
        <label>
          说明（可选）
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        {phase && (
          <label>
            状态
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as GoalPhaseStatus)}
            >
              <option value="open">进行中</option>
              <option value="done">已完成</option>
              <option value="skipped">已跳过</option>
            </select>
          </label>
        )}
        <div className="modal-footer">
          <button type="button" className="linkish" onClick={onClose}>
            取消
          </button>
          <button className="button-primary" disabled={busy}>
            保存
          </button>
        </div>
      </form>
    </Modal>
  );
}
function ActionEditor({
  action,
  phases,
  phaseId,
  busy,
  onClose,
  onSave,
}: {
  action?: GoalAction;
  phases: GoalPhase[];
  phaseId?: string | null;
  busy: boolean;
  onClose: () => void;
  onSave: (v: { title: string; notes: string; phaseId: string | null }) => void;
}) {
  const formKeys = usePlannerFormKeyboard();
  const [title, setTitle] = useState(action?.title ?? "");
  const [notes, setNotes] = useState(action?.notes ?? "");
  const [stage, setStage] = useState(action?.phaseId ?? phaseId ?? "");
  return (
    <Modal label="行动" className="goal-dialog" onClose={onClose}>
      <div className="modal-heading">
        <span>{action ? "编辑行动" : "添加行动"}</span>
        <button className="icon-button" onClick={onClose}>
          ×
        </button>
      </div>
      <form {...formKeys}
        className="goal-editor"
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim())
            onSave({
              title: title.trim(),
              notes: notes.trim(),
              phaseId: stage || null,
            });
        }}
      >
        <label>
          行动
          <input
            data-autofocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          所属阶段
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">暂不归类</option>
            {phases.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          说明（可选）
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="modal-footer">
          <button className="linkish" type="button" onClick={onClose}>
            取消
          </button>
          <button className="button-primary" disabled={busy}>
            保存行动
          </button>
        </div>
      </form>
    </Modal>
  );
}
function LinkDialog({
  action,
  busy,
  onClose,
  onPick,
}: {
  action: GoalAction;
  busy: boolean;
  onClose: () => void;
  onPick: (task: GoalTask) => void;
}) {
  const [items, setItems] = useState<GoalTask[] | null>(null);
  const [query, setQuery] = useState("");
  useEffect(() => {
    void listGoalCandidates().then((x) => setItems(x.items));
  }, []);
  const shown = (items ?? []).filter(
    (x) =>
      !x.goalId &&
      `${x.title}\n${x.notes}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Modal label="关联已有待办" className="goal-dialog" onClose={onClose}>
      <div className="modal-heading">
        <span>关联已有待办</span>
        <button className="icon-button" onClick={onClose}>
          ×
        </button>
      </div>
      <div className="goal-picker">
        <p>{action.title}</p>
        <input
          data-autofocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索待办"
        />
        <ul>
          {shown.map((task) => (
            <li key={task.taskId}>
              <strong>{task.title}</strong>
              <button
                className="button-secondary"
                disabled={busy}
                onClick={() => onPick(task)}
              >
                关联
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  );
}
