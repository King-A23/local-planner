import { useState, type ReactNode } from "react";

import { SearchIcon } from "./SearchDialog";
import { MonthCalendar } from "./Calendar";
import { DISPLAY_NAME } from "./constants";
import { handleNavClick } from "./route";

type ShellProps = {
  children: ReactNode;
  inventoryCount?: number;
  today?: string;
  viewedDate?: string;
  activeSection?: "today" | "inventory" | "recurrences" | "goals" | "settings";
  onSearch: () => void;
  agentOpen: boolean;
  agentStatus?: string | null;
  onOpenAgent: (trigger: HTMLButtonElement) => void;
};

export function Shell({
  children,
  inventoryCount,
  today,
  viewedDate,
  activeSection,
  agentOpen,
  agentStatus,
  onOpenAgent,
  onSearch,
}: ShellProps) {
  const [calOpen, setCalOpen] = useState(false);

  return (
    <div className="app">
      <header className="shell">
        <a className="brand" href="/" onClick={(e) => handleNavClick(e, "/")}>
          {DISPLAY_NAME}
        </a>
        <nav className="nav">
          <a
            href="/"
            aria-current={activeSection === "today" ? "page" : undefined}
            onClick={(e) => handleNavClick(e, "/")}
          >
            今天
          </a>
          <a
            href="/inventory"
            aria-current={activeSection === "inventory" ? "page" : undefined}
            onClick={(e) => handleNavClick(e, "/inventory")}
          >
            待办
            {inventoryCount ? (
              <span className="badge count">{inventoryCount}</span>
            ) : null}
          </a>
          <a
            href="/recurrences"
            aria-current={activeSection === "recurrences" ? "page" : undefined}
            onClick={(e) => handleNavClick(e, "/recurrences")}
          >
            定期事项
          </a>
          <a
            href="/goals"
            aria-current={activeSection === "goals" ? "page" : undefined}
            onClick={(e) => handleNavClick(e, "/goals")}
          >
            规划
          </a>
          {(activeSection !== "goals" || agentOpen || agentStatus) && <button
            type="button"
            className={`nav-agent ${agentOpen ? "active" : ""}`}
            aria-expanded={agentOpen}
            aria-controls="agent-panel"
            title={agentOpen ? "收起计划助手（Esc）；聚焦：⌘ / Ctrl + Shift + L" : "打开计划助手（⌘ / Ctrl + Shift + L）"}
            onClick={(event) => onOpenAgent(event.currentTarget)}
          >
            <span className="agent-nav-sparkle">✨</span>
            <span className="agent-label-long">{agentStatus === "paused" ? "助手已暂停" : agentStatus ? "助手执行中" : "计划助手"}</span>
            <span className="agent-label-short">助手</span>
          </button>}
          <button
            type="button"
            className="nav-cal"
            aria-expanded={calOpen}
            aria-haspopup="dialog"
            disabled={!today}
            onClick={() => setCalOpen((open) => !open)}
          >
            日历
          </button>
          <button type="button" className="nav-search" aria-label="搜索事项" title="搜索（⌘ / Ctrl + K）" onClick={onSearch}><SearchIcon /></button>
          <a href="/settings" aria-current={activeSection === "settings" ? "page" : undefined} onClick={(e) => handleNavClick(e, "/settings")}>设置</a>
          {calOpen && today ? (
            <MonthCalendar
              today={today}
              viewedDate={viewedDate}
              onClose={() => setCalOpen(false)}
            />
          ) : null}
        </nav>
      </header>
      {children}
    </div>
  );
}
