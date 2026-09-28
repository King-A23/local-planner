import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { DISPLAY_NAME } from "./constants";
import { closeDesktopSettings, isSettingsWindow } from "./desktop";
import { SettingsPage } from "./SettingsPage";
import "./styles.css";

document.title = isSettingsWindow ? `设置 · ${DISPLAY_NAME}` : DISPLAY_NAME;
function applyTheme(selected: string | null) {
  document.documentElement.setAttribute("data-theme", selected && ["warm-paper", "midnight", "nordic", "forest", "retro"].includes(selected) ? selected : "warm-paper");
}
try {
  const selected = new URLSearchParams(window.location.search).get("theme") ?? localStorage.getItem("planner_theme");
  applyTheme(selected);
} catch { applyTheme(null); }
window.addEventListener("storage", (event) => { if (event.key === "planner_theme") applyTheme(event.newValue); });
window.addEventListener("planner:theme-changed", (event) => applyTheme((event as CustomEvent<string>).detail));

const root = document.getElementById("root");
if (!root) {
  throw new Error("missing #root");
}

createRoot(root).render(
  <StrictMode>
    {isSettingsWindow
      ? <div className="settings-window"><SettingsPage onClose={closeDesktopSettings} /></div>
      : <App />}
  </StrictMode>,
);
