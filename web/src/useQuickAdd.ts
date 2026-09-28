import { useEffect, useRef } from "react";

export function useQuickAdd(enabled: boolean) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!enabled) return;
    function focus() {
      if (document.querySelector("dialog[open]")) return;
      inputRef.current?.focus();
      inputRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n" && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("planner:quick-add", focus);
    if (new URLSearchParams(window.location.search).has("add")) {
      focus();
      window.history.replaceState(null, "", window.location.pathname);
    }
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("planner:quick-add", focus);
    };
  }, [enabled]);
  return inputRef;
}
