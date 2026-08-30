import { useEffect, useState, type FormEvent } from "react";

import {
  addTodoOnDay,
  completeTodo,
  deleteTask,
  errorMessage,
  isDayPlan,
  openDay,
  renameTask,
  uncompleteTodo,
  type DayPlan,
  type Todo,
} from "./api";
import { formatDayHeading } from "./dates";

type DayViewProps = {
  date: string;
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

export function DayView({ date }: DayViewProps) {
  const [plan, setPlan] = useState<DayPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
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
  }, [date]);

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

  return (
    <main className="page">
      <h1 className="day-heading">
        <span>{formatDayHeading(plan.date)}</span>
        {plan.isToday ? <span className="badge">今天</span> : null}
        {plan.isPast ? <span className="badge">只读</span> : null}
        {plan.isFuture ? <span className="badge">未来</span> : null}
      </h1>
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
              placeholder="写下一条正经待办，回车即加入今天"
              aria-label="新的正经待办"
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
