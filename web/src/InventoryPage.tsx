import { openItemEditor, NotesMark } from "./ItemEditor";
import { useItemFocus } from "./useItemFocus";
import { useEntryKeyboard } from "./useEntryKeyboard";
import { useEffect, useRef, useState, type FormEvent } from "react";

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
import { ItemRow } from "./ItemActions";
import { useItemOptions } from "./ItemOptions";
import { useQuickAdd } from "./useQuickAdd";
import { addCivilDays, maxWritableDate } from "./dates";

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
  const options = useItemOptions();
  const maxDate = maxWritableDate(today);
  const quickAddRef = useQuickAdd(items !== null);
  const addingRef = useRef(false);
  useItemFocus(items !== null, items);
  const entryKeyboard = useEntryKeyboard(() => { setDraft(""); quickAddRef.current?.blur(); });

  function dueHint(target: string | null): string | null {
    if (!target) {
      return null;
    }
    if (target < today) {
      return "目标日已过";
    }
    if (target === today) {
      return "目标日是今天";
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
    if (entryKeyboard.shouldIgnoreSubmit()) return;
    const title = draft.trim();
    if (!title || addingRef.current) {
      return;
    }
    addingRef.current = true;
    try {
      await mutate(async () => {
        await addToInventory(title, draftDate || null);
        setDraft((current) => current.trim() === title ? "" : current);
        setDraftDate((current) => current === draftDate ? "" : current);
      });
    } finally { addingRef.current = false; }
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
      <h1>待办</h1>
      {error ? <p className="error">{error}</p> : null}
      {items.length === 0 ? (
        <p className="empty-copy">还没有待办事项，可以从下面添加第一件。</p>
      ) : (
        <ul className="inventory-list">
          {items.map((item) => (
            <ItemRow key={item.taskId} className="inventory-item" id={item.taskId} title={item.title} actions={[
              { label: "编辑详情…", run: () => openItemEditor({ id: item.taskId, kind: "task", title: item.title, notes: item.notes, writable: true }) },
              { label: "标记已完成", run: () => void mutate(() => completeInventoryTask(item.taskId)) },
              { label: "安排到今天", separator: true, run: () => void mutate(() => scheduleTask(item.taskId, today)) },
              { label: "安排到明天", run: () => void mutate(() => scheduleTask(item.taskId, addCivilDays(today, 1))) },
              { label: "选择日期…", run: () => options.show({ title: item.title, kind: "date", date: today, min: today, max: maxDate, save: (values) => scheduleTask(item.taskId, values.date) }) },
              { label: "目标日期…", separator: true, run: () => options.show({ title: item.title, kind: "target", date: item.targetDate ?? "", save: (values) => setTaskTarget(item.taskId, values.date || null) }) },
              { label: "删除", separator: true, danger: true, run: () => void mutate(() => deleteTask(item.taskId)) },
            ]}>
              <button type="button" className="title" onClick={() => openItemEditor({ id: item.taskId, kind: "task", title: item.title, notes: item.notes, writable: true })}>{item.title}<NotesMark notes={item.notes} /></button>
              {dueHint(item.targetDate) ? (
                <span className="badge">{dueHint(item.targetDate)}</span>
              ) : null}
              {item.recurrence ? (
                <span className="badge recurrence-badge">来自定期事项</span>
              ) : null}
              {item.targetDate ? <span className="task-clock-summary">目标：{item.targetDate}</span> : null}
                <button
                  type="button"
                  className="linkish quiet"
                  onClick={() =>
                    void mutate(() => scheduleTask(item.taskId, today))
                  }
                >
                  加入今天
                </button>
            </ItemRow>
          ))}
        </ul>
      )}
      {options.dialog}
      <section className="inventory-composer" aria-labelledby="inventory-composer-title">
        <h2 id="inventory-composer-title" className="inventory-composer-title">
          先记下来，以后再安排
        </h2>
        <form className="add-form inventory-add-form" onSubmit={onAdd}>
          <label className="inventory-title-field">
            <span className="visually-hidden">新的待办事项</span>
            <input
              ref={quickAddRef}
              {...entryKeyboard.bind}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label="新的待办事项"
              placeholder="输入待办事项，按回车添加"
              maxLength={200}
            />
          </label>
          <label className="inventory-date-field">
            <span className="visually-hidden">目标日期（可选，不会自动排入当天）</span>
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
              aria-label="目标日期（可选，不会自动排入当天）"
            />
          </label>
          <button
            type="submit"
            className="button-primary inventory-add-button"
            onClick={entryKeyboard.allowSubmit}
            disabled={!draft.trim()}
          >
            添加
          </button>
        </form>
      </section>
    </main>
  );
}
