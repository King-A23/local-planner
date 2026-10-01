import { useEffect, useState } from "react";
import { notifySettingsChange } from "./desktop";

const KEY = "planner_assistant_process";
const EVENT = "planner:assistant-preferences-changed";

function read(): boolean {
  if (window.__PLANNER_DESKTOP_WINDOW__) return window.__PLANNER_DESKTOP_ASSISTANT_PROCESS__ === true;
  try { return localStorage.getItem(KEY) === "true"; } catch { return false; }
}
function store(value: boolean) {
  if (window.__PLANNER_DESKTOP_WINDOW__) window.__PLANNER_DESKTOP_ASSISTANT_PROCESS__ = value;
  try { localStorage.setItem(KEY, String(value)); } catch { /* optional preference */ }
}

export function useAssistantPreferences() {
  const [showProcess, setShowProcess] = useState(read);
  useEffect(() => {
    const changed = (event: Event) => {
      const value = (event as CustomEvent).detail === "true";
      store(value); setShowProcess(value);
    };
    const refresh = () => {
      setShowProcess(read());
      if (window.__PLANNER_DESKTOP_WINDOW__)
        window.webkit?.messageHandlers?.plannerDesktop?.postMessage({ action: "getAssistantPreferences" });
    };
    window.addEventListener(EVENT, changed);
    window.addEventListener("storage", refresh);
    window.addEventListener("planner:settings-opened", refresh);
    refresh();
    return () => {
      window.removeEventListener(EVENT, changed);
      window.removeEventListener("storage", refresh);
      window.removeEventListener("planner:settings-opened", refresh);
    };
  }, []);
  return { showProcess, choose: (value: boolean) => { store(value); notifySettingsChange(EVENT, String(value)); } };
}
