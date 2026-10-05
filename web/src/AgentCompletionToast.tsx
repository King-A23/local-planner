import { useEffect, useState } from "react";
import type { AgentCompletionNotice } from "./agentCompletion";

export function AgentCompletionToast() {
  const [notice, setNotice] = useState<AgentCompletionNotice | null>(null);
  useEffect(() => {
    const completed = (event: Event) => setNotice((event as CustomEvent<AgentCompletionNotice>).detail);
    const clear = () => setNotice(null);
    window.addEventListener("planner:agent-completed", completed);
    window.addEventListener("planner:restored", clear);
    return () => {
      window.removeEventListener("planner:agent-completed", completed);
      window.removeEventListener("planner:restored", clear);
    };
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);
  // Keep the live region mounted so assistive technology announces new text.
  return <div className="agent-completion-region" role="status" aria-live="polite" aria-atomic="true">
    {notice && <div className={`agent-completion-toast is-${notice.kind}`}>
      <span className="agent-completion-icon" aria-hidden="true">{notice.kind === "success" ? "✓" : notice.kind === "error" ? "!" : "■"}</span>
      <div><strong>{notice.title}</strong><p>{notice.message}</p></div>
      <button type="button" className="linkish quiet" aria-label="关闭助手完成通知" onClick={() => setNotice(null)}>×</button>
    </div>}
  </div>;
}
