import { useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { errorMessage, settingsRequest, type LauncherCheck } from "./api";
import { navigate } from "./route";
import { useAutoGrowingComposer } from "./useAutoGrowingComposer";
import { ComposerKeyboard } from "./composerKeyboard";
import { useSendShortcut } from "./useSendShortcut";
import { ASSISTANT_EXAMPLES } from "./assistantExamples";

type Launcher = { id: string; name: string; command: string };
type Receipt = {
  summary?: string; changed?: boolean;
  changes?: Array<{ type?: string; id?: string; title?: string; label?: string; count?: number; items?: string[] }>;
};
type Run = {
  id: string; requestId: string; launcherId: string; prompt: string;
  status: string; elapsedSeconds: number; surface: "today" | "todo" | "day"; date: string | null;
  result: { ok: boolean; message?: string; stdout?: string; stderr?: string; receipt?: Receipt } | null;
};
const ACTIVE = new Set(["starting", "running", "paused", "stopping"]);
const STATUSES: Record<string, string> = {
  starting: "正在准备或核对结果", running: "正在执行", paused: "已暂停", stopping: "正在停止",
  succeeded: "执行完成", failed: "执行未完成", failed_with_changes: "执行未完成，已有部分改动",
  stopped: "已停止", stopped_with_changes: "已停止，已有改动保留",
};
const DRAFT_KEY = "planner_agent_draft";
const SELECTION_KEY = "planner_agent_launcher";
function readPreference(key: string): string {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}
function savePreference(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* storage may be unavailable */ }
}
async function request<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message ?? "暂时无法连接，请重试");
  return data as T;
}

export function AgentPanel({ open, onClose, onOpen, triggerRef, surface, date, onRan, onStatusChange }: {
  open: boolean; onClose: () => void; onOpen?: () => void; triggerRef: RefObject<HTMLElement | null>;
  surface: "today" | "todo" | "day"; date: string | null; onRan?: () => void; onStatusChange?: (status: string | null) => void;
}) {
  const [items, setItems] = useState<Launcher[]>([]);
  const [selected, setSelected] = useState(() => readPreference(SELECTION_KEY));
  const [prompt, setPrompt] = useState(() => readPreference(DRAFT_KEY));
  const [run, setRun] = useState<Run | null>(null);
  const [pending, setPending] = useState(false);
  const [synced, setSynced] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [environment, setEnvironment] = useState<LauncherCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [configRevision, setConfigRevision] = useState(0);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const keyboard = useRef(new ComposerKeyboard());
  const { shortcut, sendLabel } = useSendShortcut();
  const actionRef = useRef(false);
  const requestRef = useRef<{ key: string; id: string } | null>(null);
  const notifiedRef = useRef("");
  const onRanRef = useRef(onRan);
  onRanRef.current = onRan;
  const active = Boolean(run && ACTIVE.has(run.status));
  const paused = run?.status === "paused";
  const edited = Boolean(run && prompt.trim() !== run.prompt);
  const blocked = environment && ["missing", "invalid", "login_required"].includes(environment.status);
  useAutoGrowingComposer(composerRef, promptRef);

  useEffect(() => {
    if (!open || !selected || active) return;
    let stopped = false;
    setEnvironment(null); setChecking(true);
    settingsRequest<LauncherCheck>(`/api/launchers/${selected}/check`, "POST").then((result) => {
      if (!stopped) setEnvironment(result);
    }).catch(() => { if (!stopped) setEnvironment({ status: "unknown", message: "暂时无法检测环境，可在设置中重试。" }); })
      .finally(() => { if (!stopped) setChecking(false); });
    return () => { stopped = true; };
  }, [open, selected, active, configRevision]);

  useEffect(() => {
    const reload = (event: Event) => {
      const choice = (event as CustomEvent<string | undefined>).detail;
      request<{ items: Launcher[] }>("/api/launchers").then(({ items }) => {
        setItems(items);
        const saved = typeof choice === "string" ? choice : readPreference(SELECTION_KEY);
        setSelected(items.some((item) => item.id === saved) ? saved : items[0]?.id ?? "");
        setEnvironment(null);
        setConfigRevision((revision) => revision + 1);
      }).catch((err) => setError(errorMessage(err)));
    };
    window.addEventListener("planner:launchers-changed", reload);
    return () => window.removeEventListener("planner:launchers-changed", reload);
  }, []);

  useEffect(() => { onStatusChange?.(active && run ? run.status : null); }, [active, run?.status, onStatusChange]);
  useEffect(() => { savePreference(DRAFT_KEY, prompt); }, [prompt]);
  useEffect(() => { savePreference(SELECTION_KEY, selected); }, [selected]);
  useEffect(() => {
    if (open) promptRef.current?.focus();
  }, [open]);
  useEffect(() => {
    let stopped = false;
    let timer: number;
    request<{ items: Launcher[] }>("/api/launchers").then(({ items }) => {
      if (stopped) return;
      setItems(items);
      setSelected((current) => items.some((item) => item.id === current) ? current : items[0]?.id ?? "");
    }).catch((err) => { if (!stopped) setError(errorMessage(err)); });
    async function poll() {
      try {
        const { run: latest } = await request<{ run: Run | null }>("/api/agent-runs");
        if (stopped) return;
        setRun(latest);
        setSynced(true);
        if (latest && latest.result && notifiedRef.current !== latest.id) {
          notifiedRef.current = latest.id;
          onRanRef.current?.();
        }
      } catch {
        if (!stopped) setSynced(false);
      } finally {
        if (!stopped) timer = window.setTimeout(poll, 1000);
      }
    }
    void poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector("dialog[open]")) {
        setShowMenu(false);
        onClose();
        triggerRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, triggerRef]);

  async function perform(work: () => Promise<void>) {
    if (actionRef.current) return;
    actionRef.current = true;
    setPending(true);
    setError(null);
    try { await work(); } catch (err) { setError(errorMessage(err)); }
    finally { actionRef.current = false; setPending(false); }
  }
  async function submitPrompt(launcherId = selected, context = { surface, date }) {
    const text = prompt.trim();
    if (!text || !launcherId) return;
    const key = JSON.stringify([launcherId, text, context.surface, context.date]);
    if (requestRef.current?.key !== key) requestRef.current = { key, id: crypto.randomUUID() };
    const next = await request<Run>("/api/agent-runs", {
      launcherId, requestId: requestRef.current.id, prompt: text, ...context,
    });
    setRun(next);
    setDismissed(null);
    requestRef.current = null;
    setShowMenu(false);
  }
  function send() {
    if (!active && synced && !blocked && !checking) void perform(() => submitPrompt());
  }
  function control(action: "pause" | "resume" | "stop") {
    if (!run) return;
    void perform(async () => {
      const next = await request<Run>(`/api/agent-runs/${run.id}/${action}`, {});
      setRun(next);
      setDismissed(null);
      if (action === "pause") {
        setPrompt(run.prompt);
        window.setTimeout(() => promptRef.current?.focus(), 0);
        onRanRef.current?.();
      }
    });
  }
  function continueWithChanges() {
    if (!run || !prompt.trim()) return;
    void perform(async () => {
      await request<Run>(`/api/agent-runs/${run.id}/stop`, {});
      let finished: Run | null = null;
      for (let attempt = 0; attempt < 100; attempt++) {
        const next = await request<Run>(`/api/agent-runs/${run.id}`);
        setRun(next);
        if (!ACTIVE.has(next.status)) { finished = next; break; }
        await new Promise((resolve) => window.setTimeout(resolve, 200));
      }
      if (!finished) throw new Error("旧执行仍在收尾。新指令已保留，待停止后再发送。");
      onRanRef.current?.();
      await submitPrompt(run.launcherId, { surface: run.surface, date: run.date });
    });
  }

  const result = run?.result;
  const feedback = Boolean(run && (active || (result && dismissed !== run.id)));
  const output = [result?.stdout, result?.stderr].filter(Boolean).join("\n").trim();
  const status = run ? STATUSES[run.status] ?? run.status : "";

  return createPortal(
    <aside id="agent-panel" className="agent-drawer agent-dock-layer" aria-label="计划助手" hidden={!open}>
      <div className="agent-dock-wrapper">
        {!synced && <p className="agent-connection" role="status">正在重新连接助手，执行状态确认后可继续操作…</p>}
        {!active && (blocked || !items.length) && <div className="agent-setup-hint"><span>{environment?.message ?? "连接一个助手，就能用一句话调整计划。"}</span><button type="button" onClick={() => { onClose(); navigate("/settings#assistant"); }}>连接助手</button></div>}
        {error && <p className="error agent-feedback" role="alert">{error}</p>}
        {feedback && run && <div className="agent-floating-receipt-card agent-run-card">
          <div className="agent-floating-receipt-header">
            <strong role="status">{status}</strong>
            <span className="muted">{Math.floor(run.elapsedSeconds)} 秒</span>
            {!active && <button type="button" className="linkish quiet" aria-label="关闭回执" onClick={() => setDismissed(run.id)}>×</button>}
          </div>
          {active ? <>
            <p className="agent-run-prompt">{run.prompt}</p>
            <div className="agent-run-controls">
              {run.status === "running" && <button type="button" disabled={pending || !synced} onClick={() => control("pause")}>暂停</button>}
              {paused && <button type="button" disabled={pending || !synced || !prompt.trim()} onClick={() => edited ? continueWithChanges() : control("resume")}>{edited ? "按新指令继续" : "继续执行"}</button>}
              <button type="button" className="linkish quiet" disabled={pending || !synced || run.status === "stopping"} onClick={() => control("stop")}>停止本次</button>
            </div>
            {paused && <p className="agent-run-hint">{edited ? "将结束旧执行，保留已有改动，再读取当前计划执行新指令。" : "可修改下面的指令。本机执行已挂起；已发出的远端请求可能仍在继续。"}</p>}
          </> : <>
            {result?.message && <p className="agent-feedback">{result.message}</p>}
            {result?.receipt && <AgentChangeReceipt receipt={result.receipt} />}
            {output && <details className="agent-output"><summary>查看执行详情</summary><pre>{output}</pre></details>}
            {!result?.ok && <button type="button" className="linkish" onClick={() => { setPrompt(run.prompt); promptRef.current?.focus(); }}>编辑指令后重试</button>}
          </>}
        </div>}
        {showMenu && <div className="agent-plus-menu">
          <div className="agent-plus-menu-header">试着这样说</div>
          {ASSISTANT_EXAMPLES.map((example) => <button key={example} type="button" className="agent-plus-menu-item" onClick={() => { setPrompt(example); setShowMenu(false); promptRef.current?.focus(); }}>{example}</button>)}
        </div>}
        <form ref={composerRef} className="agent-pill-bar" onSubmit={(event) => { event.preventDefault(); send(); }}>
          <button type="button" className={`agent-pill-control agent-pill-btn-plus${showMenu ? " is-active" : ""}`}
            disabled={active || pending} aria-label="指令示例" title="指令示例" aria-expanded={showMenu}
            onClick={() => setShowMenu((value) => !value)}>+</button>
          <textarea ref={promptRef} className="agent-pill-input" id="agent-prompt" aria-label={paused ? "调整执行指令" : "给计划助手的指令"}
            rows={1} value={prompt}
            disabled={pending || (active && !paused)} placeholder={items.length ? "写下要助手做的事…" : "请先配置计划助手"}
            onFocus={onOpen}
            onBlur={() => keyboard.current.reset()}
            onCompositionStart={() => keyboard.current.compositionStart()}
            onCompositionEnd={() => keyboard.current.compositionEnd(performance.now())}
            onKeyUp={(event) => keyboard.current.keyUp(event.key)}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              const action = keyboard.current.keyDown(event.nativeEvent, shortcut, performance.now());
              if (action === "ime") {
                // Let the input method commit/cancel, without triggering app shortcuts.
                event.stopPropagation();
              } else if (action === "suppress" || action === "send") {
                event.preventDefault();
                event.stopPropagation();
                if (action === "send" && !active) send();
              }
            }} />
          <div className="agent-pill-control agent-pill-model-btn" title="选择计划助手">
            <span className="agent-pill-model-name" aria-hidden="true">{items.find((item) => item.id === selected)?.name ?? "选择助手"}</span>
            <span className="agent-pill-model-chevron" aria-hidden="true">⌄</span>
            <select className="agent-pill-select-native" aria-label="选择计划助手" value={selected} disabled={active || pending || !items.length} onChange={(event) => setSelected(event.target.value)}>
              {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          {!active && <button type="submit" className="agent-pill-control agent-pill-btn-send"
            aria-label={checking ? "检测中…" : pending ? "正在提交…" : "发送指令"} title={`发送指令（${sendLabel}）`}
            disabled={!synced || pending || checking || Boolean(blocked) || !selected || !prompt.trim()}>
            {checking || pending ? <span className="agent-pill-spinner" aria-hidden="true" /> : <span aria-hidden="true">↑</span>}
          </button>}
        </form>
      </div>
    </aside>, document.body,
  );
}

const CHANGE_LABELS: Record<string, string> = {
  recurrence_created: "新增定期事项", recurrence_updated: "更新定期事项", recurrence_paused: "暂停定期事项",
  recurrence_resumed: "恢复定期事项", recurrence_stopped: "停止定期事项", recurrence_deleted: "删除定期事项",
  plan_added: "新增计划", errand_added: "新增零碎事项", todo_added: "新增待办", todo_to_today: "加入今天",
  todo_scheduled: "安排到某天", moved_to_todo: "移回待办", rescheduled: "调整安排", completed: "完成",
  notes_changed: "更新备注", order_changed: "调整排序", completion_undone: "取消完成", renamed: "更新标题", clock_changed: "更新时间", target_date_changed: "更新目标日期", deleted: "删除",
};
function AgentChangeReceipt({ receipt }: { receipt: Receipt }) {
  return <section className="agent-receipt" aria-label="计划改动">
    {receipt.summary && <p>{receipt.summary.replaceAll("To Do", "待办").replaceAll("Errand", "零碎事项").replaceAll("Plan", "计划")}</p>}
    {(receipt.changes ?? []).length > 0 && <ul>{receipt.changes?.map((change, index) => <li key={`${change.type ?? "change"}-${change.id ?? index}`}>
      {change.label ?? CHANGE_LABELS[change.type ?? ""] ?? "计划改动"}{change.count ? `（${change.count}）` : ""}{change.title ? `：${change.title}` : change.items?.length ? `：${change.items.join("、")}` : ""}
    </li>)}</ul>}
  </section>;
}
