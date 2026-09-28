import { useEffect, useRef, useState } from "react";
import { errorMessage, undoDeletion, type UndoNotice } from "./api";

type TimedNotice = UndoNotice & { expiresAt: number };
const unexpired = (items: TimedNotice[]) => items.filter((item) => item.expiresAt > Date.now());

export function UndoToast({ onChanged }: { onChanged: () => void }) {
  const [notices, setNotices] = useState<TimedNotice[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ token: string; message: string } | null>(null);
  const actionRef = useRef(false);
  const notice = notices[0];
  useEffect(() => {
    const added = (event: Event) => {
      const added = { ...(event as CustomEvent<UndoNotice>).detail, expiresAt: Date.now() + 3_000 };
      setNotices((items) => [added, ...unexpired(items)].slice(0, 5));
      setError(null);
    };
    const clear = () => { setNotices([]); setError(null); };
    window.addEventListener("planner:deleted", added);
    window.addEventListener("planner:restored", clear);
    return () => { window.removeEventListener("planner:deleted", added); window.removeEventListener("planner:restored", clear); };
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => {
      setNotices(unexpired);
      setError(null);
    }, Math.max(0, notice.expiresAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [notice]);
  if (!notice) return null;
  async function undo() {
    if (actionRef.current) return;
    actionRef.current = true; setBusy(true); setError(null);
    try {
      await undoDeletion(notice.token);
      setNotices((items) => unexpired(items).filter((item) => item.token !== notice.token));
      onChanged();
    } catch (err) { setError({ token: notice.token, message: errorMessage(err) }); }
    finally { actionRef.current = false; setBusy(false); }
  }
  return <div className="undo-toast" aria-label="删除操作">
    <span role="status">{error?.token === notice.token ? error.message : `已删除「${notice.title}」`}</span>
    <button type="button" disabled={busy} onClick={() => void undo()}>{busy ? "正在撤销…" : "撤销"}</button>
    <button type="button" className="linkish quiet" aria-label="关闭删除提示" disabled={busy} onClick={() => { setNotices((items) => unexpired(items.slice(1))); setError(null); }}>×</button>
  </div>;
}
