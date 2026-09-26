import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { DISPLAY_NAME } from "./constants";
import "./styles.css";

document.title = DISPLAY_NAME;
try {
  const selected = new URLSearchParams(window.location.search).get("theme") ?? localStorage.getItem("planner_theme");
  if (selected && ["warm-paper", "midnight", "nordic", "forest", "retro"].includes(selected)) document.documentElement.setAttribute("data-theme", selected);
} catch { /* use default theme when storage is unavailable */ }

const root = document.getElementById("root");
if (!root) {
  throw new Error("missing #root");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
