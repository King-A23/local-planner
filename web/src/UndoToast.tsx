import { useEffect, useRef, useState } from "react";
import { errorMessage, undoDeletion, type UndoNotice } from "./api";

export function UndoToast({ onChanged }: { onChanged: () => void }) {
  const [notices, setNotices] = useState<UndoNotice[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actionRef = useRef(false);
  const notice = notices[0];
  useEffect(() => {
    const added = (event: Event) => {
      setNotices((items) => [(event as CustomEvent<UndoNotice>).detail, ...items].slice(0, 5));
      setError(null);
    };
    const clear = () => { setNotices([]); setError(null); };
    window.addEventListener("planner:deleted", added);
    window.addEventListener("planner:restored", clear);
    return () => { window.removeEventListener("planner:deleted", added); window.removeEventListener("planner:restored", clear); };
  }, []);
  useEffect(() => {
    if (!notice || busy) return;
    const timer = window.setTimeout(() => {
      setNotices((items) => items.filter((item) => item.token !== notice.token));
      setError(null);
    }, 30_000);
    return () => window.clearTimeout(timer);
  }, [notice, busy]);
  if (!notice) return null;
  async function undo() {
    if (actionRef.current) return;
    actionRef.current = true; setBusy(true); setError(null);
    try {
      await undoDeletion(notice.token);
      setNotices((items) => items.filter((item) => item.token !== notice.token));
      onChanged();
    } catch (err) { setError(errorMessage(err)); }
    finally { actionRef.current = false; setBusy(false); }
  }
  return <div className="undo-toast" aria-label="删除操作">
    <span role="status">{error ?? `已删除「${notice.title}」`}</span>
    <button type="button" disabled={busy} onClick={() => void undo()}>{busy ? "正在撤销…" : "撤销"}</button>
    <button type="button" className="linkish quiet" aria-label="关闭删除提示" disabled={busy} onClick={() => { setNotices((items) => items.slice(1)); setError(null); }}>×</button>
  </div>;
}
