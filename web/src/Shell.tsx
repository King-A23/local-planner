import type { ReactNode } from "react";

import { DISPLAY_NAME } from "./constants";
import { handleNavClick } from "./route";

type ShellProps = {
  children: ReactNode;
  inventoryCount?: number;
};

export function Shell({ children, inventoryCount }: ShellProps) {
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
          <span className="nav-stub" title="月历将在后续版本提供">
            日期
          </span>
        </nav>
      </header>
      {children}
    </div>
  );
}
