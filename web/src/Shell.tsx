import { useState, type ReactNode } from "react";

import { MonthCalendar } from "./Calendar";
import { DISPLAY_NAME } from "./constants";
import { handleNavClick } from "./route";

type ShellProps = {
  children: ReactNode;
  inventoryCount?: number;
  today?: string;
  viewedDate?: string;
};

export function Shell({
  children,
  inventoryCount,
  today,
  viewedDate,
}: ShellProps) {
  const [calOpen, setCalOpen] = useState(false);

  return (
    <div className="app">
      <header className="shell">
        <a className="brand" href="/" onClick={(e) => handleNavClick(e, "/")}>
          {DISPLAY_NAME}
        </a>
        <nav className="nav">
          <a href="/" onClick={(e) => handleNavClick(e, "/")}>
            今天
          </a>
          <a href="/inventory" onClick={(e) => handleNavClick(e, "/inventory")}>
            库存
            {inventoryCount ? (
              <span className="badge count">{inventoryCount}</span>
            ) : null}
          </a>
          <button
            type="button"
            className="nav-cal"
            aria-expanded={calOpen}
            aria-haspopup="dialog"
            disabled={!today}
            onClick={() => setCalOpen((open) => !open)}
          >
            日期
          </button>
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
