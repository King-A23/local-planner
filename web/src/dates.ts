/** Civil YYYY-MM-DD helpers. Never parse calendar dates as UTC midnight Date values. */

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const WEEKDAYS = [
  "星期日",
  "星期一",
  "星期二",
  "星期三",
  "星期四",
  "星期五",
  "星期六",
];

function isLeap(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    return isLeap(year) ? 29 : 28;
  }
  return [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month] ?? 0;
}

export function isCivilDate(value: string): boolean {
  const match = DATE_RE.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1) {
    return false;
  }
  return day <= daysInMonth(year, month);
}

/** Sakamoto weekday: 0 = Sunday. Pure civil arithmetic, no Date. */
function weekdaySun0(year: number, month: number, day: number): number {
  const t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
  const y = month < 3 ? year - 1 : year;
  return (
    (y +
      Math.floor(y / 4) -
      Math.floor(y / 100) +
      Math.floor(y / 400) +
      t[month - 1] +
      day) %
    7
  );
}

export type CivilParts = {
  year: number;
  month: number;
  day: number;
};

export function parseCivil(iso: string): CivilParts | null {
  const match = DATE_RE.exec(iso);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)) {
    return null;
  }
  return { year, month, day };
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function formatCivil(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, "0")}-${pad2(month)}-${pad2(day)}`;
}

/** Civil-day ±n via Y-M-D parts. Never string-slice the day field. */
export function addCivilDays(iso: string, delta: number): string {
  const parts = parseCivil(iso);
  if (!parts) {
    return iso;
  }
  let { year, month, day } = parts;
  const step = delta >= 0 ? 1 : -1;
  let left = Math.abs(delta);
  while (left > 0) {
    day += step;
    if (day < 1) {
      month -= 1;
      if (month < 1) {
        month = 12;
        year -= 1;
      }
      day = daysInMonth(year, month);
    } else {
      const dim = daysInMonth(year, month);
      if (day > dim) {
        day = 1;
        month += 1;
        if (month > 12) {
          month = 1;
          year += 1;
        }
      }
    }
    left -= 1;
  }
  return formatCivil(year, month, day);
}

export function addCivilMonths(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const idx = year * 12 + (month - 1) + delta;
  const nextYear = Math.floor(idx / 12);
  return { year: nextYear, month: idx - nextYear * 12 + 1 };
}

export const WEEKDAY_LABELS_MON_FIRST = ["一", "二", "三", "四", "五", "六", "日"];

/** Monday-first 6×7 grid. Adjacent-month cells included so dots can render. */
export function monthGrid(year: number, month: number): string[] {
  const first = formatCivil(year, month, 1);
  const sun0 = weekdaySun0(year, month, 1);
  const monday0 = (sun0 + 6) % 7;
  const cells: string[] = [];
  let cursor = addCivilDays(first, -monday0);
  for (let i = 0; i < 42; i += 1) {
    cells.push(cursor);
    cursor = addCivilDays(cursor, 1);
  }
  return cells;
}

export function formatDayHeading(iso: string): string {
  const parts = parseCivil(iso);
  if (!parts) {
    return iso;
  }
  const { year, month, day } = parts;
  return `${year}年${month}月${day}日 ${WEEKDAYS[weekdaySun0(year, month, day)]}`;
}
