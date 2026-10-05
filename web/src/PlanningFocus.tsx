import { useRef, useState } from "react";
import { changeGoal, errorMessage, type Goal, type GoalActionInput } from "./api";
import { Modal } from "./Modal";
import { focusedGoals, nextActionCandidates, nextGoalAction } from "./planningView";
import { handleNavClick } from "./route";
import { usePlanningFocus } from "./usePlanningFocus";

export function PlanningFocus({ goals, today, recoveryGeneration, onChanged, onMap }: {
  goals: Goal[]; today: string; recoveryGeneration: string | null;
  onChanged: () => Promise<unknown>; onMap: () => void;
}) {
  const { ids, choose } = usePlanningFocus();
  const [picker, setPicker] = useState(false);
  const [nextPickerId, setNextPickerId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const items = focusedGoals(goals, ids);
  const picking = goals.find((goal) => goal.id === nextPickerId);
  async function mutate(goal: Goal, input: { operation: GoalActionInput["operation"]; [key: string]: unknown }) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(null);
    try {
      await changeGoal(goal.id, { ...input, expectedRevision: goal.revision, recoveryGeneration });
      setNextPickerId(null);
      await onChanged();
    } catch (e) {
      setError(errorMessage(e));
      await onChanged().catch(() => undefined);
    } finally { locked.current = false; setBusy(false); }
  }
  return <section className="planning-focus" aria-label="当前重点">
    <header className="planning-focus-heading"><h2>当前重点</h2><button className="linkish" onClick={() => setPicker(true)}>选择重点</button></header>
    {error && <p className="error" role="alert">{error}</p>}
    {!items.length && <div className="planning-focus-empty">
      <p>{ids.length ? "重点目标已暂停、结束或移除。可以选择其他目标，或查看目标地图。" : "选几个最近想推进的目标，阶段成果和下一步会显示在这里。"}</p>
      <button className="linkish" onClick={onMap}>查看目标地图</button>
    </div>}
    <div className="planning-focus-grid">{items.map((goal) => {
      const stage = goal.phases.find((item) => item.id === goal.focusPhaseId);
      const next = nextGoalAction(goal);
      const href = `/goals/${encodeURIComponent(goal.id)}`;
      return <article className="planning-focus-card" key={goal.id} aria-label={goal.title}>
        <header><a href={href} onClick={(e) => handleNavClick(e, href)}>{goal.title}</a>{goal.horizonText && <small>{goal.horizonText}</small>}</header>
        <div className="planning-focus-stage"><span>当前阶段</span><strong>{stage?.title || "尚未设置阶段"}</strong>
          {stage?.outcome && <p>阶段成果：{stage.outcome}</p>}
        </div>
        <div className="planning-focus-next"><span>下一步</span>
          {next ? <><strong>{next.title}</strong><small>{next.scheduledDate === today ? "已在今天" : next.scheduledDate ? `已安排 · ${next.scheduledDate}` : next.taskId ? "待办" : "尚未加入待办"}</small>
            <div className="planning-focus-controls">
              {next.scheduledDate === today ? <a href="/" onClick={(e) => handleNavClick(e, "/")}>查看今天</a>
                : <button className="button-primary small" disabled={busy} onClick={() => void mutate(goal, next.taskId
                    ? { operation: "schedule-next", expectedTaskId: next.taskId, expectedScheduledDate: next.scheduledDate }
                    : { operation: "materialize-action", actionId: next.id, destination: "today", requestId: crypto.randomUUID() })}>
                    {next.scheduledDate ? "改到今天" : "加入今天"}
                  </button>}
              {!next.taskId && <button className="linkish" disabled={busy} onClick={() => void mutate(goal, {
                operation: "materialize-action", actionId: next.id, destination: "inventory", requestId: crypto.randomUUID(),
              })}>加入待办</button>}
              <button className="linkish" disabled={busy} onClick={() => setNextPickerId(goal.id)}>更换下一步</button>
            </div>
          </> : <><p>选择一件可以开始的行动。</p><button className="button-secondary small" disabled={busy} onClick={() => setNextPickerId(goal.id)}>选择下一步</button></>}
        </div>
      </article>;
    })}</div>
    {picker && <FocusPicker goals={goals} ids={ids} onClose={() => setPicker(false)} onSave={(next) => { choose(next); setPicker(false); }} />}
    {picking && <Modal label="选择下一步" className="goal-dialog" onClose={() => { if (!busy) setNextPickerId(null); }}>
      <header><h2>「{picking.title}」的下一步</h2><button className="linkish" disabled={busy} onClick={() => setNextPickerId(null)}>取消</button></header>
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="planning-next-picker">{nextActionCandidates(picking).map((action) => <li key={action.id}>
        <button className="button-secondary" disabled={busy || picking.state !== "active"} onClick={() => void mutate(picking, { operation: "next-action", actionId: action.id })}>
          <strong>{action.title}</strong><small>{picking.phases.find((item) => item.id === action.phaseId)?.title || "不分阶段"}{action.taskId ? " · 已关联任务" : ""}</small>
        </button>
      </li>)}</ul>
      {!nextActionCandidates(picking).length && <p>当前还没有可选行动。打开路线后，可以添加行动或用助手补充。</p>}
      <a href={`/goals/${encodeURIComponent(picking.id)}`} onClick={(e) => handleNavClick(e, `/goals/${encodeURIComponent(picking.id)}`)}>打开路线</a>
    </Modal>}
  </section>;
}

function FocusPicker({ goals, ids, onClose, onSave }: { goals: Goal[]; ids: string[]; onClose: () => void; onSave: (ids: string[]) => void }) {
  const [selected, setSelected] = useState(ids.filter((id) => goals.some((goal) => goal.id === id)));
  const options = goals.filter((goal) => goal.state === "active" || ids.includes(goal.id));
  return <Modal label="选择重点目标" className="goal-dialog" onClose={onClose}>
    <form onSubmit={(e) => { e.preventDefault(); onSave(selected); }}>
      <header><h2>选择重点目标</h2><button type="button" className="linkish" onClick={onClose}>取消</button></header>
      <p className="settings-caption">选择最近想推进的目标，之后可以随时更换。</p>
      <div className="planning-focus-options">{options.map((goal) => <label key={goal.id}>
        <input type="checkbox" checked={selected.includes(goal.id)} disabled={!selected.includes(goal.id) && (goal.state !== "active" || selected.length >= 100)}
          onChange={(e) => setSelected((current) => e.target.checked ? [...current, goal.id] : current.filter((id) => id !== goal.id))} />
        <span>{goal.title}{goal.state !== "active" && <small>{goal.state === "paused" ? "已暂停" : "已结束"}</small>}</span>
      </label>)}</div>
      {!options.length && <p>新建一个目标后，就可以将它设为重点。</p>}
      <footer><button className="button-primary" type="submit">保存选择</button></footer>
    </form>
  </Modal>;
}
