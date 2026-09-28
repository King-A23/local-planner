import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { moveItem } from "./reorder";

export type ReorderRow = { handle: ReactNode; attributes: HTMLAttributes<HTMLLIElement> };
type Drop = { id: string; after: boolean };
type Drag = { id: string; x: number; y: number; started: boolean };
export function ReorderList<T>({ items, getId, getLabel, writable, onReorder, children }: {
  items: T[]; getId: (item: T) => string; getLabel: (item: T) => string; writable: boolean;
  onReorder: (ids: string[]) => Promise<boolean>; children: (item: T, row: ReorderRow) => ReactNode;
}) {
  const [source, setSource] = useState<string | null>(null);
  const [target, setTarget] = useState<Drop | null>(null);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [pendingIds, setPendingIds] = useState<string[] | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const drag = useRef<Drag | null>(null);
  const drop = useRef<Drop | null>(null);
  const focusAfter = useRef<string | null>(null);
  const busy = useRef(false);
  const list = useRef<HTMLUListElement>(null);
  const ids = items.map(getId);
  const visible = pendingIds && pendingIds.length === ids.length && pendingIds.every((id) => ids.includes(id))
    ? pendingIds.map((id) => items.find((item) => getId(item) === id)!) : items;
  function clearDrag() { drag.current = null; drop.current = null; setSource(null); setTarget(null); }
  useEffect(() => {
    const cancel = (e: KeyboardEvent) => {
      if (e.key === "Escape" && drag.current) { e.preventDefault(); clearDrag(); }
    };
    window.addEventListener("keydown", cancel);
    return () => window.removeEventListener("keydown", cancel);
  }, []);
  useEffect(() => {
    if (pendingIds || !focusAfter.current) return;
    list.current?.querySelector<HTMLButtonElement>(`[data-reorder-id="${CSS.escape(focusAfter.current)}"]`)?.focus({ preventScroll: true });
    focusAfter.current = null;
  }, [pendingIds, items]);
  async function commit(next: string[], moved: string) {
    clearDrag();
    if (busy.current || next.every((id, i) => id === ids[i])) return;
    busy.current = true; setPendingIds(next);
    const ok = await onReorder(next);
    focusAfter.current = moved;
    setPendingIds(null); busy.current = false;
    const label = items.find((item) => getId(item) === moved);
    setAnnouncement(ok ? `${label ? getLabel(label) : "事项"}已移至第 ${next.indexOf(moved) + 1} 项` : "排序未保存，请重试");
  }
  function locate(x: number, y: number) {
    const bounds = list.current?.getBoundingClientRect();
    let next: Drop | null = null;
    if (bounds && x >= bounds.left - 28 && x <= bounds.right + 16 && y >= bounds.top - 24 && y <= bounds.bottom + 24) {
      for (const row of list.current!.querySelectorAll<HTMLElement>("[data-reorder-row]")) {
        const rect = row.getBoundingClientRect();
        next = { id: row.dataset.reorderRow!, after: y > rect.top + rect.height / 2 };
        if (y < rect.bottom) break;
      }
    }
    drop.current = next; setTarget(next);
  }
  const draggedItem = items.find((item) => getId(item) === source);
  return <>
    <ul className="todos reorder-list" ref={list} aria-busy={pendingIds !== null}>
      {visible.map((item) => {
        const id = getId(item);
        return children(item, {
          attributes: {
            "data-reorder-row": id,
            "data-dragging": source === id || undefined,
            "data-drop": target?.id === id && target.id !== source ? target.after ? "after" : "before" : undefined,
          } as HTMLAttributes<HTMLLIElement>,
          handle: writable && items.length > 1 ? <button type="button" className="drag-handle"
            data-reorder-id={id} aria-label={`调整顺序：${getLabel(item)}`} title="拖动排序；Option / Alt + ↑ ↓ 调整顺序"
            aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown" disabled={pendingIds !== null}
            onPointerDown={(event) => {
              if (event.button !== 0 || busy.current) return;
              event.currentTarget.setPointerCapture(event.pointerId);
              drag.current = { id, x: event.clientX, y: event.clientY, started: false };
            }}
            onPointerMove={(event) => {
              const current = drag.current;
              if (!current) return;
              if (!current.started && Math.hypot(event.clientX - current.x, event.clientY - current.y) < 5) return;
              event.preventDefault(); current.started = true; setSource(current.id);
              setPointer({ x: event.clientX, y: event.clientY });
              if (event.clientY < 60) window.scrollBy(0, -18);
              else if (event.clientY > window.innerHeight - 60) window.scrollBy(0, 18);
              locate(event.clientX, event.clientY);
            }}
            onPointerUp={(event) => {
              const current = drag.current, destination = drop.current;
              if (current?.started && destination && writable) {
                event.preventDefault();
                void commit(moveItem(ids, current.id, destination.id, destination.after), current.id);
              } else clearDrag();
            }}
            onPointerCancel={clearDrag} onLostPointerCapture={clearDrag}
            onKeyDown={(event) => {
              if (!event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key) || event.repeat) return;
              event.preventDefault();
              const index = ids.indexOf(id), direction = event.key === "ArrowDown" ? 1 : -1;
              if (ids[index + direction]) void commit(moveItem(ids, id, ids[index + direction], direction === 1), id);
            }}>
            <svg width="12" height="18" viewBox="0 0 12 18" fill="currentColor" aria-hidden="true"><path d="M3 3h2v2H3zm4 0h2v2H7zM3 8h2v2H3zm4 0h2v2H7zM3 13h2v2H3zm4 0h2v2H7z" /></svg>
          </button> : null,
        });
      })}
    </ul>
    <span className="visually-hidden" role="status">{announcement}</span>
    {draggedItem && createPortal(<div className="drag-preview" aria-hidden="true" style={{ left: Math.min(pointer.x + 16, window.innerWidth - 270), top: pointer.y + 12 }}>{getLabel(draggedItem)}</div>, document.body)}
  </>;
}
