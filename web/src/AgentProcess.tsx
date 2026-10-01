import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { mergeProcessEvents, type ProcessBatch, type ProcessEvent } from "./agentProgressEvents";

const LABELS: Record<string, string> = { running: "进行中", completed: "已完成", failed: "失败", paused: "已暂停", stopping: "停止中", succeeded: "已结束", stopped: "已停止" };

export function AgentProcess({ runId, active }: { runId: string; active: boolean }) {
  const [expanded, setExpanded] = useState(active);
  const [items, setItems] = useState<ProcessEvent[]>([]);
  const [source, setSource] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [disconnected, setDisconnected] = useState(false);
  const cursor = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const collapseTimer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (active) { setExpanded(true); return; }
    // Only fold an already expanded run at completion. Manual reopening of an
    // initially finished run must not start another countdown.
    if (!expanded) return;
    collapseTimer.current = window.setTimeout(() => setExpanded(false), 3000);
    return () => window.clearTimeout(collapseTimer.current);
  }, [active]);
  useEffect(() => {
    if (!expanded) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const res = await fetch(`/api/agent-runs/${encodeURIComponent(runId)}/events?after=${cursor.current}`);
        if (!res.ok) throw new Error("progress unavailable");
        const batch = await res.json() as ProcessBatch;
        if (stopped) return;
        cursor.current = batch.nextSequence;
        setItems((previous) => mergeProcessEvents(previous, batch));
        setSource(batch.source); setTruncated((previous) => previous || batch.truncated); setDisconnected(false);
      } catch { if (!stopped) setDisconnected(true); }
      finally { if (!stopped && active) timer = window.setTimeout(poll, 500); }
    };
    void poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [runId, active, expanded]);
  useLayoutEffect(() => {
    if (follow.current && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [items]);
  return <details className="agent-process" aria-label="模型操作过程" open={expanded}
    onToggle={(event) => setExpanded(event.currentTarget.open)}>
    <summary className="agent-process-heading" onClick={() => window.clearTimeout(collapseTimer.current)}>模型操作过程</summary>
    {disconnected && <p className="muted" role="status">操作过程暂时无法连接，正在重试。执行状态以助手回执为准。</p>}
    {source === "none" ? <p className="muted">此助手暂不提供实时操作过程</p> : <div ref={listRef} className="agent-process-list" onScroll={(event) => {
      const el = event.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    }}>
      {truncated && <p className="muted">较早内容已省略</p>}
      {!items.length && <p className="muted">等待助手输出操作步骤…</p>}
      {items.map((item) => <div key={item.itemId} className={`agent-process-item ${item.kind}`}>
        <div className="agent-process-summary"><span>{item.summary}</span>{item.kind !== "message" && <small>{LABELS[item.status] ?? "已结束"}</small>}</div>
        {item.details && <details><summary>查看详情</summary><pre>{item.details}</pre></details>}
      </div>)}
    </div>}
  </details>;
}
