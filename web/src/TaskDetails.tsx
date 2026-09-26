import { useEffect, useRef, type ReactNode } from "react";

export function TaskDetails({ title, children }: { title: string; children: ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !ref.current?.contains(event.target)) ref.current?.removeAttribute("open");
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  return (
    <details name="task-actions" className="task-details" ref={ref} onKeyDown={(event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        ref.current?.removeAttribute("open");
        ref.current?.querySelector("summary")?.focus();
      }
    }}>
      <summary aria-label={`更多操作：${title}`} title="更多操作">···</summary>
      <div className="task-details-content">{children}</div>
    </details>
  );
}

export function ClockSummary({ start, end }: { start: string | null; end: string | null }) {
  if (!start && !end) return null;
  return <span className="task-clock-summary">{start && end ? `${start}–${end}` : start ? `${start} 开始` : `${end} 前`}</span>;
}
