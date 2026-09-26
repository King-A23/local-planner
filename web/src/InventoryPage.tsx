import { useEffect, useState, type FormEvent } from "react";

import {
  addToInventory,
  completeInventoryTask,
  deleteTask,
  errorMessage,
  listInventory,
  scheduleTask,
  setTaskTarget,
  type InventoryItem,
} from "./api";
import { DatePickButton } from "./DatePickButton";
import { maxWritableDate } from "./dates";

type InventoryPageProps = {
  today: string;
  onInventoryChange: () => void;
  refreshToken?: number;
};

function formatChineseDate(value: string): string {
  if (!value) {
    return "选择日期";
  }
  const [year, month, day] = value.split("-");
  return `${year}年${Number(month)}月${Number(day)}日`;
}

export function InventoryPage({
  today,
  onInventoryChange,
  refreshToken,
}: InventoryPageProps) {
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [draftDate, setDraftDate] = useState("");
  const maxDate = maxWritableDate(today);

  function dueHint(target: string | null): string | null {
    if (!target) {
      return null;
    }
    if (target < today) {
      return "Overdue";
    }
    if (target === today) {
      return "Due";
    }
    return null;
  }

  async function reload(): Promise<InventoryItem[]> {
    const data = await listInventory();
    setItems(data.items);
    return data.items;
  }

  useEffect(() => {
    let cancelled = false;
    listInventory()
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setItems([]);
          setError(errorMessage(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [today, refreshToken]);

  async function mutate(work: () => Promise<unknown>): Promise<void> {
    try {
      await work();
      await reload();
      setError(null);
      onInventoryChange();
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  }

  async function onAdd(event: FormEvent): Promise<void> {
    event.preventDefault();
    const title = draft.trim();
    if (!title) {
      return;
    }
    await mutate(async () => {
      await addToInventory(title, draftDate || null);
      setDraft("");
      setDraftDate("");
    });
  }

  if (items === null) {
    return (
      <main className="page">
        <p>加载中…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <h1>To Do</h1>
      {error ? <p className="error">{error}</p> : null}
      {items.length === 0 ? (
        <p className="empty-copy">还没有待办事项，可以从下面添加第一件。</p>
      ) : (
        <ul className="inventory-list">
          {items.map((item) => (
            <li key={item.taskId} className="inventory-item">
              <span className="title">{item.title}</span>
              {dueHint(item.targetDate) ? (
                <span className="badge">{dueHint(item.targetDate)}</span>
              ) : null}
              {item.recurrence ? (
                <span className="badge recurrence-badge">来自定期事项</span>
              ) : null}
              <input
                type="date"
                value={item.targetDate ?? ""}
                onChange={(event) =>
                  void mutate(() =>
                    setTaskTarget(item.taskId, event.target.value || null),
                  )
                }
                aria-label="Target date"
              />
              <span className="todo-actions">
                <button
                  type="button"
                  className="linkish"
                  aria-label={`标记已完成：${item.title}`}
                  onClick={() => void mutate(() => completeInventoryTask(item.taskId))}
                >
                  标记已完成
                </button>
                <button
                  type="button"
                  className="linkish quiet"
                  onClick={() =>
                    void mutate(() => scheduleTask(item.taskId, today))
                  }
                >
                  Today
                </button>
                <DatePickButton
                  label="Later"
                  min={today}
                  max={maxDate}
                  onPick={(date) =>
                    void mutate(() => scheduleTask(item.taskId, date))
                  }
                />
                <button
                  type="button"
                  className="linkish"
                  aria-label={`删除：${item.title}`}
                  onClick={() => void mutate(() => deleteTask(item.taskId))}
                >
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <section className="inventory-composer" aria-labelledby="inventory-composer-title">
        <h2 id="inventory-composer-title" className="inventory-composer-title">
          在这里添加新的待办事项，也可以让上方的计划助手帮你完成。
        </h2>
        <form className="add-form inventory-add-form" onSubmit={onAdd}>
          <label className="inventory-title-field">
            <span className="visually-hidden">新的待办事项</span>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label="新的待办事项"
              placeholder="输入待办事项，按回车添加"
              maxLength={200}
            />
          </label>
          <label className="inventory-date-field">
            <span className="visually-hidden">目标日期（可选）</span>
            <span className="inventory-date-value" aria-hidden="true">
              {formatChineseDate(draftDate)}
            </span>
            <svg
              className="inventory-date-icon"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
            >
              <path
                d="M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.7"
              />
            </svg>
            <input
              type="date"
              lang="zh-CN"
              value={draftDate}
              onChange={(event) => setDraftDate(event.target.value)}
              aria-label="目标日期（可选）"
            />
          </label>
          <button
            type="submit"
            className="button-primary inventory-add-button"
            disabled={!draft.trim()}
          >
            添加
          </button>
        </form>
      </section>
    </main>
  );
}
