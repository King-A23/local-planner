import { useEffect, useState } from "react";
import { parseSendShortcut, type SendShortcut } from "./composerKeyboard";
import { notifySettingsChange } from "./desktop";

const KEY = "planner_send_shortcut";
const EVENT = "planner:shortcuts-changed";
const MODIFIER = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

function read(): SendShortcut {
  try { return parseSendShortcut(localStorage.getItem(KEY)); } catch { return "enter"; }
}
function store(value: SendShortcut) {
  try { localStorage.setItem(KEY, value); } catch { /* Preference still works for this session. */ }
}

export function useSendShortcut() {
  const [shortcut, setShortcut] = useState(read);
  useEffect(() => {
    const changed = (event: Event) => {
      const value = parseSendShortcut((event as CustomEvent).detail);
      store(value); setShortcut(value);
    };
    const refresh = () => setShortcut(read());
    const storage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) refresh(); };
    window.addEventListener(EVENT, changed);
    window.addEventListener("storage", storage);
    window.addEventListener("planner:settings-opened", refresh);
    return () => {
      window.removeEventListener(EVENT, changed);
      window.removeEventListener("storage", storage);
      window.removeEventListener("planner:settings-opened", refresh);
    };
  }, []);
  return {
    shortcut,
    choose: (value: SendShortcut) => { store(value); notifySettingsChange(EVENT, value); },
    modifierLabel: `${MODIFIER} + Enter`,
    sendLabel: shortcut === "enter" ? "Enter" : `${MODIFIER} + Enter`,
    newlineLabel: shortcut === "enter" ? "Shift + Enter" : "Enter",
  };
}
