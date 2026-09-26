import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

import { errorMessage } from "./api";

type Launcher = {
  id: string;
  name: string;
  command: string;
};

type RunResponse = {
  ok?: boolean;
  message?: string;
  stdout?: string;
  stderr?: string;
  receipt?: {
    summary?: string;
    changed?: boolean;
    counts?: Record<string, number>;
    changes?: Array<{
      type?: string;
      entity?: string;
      id?: string;
      title?: string;
      label?: string;
      count?: number;
      items?: string[];
    }>;
  };
};

const JSON_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

async function readLaunchers(): Promise<Launcher[]> {
  const res = await fetch("/api/launchers");
  if (!res.ok) {
    throw new Error("无法加载 Agent");
  }
  const body = (await res.json()) as { items: Launcher[] };
  return body.items;
}

let _measureCanvas: HTMLCanvasElement | null = null;
function measureTextWidth(text: string, font: string): number {
  if (typeof document === "undefined") return text.length * 8;
  if (!_measureCanvas) _measureCanvas = document.createElement("canvas");
  const ctx = _measureCanvas.getContext("2d");
  if (!ctx) return text.length * 8;
  ctx.font = font;
  return ctx.measureText(text).width;
}

export function AgentPanel({
  open,
  onClose,
  onOpen,
  triggerRef,
  surface,
  date,
  onRan,
}: {
  open: boolean;
  onClose: () => void;
  onOpen?: () => void;
  triggerRef: RefObject<HTMLElement | null>;
  surface: "today" | "todo" | "day";
  date: string | null;
  onRan?: () => void;
}) {
  const [items, setItems] = useState<Launcher[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<RunResponse["receipt"] | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [isMultiline, setIsMultiline] = useState(false);

  const drawerRef = useRef<HTMLElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = promptRef.current;
    if (!el) return;

    const text = prompt;
    const hasNewline = text.includes("\n");

    let shouldBeMulti = hasNewline;
    if (!hasNewline && text.trim().length > 0) {
      const containerWidth = el.parentElement?.clientWidth ?? 600;
      const singleLineWidth = Math.max(containerWidth - 180, 160);

      const font = window.getComputedStyle(el).font || "15px system-ui";
      const textWidth = measureTextWidth(text, font);
      if (textWidth > singleLineWidth) {
        shouldBeMulti = true;
      }
    }

    setIsMultiline((prev) => (prev === shouldBeMulti ? prev : shouldBeMulti));

    if (!shouldBeMulti) {
      el.style.height = "";
    } else {
      el.style.height = "auto";
      const scrollH = el.scrollHeight;
      const nextHeight = Math.min(Math.max(scrollH, 44), 192);
      el.style.height = `${nextHeight}px`;
    }
  }, [prompt]);

  useLayoutEffect(() => {
    adjustHeight();
  }, [prompt, adjustHeight]);

  useEffect(() => {
    window.addEventListener("resize", adjustHeight);
    return () => window.removeEventListener("resize", adjustHeight);
  }, [adjustHeight]);

  const currentLauncher = items.find((item) => item.id === selected) ?? items[0];

  function applyItems(next: Launcher[], preferId?: string): void {
    setItems(next);
    const keep =
      preferId && next.some((item) => item.id === preferId)
        ? preferId
        : next.some((item) => item.id === selected)
          ? selected
          : (next[0]?.id ?? "");
    setSelected(keep);
  }

  function reload(preferId?: string): void {
    readLaunchers()
      .then((next) => {
        applyItems(next, preferId);
        setError(null);
      })
      .catch((err: unknown) => setError(errorMessage(err)));
  }

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    if (open) {
      promptRef.current?.focus();
      adjustHeight();
    }
  }, [open, adjustHeight]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (showMenu) {
          setShowMenu(false);
          return;
        }
        if (receipt || error || output) {
          setReceipt(null);
          setError(null);
          setOutput(null);
          return;
        }
        onClose();
        triggerRef.current?.focus();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showMenu, receipt, error, output, onClose, triggerRef]);

  async function onDelete(): Promise<void> {
    if (!selected) {
      return;
    }
    try {
      const res = await fetch(`/api/launchers/${selected}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error("删除失败");
      }
      setReceipt({ summary: "Agent 已删除" });
      reload();
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  }

  async function run(): Promise<void> {
    if (!selected || !prompt.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    setReceipt(null);
    setOutput(null);
    try {
      const res = await fetch(`/api/launchers/${selected}/run`, {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({
          prompt: prompt.trim(),
          surface,
          date,
        }),
      });
      const body = (await res.json()) as RunResponse;
      onRan?.();
      if (!res.ok || !body.ok) {
        const scriptOutput = [body.stdout, body.stderr]
          .filter((value): value is string => Boolean(value?.trim()))
          .join("\n")
          .trim();
        setError(
          body.message || "未能确认本次更新完成。请查看当前计划；执行可能已产生部分改动。",
        );
        if (body.receipt?.changed) {
          setReceipt(body.receipt);
        }
        setOutput(scriptOutput || null);
        return;
      }
      setReceipt(body.receipt ?? { summary: "计划已刷新" });
      if (!body.receipt && body.stdout?.trim()) {
        setOutput(body.stdout.trim());
      }
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function handlePromptKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>,
  ): void {
    if (event.nativeEvent.isComposing) {
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busy && selected && prompt.trim()) {
        void run();
      }
    }
  }

  async function onSend(event: FormEvent): Promise<void> {
    event.preventDefault();
    await run();
  }

  const hasFeedback = Boolean(receipt || error || output);

  return createPortal(
    <aside
      ref={drawerRef}
      id="agent-panel"
      className="agent-drawer agent-dock-layer"
      role="dialog"
      aria-modal="true"
      aria-label="计划助手"
    >
      <div
        className="agent-backdrop"
        tabIndex={-1}
        aria-hidden="true"
        onClick={() => {
          setShowMenu(false);
          setReceipt(null);
          setError(null);
          setOutput(null);
        }}
      />

      <div className="agent-dock-wrapper">
        {/* 浮动结果回执卡片：执行完毕或报错时展示，不侵入输入栏 */}
        {hasFeedback && (
          <div className="agent-floating-receipt-card" role="status">
            <div className="agent-floating-receipt-header">
              <span className="agent-floating-receipt-title">
                {error ? "执行异常" : "执行回执"}
              </span>
              <button
                type="button"
                className="agent-floating-receipt-close"
                aria-label="关闭回执"
                onClick={() => {
                  setReceipt(null);
                  setError(null);
                  setOutput(null);
                }}
              >
                ×
              </button>
            </div>
            {error && (
              <p className="error agent-feedback" role="alert">
                {error}
              </p>
            )}
            {receipt && <AgentChangeReceipt receipt={receipt} />}
            {output && (
              <section className="agent-output" aria-label="技术输出">
                <h3>技术输出</h3>
                <pre>{output}</pre>
              </section>
            )}
          </div>
        )}

        {/* 快捷指令浮动菜单（点击左侧 + 展开） */}
        {showMenu && (
          <div className="agent-plus-menu" role="menu">
            <div className="agent-plus-menu-header">快捷指令</div>
            <button
              type="button"
              className="agent-plus-menu-item"
              onClick={() => {
                setPrompt("根据当前目标安排今日重点事项与执行次序");
                setShowMenu(false);
                promptRef.current?.focus();
              }}
            >
              ✨ 安排今日要事
            </button>
            <button
              type="button"
              className="agent-plus-menu-item"
              onClick={() => {
                setPrompt("把昨天未完成的事项梳理并移入 To Do 待办");
                setShowMenu(false);
                promptRef.current?.focus();
              }}
            >
              ✨ 整理待办库存
            </button>
            <button
              type="button"
              className="agent-plus-menu-item"
              onClick={() => {
                setPrompt("合理规划下午与晚上的时间安排，留出休息时间");
                setShowMenu(false);
                promptRef.current?.focus();
              }}
            >
              ✨ 优化时间节奏
            </button>
            {selected && (
              <div className="agent-plus-menu-footer">
                <button
                  type="button"
                  className="agent-plus-menu-delete"
                  onClick={() => {
                    setShowMenu(false);
                    void onDelete();
                  }}
                  disabled={busy}
                >
                  删除此模型
                </button>
              </div>
            )}
          </div>
        )}

        {/* 底部极简药丸输入框 (ChatGPT 同款) */}
        <form
          className={`agent-pill-bar ${isMultiline ? "is-multiline" : ""}`}
          onSubmit={onSend}
        >
          {/* 左侧 + 按钮 */}
          <button
            type="button"
            className={`agent-pill-btn-plus ${showMenu ? "is-active" : ""}`}
            title="快捷指令与模型设置"
            aria-label="快捷指令与模型设置"
            onClick={() => setShowMenu((prev) => !prev)}
          >
            +
          </button>

          {/* 中间输入框：自适应多行输入，Enter 发送，Shift+Enter 换行 */}
          <textarea
            ref={promptRef}
            id="agent-prompt"
            rows={1}
            className="agent-pill-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handlePromptKeyDown}
            onFocus={() => {
              onOpen?.();
            }}
            placeholder="问问计划助手..."
            disabled={busy || items.length === 0}
            autoComplete="off"
          />

          {/* 右侧：模型选择器 (“极高 ∨” 样式) */}
          <div className="agent-pill-model-btn" title="选择模型">
            <span className="agent-pill-model-name">
              {currentLauncher?.name || "默认模型"}
            </span>
            <span className="agent-pill-model-chevron" aria-hidden="true">
              ∨
            </span>
            <select
              id="agent-launcher"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
              aria-label="Agent group"
              className="agent-pill-select-native"
              disabled={busy || items.length === 0}
            >
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

          {/* 最右侧：发送按钮（蓝色圆形高亮） */}
          <button
            type="submit"
            className="agent-pill-btn-send"
            title="发送指令 (Enter 发送，Shift+Enter 换行)"
            aria-label="发送指令"
            disabled={busy || !selected || !prompt.trim()}
          >
            {busy ? (
              <span className="agent-pill-spinner" />
            ) : (
              <span className="agent-pill-send-icon">↑</span>
            )}
          </button>
        </form>
      </div>
    </aside>,
    document.body,
  );
}

function AgentChangeReceipt({
  receipt,
}: {
  receipt: NonNullable<RunResponse["receipt"]>;
}) {
  const changes = receipt.changes ?? [];
  const labels: Record<string, string> = {
    recurrence_created: "新增定期事项",
    recurrence_updated: "更新定期事项",
    recurrence_paused: "暂停定期事项",
    recurrence_resumed: "恢复定期事项",
    recurrence_stopped: "停止定期事项",
    recurrence_deleted: "删除定期事项",
    plan_added: "新增 Plan",
    errand_added: "新增 Errand",
    todo_added: "新增 To Do",
    todo_to_today: "从 To Do 加入今天",
    todo_scheduled: "排入计划",
    moved_to_todo: "移回 To Do",
    rescheduled: "改排",
    completed: "完成",
    completion_undone: "取消完成",
    renamed: "更新标题",
    clock_changed: "更新时间",
    target_date_changed: "更新目标日",
    deleted: "删除",
  };
  return (
    <section className="agent-receipt" aria-live="polite" aria-labelledby="agent-receipt-title">
      <h3 id="agent-receipt-title">本次已更新你的计划</h3>
      {receipt.summary ? <p>{receipt.summary}</p> : null}
      {changes.length === 0 && !receipt.summary ? <p>计划已刷新。</p> : null}
      {changes.length > 0 ? (
        <ul>
          {changes.map((change, index) => {
            const names = change.items?.filter(Boolean) ?? [];
            const count = change.count ?? names.length;
            const label = change.label ?? labels[change.type ?? ""] ?? "计划改动";
            return (
              <li key={`${change.type ?? change.label ?? "改动"}-${change.id ?? index}`}>
                {label}
                {count > 0 ? `（${count}）` : ""}
                {change.title
                  ? `：${change.title}`
                  : names.length > 0
                    ? `：${names.join("、")}`
                    : ""}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
