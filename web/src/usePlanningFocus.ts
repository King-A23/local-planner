import { useEffect, useState } from "react";
import { normalizeFocusedIds } from "./planningView";
import "./desktop";

const KEY = "planner_planning_focus";
const EVENT = "planner:planning-focus-changed";

function read() {
  if (window.__PLANNER_DESKTOP_WINDOW__) return normalizeFocusedIds(window.__PLANNER_DESKTOP_PLANNING_FOCUS__);
  try { return normalizeFocusedIds(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch { return []; }
}

export function usePlanningFocus() {
  const [ids, setIds] = useState(read);
  useEffect(() => {
    const changed = (event: Event) => {
      const next = normalizeFocusedIds((event as CustomEvent).detail);
      if (window.__PLANNER_DESKTOP_WINDOW__) window.__PLANNER_DESKTOP_PLANNING_FOCUS__ = next;
      setIds(next);
    };
    const storage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) setIds(read()); };
    window.addEventListener(EVENT, changed);
    window.addEventListener("storage", storage);
    if (window.__PLANNER_DESKTOP_WINDOW__)
      window.webkit?.messageHandlers?.plannerDesktop?.postMessage({ action: "getPlanningFocus" });
    return () => {
      window.removeEventListener(EVENT, changed);
      window.removeEventListener("storage", storage);
    };
  }, []);
  function choose(value: string[]) {
    const next = normalizeFocusedIds(value);
    if (window.__PLANNER_DESKTOP_WINDOW__) {
      window.__PLANNER_DESKTOP_PLANNING_FOCUS__ = next;
      window.webkit?.messageHandlers?.plannerDesktop?.postMessage({ action: "setPlanningFocus", goalIds: next });
    } else {
      try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* optional view preference */ }
    }
    window.dispatchEvent(new CustomEvent(EVENT, { detail: next }));
  }
  return { ids, choose };
}
