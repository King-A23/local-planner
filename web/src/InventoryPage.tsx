import { useEffect, useState, type FormEvent } from "react";

import {
  addToInventory,
  deleteTask,
  errorMessage,
  listInventory,
  scheduleTask,
  type InventoryItem,
} from "./api";
import { DatePickButton } from "./DatePickButton";
import { maxWritableDate } from "./dates";

type InventoryPageProps = {
  today: string;
  onInventoryChange: () => void;
};

export function InventoryPage({
  today,
  onInventoryChange,
}: InventoryPageProps) {
  const [items, setItems] = useState<InventoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const maxDate = maxWritableDate(today);

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
  }, [today]);

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
      await addToInventory(title);
      setDraft("");
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
      {items.length === 0 ? null : (
        <ul className="inventory-list">
          {items.map((item) => (
            <li key={item.taskId} className="inventory-item">
              <span className="title">{item.title}</span>
              <span className="todo-actions">
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
                  onClick={() => void mutate(() => deleteTask(item.taskId))}
                >
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <form className="add-form" onSubmit={onAdd}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-label="To Do"
          maxLength={200}
        />
      </form>
    </main>
  );
}
