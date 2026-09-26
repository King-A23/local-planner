import { useEffect, useState } from "react";

type ClockFieldProps = {
  label: string;
  value: string | null;
  disabled?: boolean;
  onChange: (next: string | null) => void;
};

const CLOCK = /^(\d{1,2})(?::([0-5]\d))?$/;

function normalizeClock(raw: string): string | null {
  const match = CLOCK.exec(raw.trim());
  if (!match) {
    return null;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2] ?? "0");
  if (hour > 23 || minute % 5 !== 0) {
    return null;
  }
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function ClockField({
  label,
  value,
  disabled,
  onChange,
}: ClockFieldProps) {
  const [draft, setDraft] = useState(value ?? "");

  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  function commitText(raw: string): void {
    const trimmed = raw.trim();
    if (trimmed === "") {
      setDraft("");
      if (value !== null) {
        onChange(null);
      }
      return;
    }
    const normalized = normalizeClock(trimmed);
    if (normalized === null) {
      setDraft(value ?? "");
      return;
    }
    setDraft(normalized);
    if (normalized !== value) {
      onChange(normalized);
    }
  }

  return (
    <span className="clock-field">
      <input
        type="text"
        inputMode="numeric"
        className="clock-text"
        placeholder={label}
        disabled={disabled}
        value={draft}
        aria-label={label}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => commitText(draft)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            (event.target as HTMLInputElement).blur();
          }
        }}
      />
    </span>
  );
}
