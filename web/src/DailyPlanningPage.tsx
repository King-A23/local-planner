import { useEffect, useMemo, useState } from "react";

import {
  completeTodayPlanning,
  errorMessage,
  getTodayPlanning,
  scheduleTask,
  type InventoryItem,
  type PlanningUpcoming,
  type TodayPlanning,
} from "./api";
import { formatDayHeading } from "./dates";
import { handleNavClick, navigate } from "./route";

type CandidateGroup = {
  key: string;
  title: string;
  description: string;
  items: InventoryItem[];
};

function candidateGroups(planning: TodayPlanning): CandidateGroup[] {
  return [
    {
      key: "returned",
      title: "昨天未完成",
      description: "继续做还是先放一放，由你决定。",
      items: planning.returnedFromYesterday,
    },
    {
      key: "due",
      title: "到期 / 已过期",
      description: "参考日期已到的待办，需要你选入今天。",
      items: planning.due,
    },
    {
      key: "inventory",
      title: "其他待办",
      description: "挑几件今天想做的事，其余留着以后。",
      items: planning.inventory,
    },
  ];
}

function dueLabel(item: InventoryItem, today: string): string | null {
  if (!item.targetDate) {
    return null;
  }
  if (item.targetDate < today) {
    return `已过期 · ${item.targetDate}`;
  }
  if (item.targetDate === today) {
    return "今天到期";
  }
  return null;
}

function upcomingText(item: PlanningUpcoming): string {
  const parts: string[] = [];
  const scheduled = (item.todoCount ?? 0) + (item.errandCount ?? 0);
  if (scheduled > 0) {
    parts.push(`已排 ${scheduled} 条`);
  }
  if ((item.recurrenceCount ?? 0) > 0) {
    parts.push(`定期 ${item.recurrenceCount} 条`);
  }
  return parts.join(" · ") || "暂无安排";
}

export function DailyPlanningPage({
  onChange,
  onReady,
  onDefer,
  agentOpen,
  onOpenAgent,
  refreshToken,
}: {
  onChange?: () => void;
  onReady: () => void;
  onDefer: () => void;
  agentOpen: boolean;
  onOpenAgent: (trigger: HTMLButtonElement) => void;
  refreshToken?: number;
}) {
  const [planning, setPlanning] = useState<TodayPlanning | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  async function reload(): Promise<void> {
    try {
      const next = await getTodayPlanning();
      setPlanning(next);
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, [refreshToken]);

  useEffect(() => {
    if (planning?.status === "ready") {
      onReady();
      navigate("/");
    }
  }, [onReady, planning?.status]);

  async function addToToday(item: InventoryItem): Promise<void> {
    if (!planning) {
      return;
    }
    setBusyId(item.taskId);
    try {
      await scheduleTask(item.taskId, planning.date);
      await reload();
      onChange?.();
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function markReady(): Promise<void> {
    setFinishing(true);
    try {
      await completeTodayPlanning();
      onChange?.();
      onReady();
      navigate("/");
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setFinishing(false);
    }
  }

  const groups = useMemo(
    () => (planning ? candidateGroups(planning) : []),
    [planning],
  );

  if (loading) {
    return <main className="page"><p>加载中…</p></main>;
  }
  if (!planning) {
    return <main className="page"><p className="error" role="alert">{error ?? "无法打开今日规划"}</p></main>;
  }

  return (
    <>
      <main className="page daily-planning-page">
        <header className="planning-header">
          <div>
            <p className="planning-eyebrow">{formatDayHeading(planning.date)}</p>
            <h1>整理今天</h1>
            <p className="muted">
              挑选几件今天真的承诺要做的事；其他继续留在待办。
            </p>
          </div>
          <button type="button" className="linkish quiet" onClick={onDefer}>
            返回今天
          </button>
        </header>
        {error ? <p className="error" role="alert">{error}</p> : null}

        <section className="planning-section current-plan" aria-labelledby="planning-current">
          <div className="section-heading-row">
            <div>
              <h2 id="planning-current">已经安排的事</h2>
              <p className="muted">定期事项已自动加入，其他事项由你挑选。</p>
            </div>
            <button
              type="button"
              className="button-secondary"
              aria-expanded={agentOpen}
              aria-controls="agent-panel"
              onClick={(event) => onOpenAgent(event.currentTarget)}
            >
              让助手整理
            </button>
          </div>
          <div className="planning-day-columns">
            <PlanSnapshot title="今日计划" items={planning.day.todos} />
            <PlanSnapshot title="零碎事项" items={planning.day.errands} />
          </div>
        </section>

        {groups.filter((group) => group.items.length > 0).map((group) => (
          <CandidateSection
            key={group.key}
            group={group}
            today={planning.date}
            busyId={busyId}
            onAdd={(item) => void addToToday(item)}
          />
        ))}

        <details className="planning-section upcoming-section">
          <summary>看看接下来一周</summary>
          <p className="muted">这是查看，不会自动排程。</p>
          {planning.upcoming.length > 0 ? (
            <ul className="upcoming-list">
              {planning.upcoming.map((item) => (
                <li key={item.date}>
                  <span>{item.date}</span>
                  <span className="muted">{upcomingText(item)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">未来 7 天暂无已排或定期事项。</p>
          )}
        </details>
        <footer className="planning-footer">
          <button
            type="button"
            className="button-primary planning-ready"
            disabled={finishing}
            onClick={() => void markReady()}
          >
            {finishing ? "正在确认…" : "就这样，开始今天"}
          </button>
        </footer>
      </main>
    </>
  );
}

function PlanSnapshot({
  title,
  items,
}: {
  title: string;
  items: Array<{
    taskId?: string;
    id?: string;
    title: string;
    completedOnDay?: boolean;
    status?: "open" | "completed" | "expired";
    recurrence?: { label: string } | null;
  }>;
}) {
  return (
    <section className="planning-snapshot">
      <h3>{title}</h3>
      {items.length === 0 ? <p className="muted">还没有事项</p> : null}
      {items.length > 0 ? (
        <ul className="snapshot-list">
          {items.map((item, index) => {
            const done = item.completedOnDay ?? item.status === "completed";
            const expired = item.status === "expired";
            return (
              <li
                key={item.taskId ?? item.id ?? `${item.title}-${index}`}
                className={done ? "done" : expired ? "expired" : ""}
              >
                <span aria-hidden="true">{done ? "☑" : expired ? "—" : "☐"}</span>
                <span>{item.title}</span>
                {item.recurrence ? (
                  <span className="badge">
                    {item.recurrence.label === "固定周期"
                      ? "定期"
                      : `定期 · ${item.recurrence.label}`}
                  </span>
                ) : null}
                {expired ? <span className="badge">已作废</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

function CandidateSection({
  group,
  today,
  busyId,
  onAdd,
}: {
  group: CandidateGroup;
  today: string;
  busyId: string | null;
  onAdd: (item: InventoryItem) => void;
}) {
  return (
    <section className="planning-section candidate-section" aria-labelledby={`planning-${group.key}`}>
      <h2 id={`planning-${group.key}`}>{group.title}</h2>
      <p className="muted">{group.description}</p>
      {group.items.length === 0 ? <p className="muted">没有事项。</p> : null}
      {group.items.length > 0 ? (
        <ul className="planning-candidates">
          {group.items.map((item) => (
            <li key={item.taskId}>
              <span className="candidate-title">
                {item.title}
                {dueLabel(item, today) ? <span className="badge">{dueLabel(item, today)}</span> : null}
                {item.recurrence ? <span className="badge">来自定期事项</span> : null}
              </span>
              <button
                type="button"
                className="button-secondary"
                disabled={busyId !== null}
                onClick={() => onAdd(item)}
              >
                {busyId === item.taskId ? "加入中…" : "加入今天"}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {group.key === "inventory" ? (
        <a href="/inventory" className="open-inventory" onClick={(event) => handleNavClick(event, "/inventory")}>
          打开待办 →
        </a>
      ) : null}
    </section>
  );
}
