import { openItemEditor, NotesMark } from "./ItemEditor";
import { useItemFocus } from "./useItemFocus";
import { useEntryKeyboard } from "./useEntryKeyboard";
import { type ReorderRow } from "./ReorderList";
import { CompletionList } from "./CompletionList";
import { ItemRow, type ItemAction } from "./ItemActions";
import { useItemOptions } from "./ItemOptions";
import { WelcomeTip } from "./WelcomeTip";
import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  addErrandOnDay,
  addTodoOnDay,
  ApiError,
  completeErrand,
  completeTodo,
  deleteErrand,
  deleteTask,
  errorMessage,
  listInventory,
  openDay,
  reorderTodos,
  reorderErrands,
  scheduleTask,
  setErrandClocks,
  setTodoClocks,
  uncompleteErrand,
  uncompleteTodo,
  unscheduleTask,
  type DayPlan,
  type Errand,
  type InventoryItem,
  type PlanningStatus,
  type Todo,
} from "./api";
import { ClockSummary } from "./TaskDetails";
import { useQuickAdd } from "./useQuickAdd";
import { INVENTORY_INLINE_LIMIT } from "./constants";
import { addCivilDays, formatDayHeading, maxWritableDate } from "./dates";
import { handleNavClick, navigate } from "./route";

type DayViewProps = {
  date: string;
  serverToday?: string;
  onInventoryChange?: () => void;
  refreshToken?: number;
  planningStatus?: PlanningStatus;
  onStartPlanning?: () => void;
};

function isVoidedErrand(errand: Errand, writable: boolean): boolean {
  return errand.status === "expired" || (!writable && errand.status !== "completed");
}

export function DayView({
  date,
  serverToday,
  onInventoryChange,
  refreshToken,
  planningStatus,
  onStartPlanning,
}: DayViewProps) {
  const [plan, setPlan] = useState<DayPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [errandDraft, setErrandDraft] = useState("");
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const quickAddRef = useQuickAdd(Boolean(plan?.writable) && !loading);
  const addingRef = useRef(false);
  const addingErrandRef = useRef(false);
  const activeDateRef = useRef(date);
  activeDateRef.current = date;
  const planRef = useRef(plan);
  planRef.current = plan;
  useItemFocus(!loading && plan?.date === date, plan);
  const addKeyboard = useEntryKeyboard(() => { setDraft(""); quickAddRef.current?.blur(); });
  const errandKeyboard = useEntryKeyboard(() => setErrandDraft(""));

  useEffect(() => {
    let cancelled = false;
    const current = planRef.current;
    const silent = current !== null && current.date === date;
    if (!silent) {
      setLoading(true);
    }
    openDay(date)
      .then((next) => {
        if (!cancelled) {
          setPlan(next);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPlan(null);
          setError(errorMessage(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [date, serverToday, refreshToken]);

  useEffect(() => {
    if (!plan?.writable) {
      setInventory([]);
      setInventoryError(null);
      return;
    }
    let cancelled = false;
    listInventory()
      .then((data) => {
        if (!cancelled) {
          setInventory(data.items);
          setInventoryError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setInventoryError(errorMessage(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [date, plan?.writable, serverToday, refreshToken]);

  async function apply(
    work: () => Promise<DayPlan | void>,
  ): Promise<boolean> {
    try {
      const next = await work();
      if (next && next.date === activeDateRef.current) {
        setPlan(next);
      }
      setError(null);
      return true;
    } catch (err: unknown) {
      setError(errorMessage(err));
      if (err instanceof ApiError && (err.error === "DaySealed" || err.error === "Conflict")) {
        try {
          const sealed = await openDay(date);
          if (sealed.date === activeDateRef.current) setPlan(sealed);
        } catch {
          // keep DaySealed message from the write
        }
      }
      return false;
    }
  }

  async function onAdd(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (addKeyboard.shouldIgnoreSubmit()) return;
    if (!plan?.writable) {
      return;
    }
    const title = draft.trim();
    if (!title || addingRef.current) return;
    addingRef.current = true;
    try {
      await apply(async () => {
        const next = await addTodoOnDay(plan.date, title);
        setDraft((current) => current.trim() === title ? "" : current);
        onInventoryChange?.();
        return next;
      });
    } finally { addingRef.current = false; }
  }

  async function onToggle(todo: Todo): Promise<boolean> {
    if (!plan?.writable) {
      return false;
    }
    return apply(() =>
      todo.completedOnDay
        ? uncompleteTodo(plan.date, todo.taskId)
        : completeTodo(plan.date, todo.taskId),
    );
  }

  function onDelete(todo: Todo): void {
    if (!plan?.writable) {
      return;
    }
    void apply(async () => {
      await deleteTask(todo.taskId);
      setPlan((current) =>
        current
          ? {
              ...current,
              todos: current.todos.filter((item) => item.taskId !== todo.taskId),
            }
          : current,
      );
    });
  }

  async function refreshInventory(): Promise<void> {
    try {
      const data = await listInventory();
      setInventory(data.items);
      setInventoryError(null);
    } catch (err: unknown) {
      setInventoryError(errorMessage(err));
    }
  }

  function dropTodo(taskId: string): void {
    setPlan((current) =>
      current
        ? {
            ...current,
            todos: current.todos.filter((item) => item.taskId !== taskId),
          }
        : current,
    );
  }

  function onUnschedule(todo: Todo): void {
    if (!plan?.writable || todo.completedOnDay) {
      return;
    }
    void (async () => {
      const ok = await apply(async () => {
        await unscheduleTask(todo.taskId);
        dropTodo(todo.taskId);
      });
      if (!ok) {
        return;
      }
      onInventoryChange?.();
      await refreshInventory();
    })();
  }

  function onScheduleHere(item: InventoryItem): void {
    if (!plan?.writable) {
      return;
    }
    void (async () => {
      const ok = await apply(async () =>
        scheduleTask(item.taskId, plan.date),
      );
      if (!ok) {
        return;
      }
      setInventory((current) =>
        current.filter((row) => row.taskId !== item.taskId),
      );
      onInventoryChange?.();
      await refreshInventory();
    })();
  }

  async function onAddErrand(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (errandKeyboard.shouldIgnoreSubmit()) return;
    if (!plan?.writable) {
      return;
    }
    const title = errandDraft.trim();
    if (!title || addingErrandRef.current) return;
    addingErrandRef.current = true;
    try {
      await apply(async () => {
        const next = await addErrandOnDay(plan.date, title);
        setErrandDraft((current) => current.trim() === title ? "" : current);
        return next;
      });
    } finally { addingErrandRef.current = false; }
  }

  async function onToggleErrand(errand: Errand): Promise<boolean> {
    if (!plan?.writable || isVoidedErrand(errand, plan.writable)) {
      return false;
    }
    return apply(() =>
      errand.status === "completed"
        ? uncompleteErrand(errand.id)
        : completeErrand(errand.id),
    );
  }

  function onDeleteErrand(errand: Errand): void {
    if (!plan?.writable) {
      return;
    }
    void apply(() => deleteErrand(errand.id));
  }

  if (loading) {
    return (
      <main className="page">
        <p>加载中…</p>
      </main>
    );
  }

  if (!plan) {
    return (
      <main className="page">
        <p className="error">{error ?? "无法打开这一天"}</p>
      </main>
    );
  }

  const prev = addCivilDays(plan.date, -1);
  const next = addCivilDays(plan.date, 1);

  return (
    <main className={plan.writable ? "page" : "page readonly"}>
      <div className="day-nav">
        <a
          className="day-arrow"
          href={`/d/${prev}`}
          aria-label="上一天"
          onClick={(event) => handleNavClick(event, `/d/${prev}`)}
        >
          ←
        </a>
        <h1 className="day-heading">
          <span>{formatDayHeading(plan.date)}</span>
          {plan.isToday ? <span className="badge">今天</span> : null}
          {plan.isPast ? <span className="badge">只读</span> : null}
          {plan.isFuture ? <span className="badge">未来</span> : null}
        </h1>
        <a
          className="day-arrow"
          href={`/d/${next}`}
          aria-label="下一天"
          onClick={(event) => handleNavClick(event, `/d/${next}`)}
        >
          →
        </a>
      </div>
      {!plan.writable ? (
        <p className="sealed">这是过去的记录，仅供回看。</p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      {plan.isToday && <WelcomeTip />}
      {plan.isToday && planningStatus === "unplanned" && <div className="planning-shortcut"><button type="button" className="linkish quiet" onClick={onStartPlanning}>从待办中整理今天 →</button></div>}
      <div className="day-columns">
        <section className="column">
          <div className="list-heading">
            <h2>{plan.isToday ? "今日计划" : "当天计划"}</h2>
            {plan.writable && plan.manualTodoOrder && <button type="button" className="linkish quiet order-reset" title="恢复按时间排序" onClick={() => void apply(() => reorderTodos(plan.date, plan.todos.map((item) => item.taskId), false))}>按时间</button>}
            {plan.writable ? (
              <button
                type="button"
                className="linkish quiet"
                onClick={() => navigate("/recurrences?kind=plan")}
              >
                定期…
              </button>
            ) : null}
          </div>
          {plan.todos.length === 0 ? (
            <p className="column-empty">
              先写下今天想做的一件事，也可以从待办里挑选。
            </p>
          ) : (
            <CompletionList key={`todos-${plan.date}-${plan.writable}`} items={plan.todos} getId={(item) => item.taskId} getLabel={(item) => item.title}
              isCompleted={(item) => item.completedOnDay} writable={plan.writable} onToggle={onToggle}
              onReorder={(ids) => apply(async () => { await reorderTodos(plan.date, ids); return openDay(plan.date); })}>
              {(todo, reorder, toggle, busy, settling) => (
                <TodoRow key={todo.taskId} todo={todo} writable={plan.writable} date={plan.date} today={plan.serverToday}
                  onToggle={toggle} busy={busy} settling={settling} reorder={reorder} onDelete={onDelete} onUnschedule={onUnschedule}
                  onSchedule={(target) => void apply(async () => { await scheduleTask(todo.taskId, target); onInventoryChange?.(); return openDay(plan.date); })} />
              )}
            </CompletionList>
          )}
          {plan.writable ? (
            <form className="add-form" onSubmit={onAdd}>
              <input
                ref={quickAddRef}
                {...addKeyboard.bind}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                aria-label="添加计划"
                placeholder="今天想做什么？回车添加"
                maxLength={200}
              />
            </form>
          ) : null}
          {plan.writable ? (
            <InventoryAddBlock
              items={inventory}
              error={inventoryError}
              onSchedule={onScheduleHere}
            />
          ) : null}
        </section>
        <section className="column">
          <div className="list-heading">
            <h2>零碎事项</h2>
            {plan.writable && plan.manualErrandOrder && <button type="button" className="linkish quiet order-reset" title="恢复按时间排序" onClick={() => void apply(() => reorderErrands(plan.date, plan.errands.map((item) => item.id), false))}>按时间</button>}
            {plan.writable ? (
              <button
                type="button"
                className="linkish quiet"
                onClick={() => navigate("/recurrences?kind=errand")}
              >
                定期…
              </button>
            ) : null}
          </div>
          {plan.errands.length === 0 ? (
            <p className="column-empty">取快递、买杯咖啡……当天的小事记在这里。</p>
          ) : (
            <CompletionList key={`errands-${plan.date}-${plan.writable}`} items={plan.errands} getId={(item) => item.id} getLabel={(item) => item.title}
              isCompleted={(item) => item.status === "completed"} writable={plan.writable} onToggle={onToggleErrand}
              onReorder={(ids) => apply(async () => { await reorderErrands(plan.date, ids); return openDay(plan.date); })}>
              {(errand, reorder, toggle, busy, settling) => (
                <ErrandRow key={errand.id} errand={errand} writable={plan.writable} onToggle={toggle}
                  busy={busy} settling={settling} reorder={reorder} onDelete={onDeleteErrand} />
              )}
            </CompletionList>
          )}
          {plan.writable ? (
            <form className="add-form" onSubmit={onAddErrand}>
              <input
                {...errandKeyboard.bind}
                value={errandDraft}
                onChange={(event) => setErrandDraft(event.target.value)}
                aria-label="添加零碎事项"
                placeholder="记一件小事，回车添加"
                maxLength={200}
              />
            </form>
          ) : null}
        </section>
      </div>
    </main>
  );
}

type TodoRowProps = {
  todo: Todo; writable: boolean; date: string; today: string; busy: boolean; settling: boolean;
  onToggle: () => void; reorder: ReorderRow; onDelete: (todo: Todo) => void;
  onUnschedule: (todo: Todo) => void; onSchedule: (date: string) => void;
};

function TodoRow({ todo, writable, date, today, busy, settling, onToggle, reorder, onDelete, onUnschedule, onSchedule }: TodoRowProps) {
  const options = useItemOptions();
  const edit = () => openItemEditor({ id: todo.taskId, kind: "task", title: todo.title, notes: todo.notes, writable });
  const tomorrow = addCivilDays(today, 1);
  const actions: ItemAction[] = [{ label: writable ? "编辑详情…" : "查看详情…", run: edit }];
  if (writable) {
    actions.push({ label: todo.completedOnDay ? "恢复为未完成" : "标记已完成", run: onToggle, disabled: busy });
    if (!todo.completedOnDay) actions.push(
      { label: "安排到今天", separator: true, disabled: busy || date === today, run: () => onSchedule(today) },
      { label: "安排到明天", disabled: busy || date === tomorrow, run: () => onSchedule(tomorrow) },
      { label: "选择日期…", disabled: busy, run: () => options.show({ title: todo.title, kind: "date", date, min: today, max: maxWritableDate(today), save: (values) => scheduleTask(todo.taskId, values.date) }) },
      { label: "移回待办", disabled: busy, run: () => onUnschedule(todo) },
    );
    actions.push(
      { label: "设置时间…", separator: true, disabled: busy, run: () => options.show({ title: todo.title, kind: "time", start: todo.startClock, end: todo.endClock, save: (values) => setTodoClocks(date, todo.taskId, values.start || null, values.end || null) }) },
      { label: "删除", separator: true, danger: true, disabled: busy, run: () => onDelete(todo) },
    );
  }
  return <ItemRow id={todo.taskId} title={todo.title} actions={actions} {...reorder.attributes}
    className={`todo${todo.completedOnDay ? " done" : ""}${settling ? " completing" : ""}`}>
    {reorder.handle}
    <input type="checkbox" checked={todo.completedOnDay} disabled={!writable} aria-disabled={busy || undefined}
      onChange={() => { if (!busy) onToggle(); }} aria-label={todo.title} />
    <button type="button" className="title" onClick={edit}>{todo.title}<NotesMark notes={todo.notes} /></button>
    {todo.recurrence && <span className="badge recurrence-badge">{todo.recurrence.label === "固定周期" ? "定期" : `定期 · ${todo.recurrence.label}`}</span>}
    <ClockSummary start={todo.startClock} end={todo.endClock} />
    {options.dialog}
  </ItemRow>;
}

function InventoryAddBlock({
  items,
  error,
  onSchedule,
}: {
  items: InventoryItem[];
  error: string | null;
  onSchedule: (item: InventoryItem) => void;
}) {
  const shown = items.slice(0, INVENTORY_INLINE_LIMIT);
  return (
    <div className="inventory-add">
      <h3>从待办中挑选</h3>
      {error ? <p className="error">{error}</p> : null}
      {shown.length > 0 ? (
        <ul className="inventory-inline">
          {shown.map((item) => (
            <li key={item.taskId}>
              <span className="title">{item.title}</span>
              <button
                type="button"
                className="linkish quiet"
                onClick={() => onSchedule(item)}
              >
                加入
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <a
        className="open-inventory"
        href="/inventory"
        onClick={(event) => handleNavClick(event, "/inventory")}
      >
        查看全部待办 →
      </a>
    </div>
  );
}

type ErrandRowProps = {
  errand: Errand; writable: boolean; busy: boolean; settling: boolean;
  onToggle: () => void; reorder: ReorderRow; onDelete: (errand: Errand) => void;
};

function ErrandRow({ errand, writable, busy, settling, onToggle, reorder, onDelete }: ErrandRowProps) {
  const voided = isVoidedErrand(errand, writable);
  const editable = writable && !voided;
  const options = useItemOptions();
  const edit = () => openItemEditor({ id: errand.id, kind: "errand", title: errand.title, notes: errand.notes, writable: editable });
  const actions: ItemAction[] = [{ label: editable ? "编辑详情…" : "查看详情…", run: edit }];
  if (editable) actions.push(
    { label: errand.status === "completed" ? "恢复为未完成" : "标记已完成", run: onToggle, disabled: busy },
    { label: "设置时间…", separator: true, disabled: busy, run: () => options.show({ title: errand.title, kind: "time", start: errand.startClock, end: errand.endClock, save: (values) => setErrandClocks(errand.id, values.start || null, values.end || null) }) },
    { label: "删除", separator: true, danger: true, disabled: busy, run: () => onDelete(errand) },
  );
  return <ItemRow id={errand.id} title={errand.title} actions={actions} {...reorder.attributes}
    className={`todo${errand.status === "completed" ? " done" : voided ? " expired" : ""}${settling ? " completing" : ""}`}>
    {reorder.handle}
    {voided ? <span className="badge">已作废</span> : <input type="checkbox" checked={errand.status === "completed"}
      disabled={!writable} aria-disabled={busy || undefined} onChange={() => { if (!busy) onToggle(); }} aria-label={errand.title} />}
    <button type="button" className="title" onClick={edit}>{errand.title}<NotesMark notes={errand.notes} /></button>
    {errand.recurrence && <span className="badge recurrence-badge">{errand.recurrence.label === "固定周期" ? "定期" : `定期 · ${errand.recurrence.label}`}</span>}
    <ClockSummary start={errand.startClock} end={errand.endClock} />
    {options.dialog}
  </ItemRow>;
}
