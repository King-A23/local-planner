export function ClockSummary({ start, end }: { start: string | null; end: string | null }) {
  if (!start && !end) return null;
  return <span className="task-clock-summary">{start && end ? `${start}–${end}` : start ? `${start} 开始` : `${end} 前`}</span>;
}
