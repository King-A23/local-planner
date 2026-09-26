import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

import {
  createRecurrence,
  deleteRecurrence,
  errorMessage,
  listRecurrences,
  pauseRecurrence,
  resumeRecurrence,
  stopRecurrence,
  updateRecurrence,
  type Recurrence,
  type RecurrenceInput,
  type RecurrenceKind,
  type RecurrenceWeekday,
} from "./api";
import { maxWritableDate } from "./dates";

const WEEKDAYS: ReadonlyArray<{ value: RecurrenceWeekday; label: string }> = [
  { value: "mon", label: "一" },
  { value: "tue", label: "二" },
  { value: "wed", label: "三" },
  { value: "thu", label: "四" },
  { value: "fri", label: "五" },
  { value: "sat", label: "六" },
  { value: "sun", label: "日" },
];

type Editor = { item?: Recurrence; preferredKind?: RecurrenceKind } | null;
type Confirmation = {
  item: Recurrence;
  operation: "pause" | "stop" | "delete";
} | null;

function useModalBehavior(
  dialogRef: RefObject<HTMLElement | null>,
  initialFocusRef: RefObject<HTMLElement | null>,
  onClose: () => void,
): void {
  useEffect(() => {
    const app = document.querySelector<HTMLElement>(".app");
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    app?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() =>
      initialFocusRef.current?.focus(),
    );
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.getClientRects().length > 0);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) {
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !dialogRef.current.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", onKeyDown);
      app?.removeAttribute("inert");
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => previousFocus?.focus());
    };
  }, [dialogRef, initialFocusRef, onClose]);
}

function recurrenceSummary(item: Recurrence): string {
  if (item.frequency === "daily") {
    return "每天";
  }
  const names = item.weekdays
    .map((weekday) => WEEKDAYS.find((day) => day.value === weekday)?.label)
    .filter((label): label is string => Boolean(label));
  return `每周${names.join("、") || "未设置"}`;
}

function stateLabel(item: Recurrence): string {
  if (item.state === "active") {
    return "进行中";
  }
  if (item.state === "paused") {
    return "已暂停";
  }
  return "已停止";
}

function kindLabel(kind: RecurrenceKind): string {
  return kind === "plan" ? "计划" : "零碎事项";
}

function timeSummary(item: Recurrence): string | null {
  if (!item.defaultStartClock && !item.defaultEndClock) {
    return null;
  }
  if (item.defaultStartClock && item.defaultEndClock) {
    return `${item.defaultStartClock}–${item.defaultEndClock}`;
  }
  return item.defaultStartClock
    ? `${item.defaultStartClock} 开始`
    : `${item.defaultEndClock} 前`;
}

export function RecurrencesPage({
  today,
  initialKind,
  onChange,
  refreshToken,
}: {
  today: string;
  initialKind?: RecurrenceKind;
  onChange?: () => void;
  refreshToken?: number;
}) {
  const [items, setItems] = useState<Recurrence[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [busy, setBusy] = useState(false);

  async function reload(): Promise<void> {
    try {
      const result = await listRecurrences();
      setItems(result.items);
      setError(null);
    } catch (err: unknown) {
      setItems([]);
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    void reload();
  }, [refreshToken]);

  async function mutate(
    work: () => Promise<unknown>,
    message: string,
  ): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await work();
      await reload();
      setNotice(message);
      onChange?.();
      return true;
    } catch (err: unknown) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function confirmAction(): Promise<void> {
    if (!confirmation) {
      return;
    }
    const { item, operation } = confirmation;
    const action =
      operation === "pause"
        ? pauseRecurrence
        : operation === "stop"
          ? stopRecurrence
          : deleteRecurrence;
    const applied = await mutate(
      () => action(item.id),
      operation === "pause"
        ? "定期事项已暂停"
        : operation === "stop"
          ? "定期事项已停止"
          : "定期事项已删除",
    );
    if (applied) {
      setConfirmation(null);
    }
  }

  const active = (items ?? []).filter((item) => item.state === "active");
  const paused = (items ?? []).filter((item) => item.state === "paused");
  const stopped = (items ?? []).filter((item) => item.state === "stopped");

  return (
    <main className="page recurrence-page">
      <div className="page-heading-row">
        <div>
          <h1>定期事项</h1>
          <p className="muted recurrence-intro">
            让固定事项按每天或每周出现；不会发送系统通知。
          </p>
        </div>
        <button
          type="button"
          className="button-primary"
          onClick={() => setEditor({ preferredKind: initialKind })}
        >
          新建定期事项
        </button>
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {notice ? <p className="notice" role="status">{notice}</p> : null}
      {items === null ? <p>加载中…</p> : null}
      {items !== null && items.length === 0 ? (
        <section className="empty-state">
          <h2>还没有定期事项</h2>
          <p>例如每天吃药，或每周五写周报。</p>
        </section>
      ) : null}
      {active.length > 0 ? (
        <RoutineSection
          title="进行中"
          items={active}
          busy={busy}
          onEdit={(item) => setEditor({ item })}
          onPause={(item) => setConfirmation({ item, operation: "pause" })}
          onResume={(item) =>
            void mutate(() => resumeRecurrence(item.id), "定期事项已恢复")
          }
          onStop={(item) => setConfirmation({ item, operation: "stop" })}
          onDelete={(item) => setConfirmation({ item, operation: "delete" })}
        />
      ) : null}
      {paused.length > 0 ? (
        <RoutineSection
          title="已暂停"
          items={paused}
          busy={busy}
          onEdit={(item) => setEditor({ item })}
          onPause={(item) => setConfirmation({ item, operation: "pause" })}
          onResume={(item) =>
            void mutate(() => resumeRecurrence(item.id), "定期事项已恢复")
          }
          onStop={(item) => setConfirmation({ item, operation: "stop" })}
          onDelete={(item) => setConfirmation({ item, operation: "delete" })}
        />
      ) : null}
      {stopped.length > 0 ? (
        <RoutineSection
          title="已停止"
          items={stopped}
          busy={busy}
          onEdit={(item) => setEditor({ item })}
          onPause={(item) => setConfirmation({ item, operation: "pause" })}
          onResume={(item) =>
            void mutate(() => resumeRecurrence(item.id), "定期事项已恢复")
          }
          onStop={(item) => setConfirmation({ item, operation: "stop" })}
          onDelete={(item) => setConfirmation({ item, operation: "delete" })}
        />
      ) : null}
      {editor ? (
        <RoutineFormDialog
          today={today}
          item={editor.item}
          preferredKind={editor.preferredKind}
          busy={busy}
          onClose={() => setEditor(null)}
          onSubmit={async (input) => {
            const saved = await mutate(
              () =>
                editor.item
                  ? updateRecurrence(editor.item.id, input)
                  : createRecurrence(input),
              editor.item ? "定期事项已更新" : "定期事项已创建",
            );
            if (saved) {
              setEditor(null);
            }
          }}
        />
      ) : null}
      {confirmation ? (
        <ConfirmationDialog
          item={confirmation.item}
          operation={confirmation.operation}
          busy={busy}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => void confirmAction()}
        />
      ) : null}
    </main>
  );
}

function RoutineSection({
  title,
  items,
  busy,
  onEdit,
  onPause,
  onResume,
  onStop,
  onDelete,
}: {
  title: string;
  items: Recurrence[];
  busy: boolean;
  onEdit: (item: Recurrence) => void;
  onPause: (item: Recurrence) => void;
  onResume: (item: Recurrence) => void;
  onStop: (item: Recurrence) => void;
  onDelete: (item: Recurrence) => void;
}) {
  return (
    <section className="recurrence-section" aria-labelledby={`recurrences-${title}`}>
      <h2 id={`recurrences-${title}`}>{title}</h2>
      <ul className="recurrence-list">
        {items.map((item) => {
          const time = timeSummary(item);
          return (
            <li className="recurrence-card" key={item.id}>
              <div className="recurrence-card-main">
                <div className="recurrence-card-title">
                  <h3>{item.title}</h3>
                  <span className="badge">{kindLabel(item.kind)}</span>
                  <span className="badge recurrence-state">{stateLabel(item)}</span>
                </div>
                <p className="muted">
                  {recurrenceSummary(item)}
                  {time ? ` · ${time}` : ""}
                </p>
                {item.state === "stopped" && item.stoppedAt ? (
                  <p className="muted">停止于 {item.stoppedAt}</p>
                ) : item.nextOccurrenceDate ? (
                  <p className="muted">下次出现：{item.nextOccurrenceDate}</p>
                ) : null}
              </div>
              <div className="recurrence-actions">
                {item.state !== "stopped" ? (
                  <button
                    type="button"
                    className="linkish quiet"
                    disabled={busy}
                    onClick={() => onEdit(item)}
                  >
                    编辑
                  </button>
                ) : null}
                {item.state === "stopped" ? (
                  <button
                    type="button"
                    className="linkish"
                    disabled={busy}
                    onClick={() => onDelete(item)}
                  >
                    删除
                  </button>
                ) : null}
                {item.state === "active" ? (
                  <button
                    type="button"
                    className="linkish quiet"
                    disabled={busy}
                    onClick={() => onPause(item)}
                  >
                    暂停
                  </button>
                ) : null}
                {item.state === "paused" ? (
                  <button
                    type="button"
                    className="linkish quiet"
                    disabled={busy}
                    onClick={() => onResume(item)}
                  >
                    恢复
                  </button>
                ) : null}
                {item.state !== "stopped" ? (
                  <button
                    type="button"
                    className="linkish"
                    disabled={busy}
                    onClick={() => onStop(item)}
                  >
                    停止
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function RoutineFormDialog({
  today,
  item,
  preferredKind,
  busy,
  onClose,
  onSubmit,
}: {
  today: string;
  item?: Recurrence;
  preferredKind?: RecurrenceKind;
  busy: boolean;
  onClose: () => void;
  onSubmit: (input: RecurrenceInput) => Promise<void>;
}) {
  const [title, setTitle] = useState(item?.title ?? "");
  const [kind, setKind] = useState<RecurrenceKind>(
    item?.kind ?? preferredKind ?? "plan",
  );
  const [frequency, setFrequency] = useState<"daily" | "weekly">(
    item?.frequency ?? "daily",
  );
  const [weekdays, setWeekdays] = useState<RecurrenceWeekday[]>(
    item?.weekdays ?? ["mon"],
  );
  const [startDate, setStartDate] = useState(item?.startDate ?? today);
  const [startClock, setStartClock] = useState(item?.defaultStartClock ?? "");
  const [endClock, setEndClock] = useState(item?.defaultEndClock ?? "");
  const [formError, setFormError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  useModalBehavior(dialogRef, titleRef, onClose);

  function toggleWeekday(day: RecurrenceWeekday): void {
    setWeekdays((current) =>
      current.includes(day)
        ? current.filter((value) => value !== day)
        : [...current, day],
    );
  }

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      setFormError("请填写事项标题");
      return;
    }
    if (frequency === "weekly" && weekdays.length === 0) {
      setFormError("每周至少选择一天");
      return;
    }
    if (!startDate) {
      setFormError("请选择开始日期");
      return;
    }
    setFormError(null);
    await onSubmit({
      title: trimmed,
      kind,
      frequency,
      weekdays: frequency === "weekly" ? weekdays : [],
      startDate,
      defaultStartClock: startClock || null,
      defaultEndClock: endClock || null,
    });
  }

  return createPortal(
    <div className="modal-layer">
      <button
        type="button"
        className="modal-backdrop"
        tabIndex={-1}
        aria-label="关闭定期事项表单"
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        className="modal-card recurrence-form-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="recurrence-form-title"
      >
        <header className="modal-header">
          <h2 id="recurrence-form-title">
            {item ? "编辑定期事项" : "新建定期事项"}
          </h2>
          <button type="button" className="agent-close" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </header>
        <p className="muted form-help">
          {item
            ? "修改只影响尚未生成的未来事项；今天与历史记录不变。"
            : "本应用不会发送系统通知或闹钟。"}
        </p>
        {formError ? <p className="error" role="alert">{formError}</p> : null}
        <form className="routine-form" onSubmit={(event) => void submit(event)}>
          <label>
            标题
            <input
              ref={titleRef}
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <fieldset>
            <legend>类型</legend>
            <label>
              <input
                type="radio"
                checked={kind === "plan"}
                value="plan"
                onChange={() => setKind("plan")}
              />
              计划
            </label>
            <label>
              <input
                type="radio"
                checked={kind === "errand"}
                value="errand"
                onChange={() => setKind("errand")}
              />
              零碎事项
            </label>
          </fieldset>
          <p className="form-help">
            {kind === "plan"
              ? "计划本期未完成会回到待办；下一期仍会照常出现。"
              : "零碎事项本期未完成当天作废，不会进入待办。"}
          </p>
          <fieldset>
            <legend>重复</legend>
            <label>
              <input
                type="radio"
                checked={frequency === "daily"}
                value="daily"
                onChange={() => setFrequency("daily")}
              />
              每天
            </label>
            <label>
              <input
                type="radio"
                checked={frequency === "weekly"}
                value="weekly"
                onChange={() => setFrequency("weekly")}
              />
              每周
            </label>
          </fieldset>
          {frequency === "weekly" ? (
            <fieldset>
              <legend>每周哪几天</legend>
              <div className="weekday-grid">
                {WEEKDAYS.map((day) => (
                  <label key={day.value}>
                    <input
                      type="checkbox"
                      checked={weekdays.includes(day.value)}
                      onChange={() => toggleWeekday(day.value)}
                    />
                    周{day.label}
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}
          <label>
            开始日期
            <input
              type="date"
              min={today}
              max={maxWritableDate(today)}
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>
          <div className="form-row">
            <label>
              默认开始时间
              <input
                type="time"
                step="300"
                value={startClock}
                onChange={(event) => setStartClock(event.target.value)}
              />
            </label>
            <label>
              默认结束时间
              <input
                type="time"
                step="300"
                value={endClock}
                onChange={(event) => setEndClock(event.target.value)}
              />
            </label>
          </div>
          <div className="modal-actions">
            <button type="button" className="button-secondary" disabled={busy} onClick={onClose}>
              取消
            </button>
            <button type="submit" className="button-primary" disabled={busy}>
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}

function ConfirmationDialog({
  item,
  operation,
  busy,
  onCancel,
  onConfirm,
}: {
  item: Recurrence;
  operation: "pause" | "stop" | "delete";
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const isStop = operation === "stop";
  const isDelete = operation === "delete";
  const confirmRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useModalBehavior(dialogRef, confirmRef, onCancel);

  return createPortal(
    <div className="modal-layer">
      <button
        type="button"
        className="modal-backdrop"
        tabIndex={-1}
        aria-label="取消"
        onClick={onCancel}
      />
      <section
        ref={dialogRef}
        className="modal-card confirmation-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="recurrence-confirm-title"
      >
        <h2 id="recurrence-confirm-title">
          {isDelete
            ? "删除定期事项？"
            : isStop
              ? "停止定期事项？"
              : "暂停定期事项？"}
        </h2>
        <p>
          {isDelete
            ? `删除“${item.title}”后，它会从定期事项列表消失且无法撤销；已经生成的事项和历史记录仍会保留。`
            : isStop
            ? `停止“${item.title}”后不会再生成新事项，且不能恢复；今天已出现的事项和历史记录会保留。`
            : `暂停“${item.title}”后不再生成未来事项；今天已出现的事项和历史记录会保留。`}
        </p>
        <div className="modal-actions">
          <button type="button" className="button-secondary" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={isStop || isDelete ? "button-danger" : "button-primary"}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy
              ? "处理中…"
              : isDelete
                ? "删除定期事项"
                : isStop
                  ? "停止定期事项"
                  : "暂停"}
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
