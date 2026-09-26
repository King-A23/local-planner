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
  isDayPlan,
  listInventory,
  openDay,
  renameErrand,
  renameTask,
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
import { ClockField } from "./ClockField";
import { INVENTORY_INLINE_LIMIT } from "./constants";
import { addCivilDays, formatDayHeading } from "./dates";
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
  const planRef = useRef(plan);
  planRef.current = plan;

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
      if (next) {
        setPlan(next);
      }
      setError(null);
      return true;
    } catch (err: unknown) {
      setError(errorMessage(err));
      if (err instanceof ApiError && err.error === "DaySealed") {
        try {
          const sealed = await openDay(date);
          setPlan(sealed);
        } catch {
          // keep DaySealed message from the write
        }
      }
      return false;
    }
  }

  async function onAdd(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!plan?.writable) {
      return;
    }
    const title = draft.trim();
    if (!title) {
      return;
    }
    await apply(async () => {
      const next = await addTodoOnDay(plan.date, title);
      setDraft("");
      return next;
    });
  }

  function onToggle(todo: Todo): void {
    if (!plan?.writable) {
      return;
    }
    void apply(() =>
      todo.completedOnDay
        ? uncompleteTodo(plan.date, todo.taskId)
        : completeTodo(plan.date, todo.taskId),
    );
  }

  function onRename(todo: Todo, title: string): void {
    if (!plan?.writable) {
      return;
    }
    const nextTitle = title.trim();
    if (!nextTitle || nextTitle === todo.title) {
      return;
    }
    void apply(async () => {
      const result = await renameTask(todo.taskId, nextTitle);
      if (isDayPlan(result)) {
        return result;
      }
      setPlan((current) =>
        current
          ? {
              ...current,
              todos: current.todos.map((item) =>
                item.taskId === todo.taskId
                  ? { ...item, title: result.title }
                  : item,
              ),
            }
          : current,
      );
    });
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
    if (!plan?.writable) {
      return;
    }
    const title = errandDraft.trim();
    if (!title) {
      return;
    }
    await apply(async () => {
      const next = await addErrandOnDay(plan.date, title);
      setErrandDraft("");
      return next;
    });
  }

  function onToggleErrand(errand: Errand): void {
    if (!plan?.writable || isVoidedErrand(errand, plan.writable)) {
      return;
    }
    void apply(() =>
      errand.status === "completed"
        ? uncompleteErrand(errand.id)
        : completeErrand(errand.id),
    );
  }

  function onRenameErrand(errand: Errand, title: string): void {
    if (!plan?.writable) {
      return;
    }
    const nextTitle = title.trim();
    if (!nextTitle || nextTitle === errand.title) {
      return;
    }
    void apply(() => renameErrand(errand.id, nextTitle));
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
          {plan.isToday ? <span className="badge">Today</span> : null}
          {plan.isPast ? <span className="badge">Read-only</span> : null}
          {plan.isFuture ? <span className="badge">Future</span> : null}
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
        <p className="sealed">这一天已封印，不能改</p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      {plan.isToday && planningStatus === "unplanned" ? (
        <section className="planning-prompt" aria-labelledby="planning-prompt-title">
          <div>
            <h2 id="planning-prompt-title">今天尚未规划</h2>
            <p>先挑几件今天真的要做的事；定期事项已保留在清单中。</p>
          </div>
          <button type="button" className="button-secondary" onClick={onStartPlanning}>
            制定今天计划
          </button>
        </section>
      ) : null}
      {(() => {
        const total = plan.todos.length + plan.errands.length;
        if (total === 0) return null;
        const done =
          plan.todos.filter((t) => t.completedOnDay).length +
          plan.errands.filter((e) => e.status === "completed").length;
        const pct = Math.round((done / total) * 100);
        return (
          <div className="day-progress-card">
            <div className="day-progress-header">
              <span className="day-progress-title">今日进度</span>
              <span className="day-progress-counter">
                {done} / {total} 已完成 ({pct}%)
              </span>
            </div>
            <div className="day-progress-track">
              <div
                className="day-progress-fill"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })()}
      <div className="day-columns">
        <section className="column">
          <div className="list-heading">
            <h2>Plan</h2>
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
              今天还没有计划，直接添加或从 To Do 选择。
            </p>
          ) : (
            <ul className="todos">
              {plan.todos.map((todo) => (
                <TodoRow
                  key={todo.taskId}
                  todo={todo}
                  writable={plan.writable}
                  onToggle={onToggle}
                  onRename={onRename}
                  onDelete={onDelete}
                  onUnschedule={onUnschedule}
                  onClocks={(todo, start, end) => {
                    void apply(() =>
                      setTodoClocks(plan.date, todo.taskId, start, end),
                    );
                  }}
                />
              ))}
            </ul>
          )}
          {plan.writable ? (
            <form className="add-form" onSubmit={onAdd}>
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                aria-label="Plan"
                placeholder="添加计划事项 (Enter 保存)..."
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
            <h2>Errands</h2>
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
            <p className="column-empty">今天还没有零碎事项。</p>
          ) : (
            <ul className="todos">
              {plan.errands.map((errand) => (
                <ErrandRow
                  key={errand.id}
                  errand={errand}
                  writable={plan.writable}
                  onToggle={onToggleErrand}
                  onRename={onRenameErrand}
                  onDelete={onDeleteErrand}
                  onClocks={(errand, start, end) => {
                    void apply(() =>
                      setErrandClocks(errand.id, start, end),
                    );
                  }}
                />
              ))}
            </ul>
          )}
          {plan.writable ? (
            <form className="add-form" onSubmit={onAddErrand}>
              <input
                value={errandDraft}
                onChange={(event) => setErrandDraft(event.target.value)}
                aria-label="Errands"
                placeholder="添加零碎事项 (Enter 保存)..."
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
  todo: Todo;
  writable: boolean;
  onToggle: (todo: Todo) => void;
  onRename: (todo: Todo, title: string) => void;
  onDelete: (todo: Todo) => void;
  onUnschedule: (todo: Todo) => void;
  onClocks: (
    todo: Todo,
    start: string | null,
    end: string | null,
  ) => void;
};

function TodoRow({
  todo,
  writable,
  onToggle,
  onRename,
  onDelete,
  onUnschedule,
  onClocks,
}: TodoRowProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(todo.title);

  useEffect(() => {
    setTitle(todo.title);
  }, [todo.title]);

  function finish(save: boolean): void {
    if (!editing) {
      return;
    }
    setEditing(false);
    if (save) {
      onRename(todo, title);
    } else {
      setTitle(todo.title);
    }
  }

  return (
    <li className={todo.completedOnDay ? "todo done" : "todo"}>
      <input
        type="checkbox"
        checked={todo.completedOnDay}
        disabled={!writable}
        onChange={() => onToggle(todo)}
        aria-label={todo.title}
      />
      {editing && writable ? (
        <input
          className="title-input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => finish(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              finish(true);
            }
            if (event.key === "Escape") {
              finish(false);
            }
          }}
          maxLength={200}
          aria-label="改标题"
          autoFocus
        />
      ) : (
        <button
          type="button"
          className="title"
          disabled={!writable}
          onClick={() => {
            if (writable) {
              setEditing(true);
            }
          }}
        >
          {todo.title}
        </button>
      )}
      {todo.recurrence ? (
        <span className="badge recurrence-badge">
          {todo.recurrence.label === "固定周期"
            ? "定期"
            : `定期 · ${todo.recurrence.label}`}
        </span>
      ) : null}
      <span className="clock-row">
        <ClockField
          label="Start"
          value={todo.startClock}
          disabled={!writable}
          onChange={(start) => onClocks(todo, start, todo.endClock)}
        />
        <ClockField
          label="End"
          value={todo.endClock}
          disabled={!writable}
          onChange={(end) => onClocks(todo, todo.startClock, end)}
        />
      </span>
      {writable ? (
        <span className="todo-actions">
          {!todo.completedOnDay ? (
            <button
              type="button"
              className="linkish quiet"
              onClick={() => onUnschedule(todo)}
            >
              Move to To Do
            </button>
          ) : null}
          <button type="button" className="linkish" onClick={() => onDelete(todo)}>
            Delete
          </button>
        </span>
      ) : null}
    </li>
  );
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
      <h3>From To Do</h3>
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
                Add
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
        To Do →
      </a>
    </div>
  );
}

type ErrandRowProps = {
  errand: Errand;
  writable: boolean;
  onToggle: (errand: Errand) => void;
  onRename: (errand: Errand, title: string) => void;
  onDelete: (errand: Errand) => void;
  onClocks: (
    errand: Errand,
    start: string | null,
    end: string | null,
  ) => void;
};

function ErrandRow({
  errand,
  writable,
  onToggle,
  onRename,
  onDelete,
  onClocks,
}: ErrandRowProps) {
  const voided = isVoidedErrand(errand, writable);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(errand.title);

  useEffect(() => {
    setTitle(errand.title);
  }, [errand.title]);

  function finish(save: boolean): void {
    if (!editing) {
      return;
    }
    setEditing(false);
    if (save) {
      onRename(errand, title);
    } else {
      setTitle(errand.title);
    }
  }

  const className =
    errand.status === "completed"
      ? "todo done"
      : voided
        ? "todo expired"
        : "todo";

  return (
    <li className={className}>
      {voided ? (
        <span className="badge">Expired</span>
      ) : (
        <input
          type="checkbox"
          checked={errand.status === "completed"}
          disabled={!writable}
          onChange={() => onToggle(errand)}
          aria-label={errand.title}
        />
      )}
      {editing && writable && !voided ? (
        <input
          className="title-input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => finish(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              finish(true);
            }
            if (event.key === "Escape") {
              finish(false);
            }
          }}
          maxLength={200}
          aria-label="改标题"
          autoFocus
        />
      ) : voided ? (
        <span className="title">{errand.title}</span>
      ) : (
        <button
          type="button"
          className="title"
          disabled={!writable}
          onClick={() => {
            if (writable) {
              setEditing(true);
            }
          }}
        >
          {errand.title}
        </button>
      )}
      {errand.recurrence ? (
        <span className="badge recurrence-badge">
          {errand.recurrence.label === "固定周期"
            ? "定期"
            : `定期 · ${errand.recurrence.label}`}
        </span>
      ) : null}
      <span className="clock-row">
        <ClockField
          label="Start"
          value={errand.startClock}
          disabled={!writable || voided}
          onChange={(start) => onClocks(errand, start, errand.endClock)}
        />
        <ClockField
          label="End"
          value={errand.endClock}
          disabled={!writable || voided}
          onChange={(end) => onClocks(errand, errand.startClock, end)}
        />
      </span>
      {writable && !voided ? (
        <span className="todo-actions">
          <button
            type="button"
            className="linkish"
            onClick={() => onDelete(errand)}
          >
            Delete
          </button>
        </span>
      ) : null}
    </li>
  );
}
