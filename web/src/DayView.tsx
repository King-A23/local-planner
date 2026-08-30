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
  openDay,
  renameErrand,
  renameTask,
  uncompleteErrand,
  uncompleteTodo,
  type DayPlan,
  type Errand,
  type Todo,
} from "./api";
import { addCivilDays, formatDayHeading } from "./dates";
import { handleNavClick } from "./route";

type DayViewProps = {
  date: string;
  serverToday?: string;
};

function emptyCopy(plan: DayPlan): string {
  if (plan.isToday) {
    return "写下今天要做的事，或从库存抽几条";
  }
  if (plan.isFuture) {
    return "预排这一天";
  }
  return "这一天没有记录";
}

function addPlaceholder(plan: DayPlan): string {
  if (plan.isToday) {
    return "写下一条正经待办，回车即加入今天";
  }
  return "写下一条正经待办，回车即加入这一天";
}

function errandEmptyCopy(plan: DayPlan): string {
  if (plan.isPast) {
    return "这一天没有差事";
  }
  return "记下随手要办、当天作废的差事";
}

function errandPlaceholder(plan: DayPlan): string {
  if (plan.isToday) {
    return "写下一条零碎差事，回车即加入今天";
  }
  return "写下一条零碎差事，回车即加入这一天";
}

function isVoidedErrand(errand: Errand, writable: boolean): boolean {
  return errand.status === "expired" || (!writable && errand.status !== "completed");
}

export function DayView({ date, serverToday }: DayViewProps) {
  const [plan, setPlan] = useState<DayPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [errandDraft, setErrandDraft] = useState("");
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
  }, [date, serverToday]);

  async function apply(
    work: () => Promise<DayPlan | void>,
  ): Promise<void> {
    try {
      const next = await work();
      if (next) {
        setPlan(next);
      }
      setError(null);
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
        <p className="sealed">这一天已封印，不能改</p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <section className="column">
        <h2>正经待办</h2>
        {plan.todos.length === 0 ? (
          <p className="muted">{emptyCopy(plan)}</p>
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
              />
            ))}
          </ul>
        )}
        {plan.writable ? (
          <form className="add-form" onSubmit={onAdd}>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={addPlaceholder(plan)}
              aria-label="新的正经待办"
              maxLength={200}
            />
          </form>
        ) : null}
      </section>
      <section className="column">
        <h2>零碎差事</h2>
        {plan.errands.length === 0 ? (
          <p className="muted">{errandEmptyCopy(plan)}</p>
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
              />
            ))}
          </ul>
        )}
        {plan.writable ? (
          <form className="add-form" onSubmit={onAddErrand}>
            <input
              value={errandDraft}
              onChange={(event) => setErrandDraft(event.target.value)}
              placeholder={errandPlaceholder(plan)}
              aria-label="新的零碎差事"
              maxLength={200}
            />
          </form>
        ) : null}
      </section>
    </main>
  );
}

type TodoRowProps = {
  todo: Todo;
  writable: boolean;
  onToggle: (todo: Todo) => void;
  onRename: (todo: Todo, title: string) => void;
  onDelete: (todo: Todo) => void;
};

function TodoRow({
  todo,
  writable,
  onToggle,
  onRename,
  onDelete,
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
      {writable ? (
        <button type="button" className="linkish" onClick={() => onDelete(todo)}>
          删除
        </button>
      ) : null}
    </li>
  );
}

type ErrandRowProps = {
  errand: Errand;
  writable: boolean;
  onToggle: (errand: Errand) => void;
  onRename: (errand: Errand, title: string) => void;
  onDelete: (errand: Errand) => void;
};

function ErrandRow({
  errand,
  writable,
  onToggle,
  onRename,
  onDelete,
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
        <span className="badge">已作废</span>
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
      {writable && !voided ? (
        <button
          type="button"
          className="linkish"
          onClick={() => onDelete(errand)}
        >
          删除
        </button>
      ) : null}
    </li>
  );
}
