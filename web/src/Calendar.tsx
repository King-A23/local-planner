import { useEffect, useState } from "react";

import { errorMessage, getCalendar } from "./api";
import {
  addCivilMonths,
  monthGrid,
  parseCivil,
  WEEKDAY_LABELS_MON_FIRST,
} from "./dates";
import { navigate } from "./route";

type MonthCalendarProps = {
  today: string;
  viewedDate?: string;
  onClose: () => void;
};

export function MonthCalendar({
  today,
  viewedDate,
  onClose,
}: MonthCalendarProps) {
  const seed = parseCivil(viewedDate ?? today) ?? parseCivil(today);
  const [year, setYear] = useState(seed?.year ?? 2026);
  const [month, setMonth] = useState(seed?.month ?? 1);
  const [dotted, setDotted] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const cells = monthGrid(year, month);
  const from = cells[0];
  const to = cells[cells.length - 1];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    getCalendar(from, to)
      .then((cal) => {
        if (cancelled) {
          return;
        }
        const next = new Set<string>();
        for (const day of cal.days) {
          if (day.todoCount + day.errandCount > 0) {
            next.add(day.date);
          }
        }
        setDotted(next);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(errorMessage(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [from, to]);

  function shiftMonth(delta: number): void {
    const next = addCivilMonths(year, month, delta);
    setYear(next.year);
    setMonth(next.month);
  }

  function openDay(date: string): void {
    navigate(`/d/${date}`);
    onClose();
  }

  function goToday(): void {
    navigate("/");
    onClose();
  }

  return (
    <>
      <button
        type="button"
        className="calendar-backdrop"
        aria-label="关闭月历"
        onClick={onClose}
      />
      <div className="calendar-popover" role="dialog" aria-label="月历">
        <div className="calendar-head">
          <button
            type="button"
            className="cal-nav"
            aria-label="上个月"
            onClick={() => shiftMonth(-1)}
          >
            ‹
          </button>
          <h2>
            {year}年{month}月
          </h2>
          <button
            type="button"
            className="cal-nav"
            aria-label="下个月"
            onClick={() => shiftMonth(1)}
          >
            ›
          </button>
        </div>
        <button type="button" className="cal-today" onClick={goToday}>
          Today
        </button>
        {error ? <p className="error">{error}</p> : null}
        <div className="cal-weekdays">
          {WEEKDAY_LABELS_MON_FIRST.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
        <div className="cal-grid">
          {cells.map((date) => {
            const parts = parseCivil(date);
            const dayNum = parts?.day ?? 0;
            const outside = parts !== null && parts.month !== month;
            const classes = ["cal-day"];
            if (outside) {
              classes.push("outside");
            }
            if (date === today) {
              classes.push("is-today");
            }
            if (viewedDate && date === viewedDate) {
              classes.push("selected");
            }
            if (dotted.has(date)) {
              classes.push("has-dot");
            }
            return (
              <button
                key={date}
                type="button"
                className={classes.join(" ")}
                onClick={() => openDay(date)}
              >
                <span>{dayNum}</span>
                {dotted.has(date) ? <span className="cal-dot" /> : null}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}
