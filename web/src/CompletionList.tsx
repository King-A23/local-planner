import { useEffect, useRef, useState, type ReactNode } from "react";
import { ReorderList, type ReorderRow } from "./ReorderList";
import { mergeVisibleOrder } from "./reorder";

const plainRow: ReorderRow = { attributes: {}, handle: null };
export function CompletionList<T>({ items, getId, getLabel, isCompleted, writable, onToggle, onReorder, children }: {
  items: T[]; getId: (item: T) => string; getLabel: (item: T) => string; isCompleted: (item: T) => boolean;
  writable: boolean; onToggle: (item: T) => Promise<boolean>; onReorder: (ids: string[]) => Promise<boolean>;
  children: (item: T, row: ReorderRow, toggle: () => void, busy: boolean, settling: boolean) => ReactNode;
}) {
  const [holding, setHolding] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState(!writable);
  const [announcement, setAnnouncement] = useState("");
  const locks = useRef(new Set<string>());
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const mounted = useRef(true);
  const root = useRef<HTMLDivElement>(null);
  const disclosure = useRef<HTMLButtonElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; timers.current.forEach(clearTimeout); }; }, []);
  const active = items.filter((item) => !isCompleted(item) || holding.has(getId(item)));
  const done = items.filter((item) => isCompleted(item) && !holding.has(getId(item)));
  function focusRow(id: string) { root.current?.querySelector<HTMLInputElement>(`[data-item-id="${CSS.escape(id)}"] input[type=checkbox]`)?.focus({ preventScroll: true }); }
  async function toggle(item: T) {
    const id = getId(item), completing = !isCompleted(item);
    if (!writable || locks.current.has(id)) return;
    const row = root.current?.querySelector<HTMLElement>(`[data-item-id="${CSS.escape(id)}"]`);
    const hadFocus = Boolean(row?.contains(document.activeElement));
    locks.current.add(id); setPending(new Set(locks.current));
    if (completing) setHolding((old) => new Set(old).add(id));
    const ok = await onToggle(item);
    if (!mounted.current) return;
    const finish = () => {
      // Only move keyboard focus if the user has not moved it elsewhere meanwhile.
      const stillFocused = row?.contains(document.activeElement) || (hadFocus && document.activeElement === document.body);
      if (ok && completing && stillFocused) {
        const rows = Array.from(root.current?.querySelectorAll<HTMLElement>(".reorder-list > li") ?? []);
        const index = rows.indexOf(row!);
        const next = rows.slice(index + 1).concat(rows.slice(0, index)).find((candidate) => !candidate.classList.contains("done"));
        (next?.querySelector<HTMLInputElement>("input[type=checkbox]") ?? disclosure.current)?.focus({ preventScroll: true });
      }
      locks.current.delete(id); setPending(new Set(locks.current));
      setHolding((old) => { const next = new Set(old); next.delete(id); return next; });
      if (ok) setAnnouncement(`${getLabel(item)}${completing ? "已完成" : "已恢复"}`);
    };
    if (ok && completing) {
      const timer = setTimeout(() => { timers.current.delete(timer); finish(); }, 650);
      timers.current.add(timer);
    } else {
      finish();
      if (ok && hadFocus) requestAnimationFrame(() => { if (mounted.current && document.activeElement === document.body) focusRow(id); });
    }
  }
  const render = (item: T, row: ReorderRow) => children(item, row, () => void toggle(item), pending.has(getId(item)), holding.has(getId(item)) && isCompleted(item));
  const completedCount = items.filter(isCompleted).length;
  return <div ref={root} className="completion-list">
    <ReorderList items={active} getId={getId} getLabel={getLabel} writable={writable && pending.size === 0}
      onReorder={(ids) => onReorder(mergeVisibleOrder(items.map(getId), ids))}>{render}</ReorderList>
    {completedCount > 0 && <div className="completed-section">
      <button ref={disclosure} type="button" className="completed-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        <span aria-hidden="true">{expanded ? "⌄" : "›"}</span>已完成 <span>{completedCount}</span>
      </button>
      {expanded && <ul className="todos completed-list">{done.map((item) => render(item, plainRow))}</ul>}
    </div>}
    <span className="visually-hidden" role="status">{announcement}</span>
  </div>;
}
