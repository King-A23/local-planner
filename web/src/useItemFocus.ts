import { useEffect } from "react";

export function useItemFocus(ready: boolean, version: unknown) {
  useEffect(() => {
    if (!ready) return;
    let timer: number | undefined;
    let frame: number | undefined;
    let highlighted: HTMLElement | null = null;
    function scheduleReveal() {
      window.cancelAnimationFrame(frame ?? 0);
      // Wait for navigation and dialog teardown so the destination is no longer inert.
      frame = window.requestAnimationFrame(() => {
        const id = new URLSearchParams(window.location.search).get("focus");
        if (!id) return;
        const row = document.querySelector<HTMLElement>(`[data-item-id="${CSS.escape(id)}"]`);
        if (!row) return;
        row.scrollIntoView({ block: "center", behavior: "smooth" });
        row.querySelector<HTMLButtonElement>("button.title")?.focus({ preventScroll: true });
        highlighted = row;
        row.dataset.revealed = "true";
        window.clearTimeout(timer);
        timer = window.setTimeout(() => { delete row.dataset.revealed; }, 2200);
        const url = new URL(window.location.href); url.searchParams.delete("focus");
        window.history.replaceState(null, "", url.pathname + url.search + url.hash);
      });
    }
    scheduleReveal();
    window.addEventListener("popstate", scheduleReveal);
    return () => {
      window.clearTimeout(timer); window.cancelAnimationFrame(frame ?? 0);
      if (highlighted) delete highlighted.dataset.revealed;
      window.removeEventListener("popstate", scheduleReveal);
    };
  }, [ready, version]);
}
