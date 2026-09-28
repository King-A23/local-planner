import { useEffect, useId, useLayoutEffect, useRef, useState, type HTMLAttributes, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

export type ItemAction = { label: string; run: () => void; disabled?: boolean; danger?: boolean; separator?: boolean };

/** Shared by list rows and standalone section menus. */
function useItemMenu(title: string, actions: ItemAction[]) {
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();
  function close(restore = false) {
    setAnchor(null);
    if (restore) button.current?.focus({ preventScroll: true });
  }
  function open(x: number, y: number) {
    window.dispatchEvent(new Event("planner:close-item-menu"));
    setAnchor({ x, y });
  }
  useEffect(() => {
    const dismiss = () => setAnchor(null);
    window.addEventListener("planner:close-item-menu", dismiss);
    return () => window.removeEventListener("planner:close-item-menu", dismiss);
  }, []);
  useLayoutEffect(() => {
    if (!anchor || !menu.current) return;
    const bounds = menu.current.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(anchor.x, window.innerWidth - bounds.width - 8)), top: Math.max(8, Math.min(anchor.y, window.innerHeight - bounds.height - 8)) });
    menu.current.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus({ preventScroll: true });
  }, [anchor]);
  useEffect(() => {
    if (!anchor) return;
    const outside = (e: PointerEvent) => {
      if (e.target instanceof Node && !menu.current?.contains(e.target) && !button.current?.contains(e.target)) close();
    };
    const dismiss = () => close();
    const scroll = (e: Event) => { if (!(e.target instanceof Node) || !menu.current?.contains(e.target)) close(); };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", dismiss);
    window.addEventListener("blur", dismiss);
    window.addEventListener("scroll", scroll, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("blur", dismiss);
      window.removeEventListener("scroll", scroll, true);
    };
  }, [anchor]);
  const onContextMenu = (event: MouseEvent<HTMLElement>) => {
    if (!actions.length || (event.target instanceof Element && event.target.closest("input, textarea, [contenteditable=true]"))) return;
    event.preventDefault(); open(event.clientX, event.clientY);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (actions.length && (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10"))) {
      event.preventDefault(); const rect = button.current!.getBoundingClientRect(); open(rect.right - 208, rect.bottom + 4);
    }
  };
  const content = actions.length > 0 ? <>
    <button ref={button} type="button" className="item-menu-trigger" aria-label={`更多操作：${title}`} title="更多操作"
      aria-haspopup="menu" aria-expanded={Boolean(anchor)} aria-controls={anchor ? menuId : undefined}
      onClick={() => { if (anchor) close(); else { const rect = button.current!.getBoundingClientRect(); open(rect.right - 208, rect.bottom + 4); } }}
      onKeyDown={(event) => { if (event.key === "ArrowDown") { event.preventDefault(); const rect = button.current!.getBoundingClientRect(); open(rect.right - 208, rect.bottom + 4); } }}>···</button>
    {anchor && createPortal(<div id={menuId} ref={menu} className="item-action-menu" role="menu" aria-label={`操作：${title}`} style={position}
      onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); }}
      onKeyDown={(event) => {
        // Keep menu keys away from page-wide shortcuts, especially Agent Escape.
        event.stopPropagation();
        if (event.key === "Escape") { event.preventDefault(); close(true); }
        if (event.key === "Tab") { close(true); }
        const buttons = Array.from(menu.current!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
        const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? (current + 1) % buttons.length : event.key === "ArrowUp" ? (current - 1 + buttons.length) % buttons.length : null;
        if (index !== null) { event.preventDefault(); buttons[index]?.focus(); }
      }}>
      {actions.map((action) => <button key={action.label} role="menuitem" tabIndex={-1} type="button" disabled={action.disabled}
        className={`${action.danger ? "danger" : ""} ${action.separator ? "menu-separator" : ""}`}
        onClick={() => { close(true); action.run(); }}>{action.label}</button>)}
    </div>, document.body)}
  </> : null;
  return { content, onContextMenu, onKeyDown };
}

/** The row and its visible button open the same keyboard-accessible menu. */
export function ItemRow({ id, title, actions, children, ...props }: {
  id: string; title: string; actions: ItemAction[]; children: ReactNode;
} & HTMLAttributes<HTMLLIElement>) {
  const { content, ...handlers } = useItemMenu(title, actions);
  return <li {...props} data-item-id={id} {...handlers}>{children}{content}</li>;
}

export function ItemMenu({ title, actions }: { title: string; actions: ItemAction[] }) {
  const { content, ...handlers } = useItemMenu(title, actions);
  return <div className="item-menu" {...handlers}>{content}</div>;
}
