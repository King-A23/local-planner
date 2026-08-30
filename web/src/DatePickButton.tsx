import { useRef, useState } from "react";

type DatePickButtonProps = {
  label: string;
  min: string;
  max: string;
  onPick: (date: string) => void;
};

/** Native date input, today+future only. Not a modal and not a third product picker. */
export function DatePickButton({
  label,
  min,
  max,
  onPick,
}: DatePickButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [visible, setVisible] = useState(false);

  function openPicker(): void {
    const el = inputRef.current;
    if (!el) {
      return;
    }
    try {
      el.showPicker();
    } catch {
      setVisible(true);
      window.setTimeout(() => el.focus(), 0);
    }
  }

  return (
    <span className="date-pick-wrap">
      <button type="button" className="linkish quiet" onClick={openPicker}>
        {label}
      </button>
      <input
        ref={inputRef}
        type="date"
        min={min}
        max={max}
        aria-label={label}
        className={visible ? "date-pick-input visible" : "date-pick-input"}
        onChange={(event) => {
          const value = event.target.value;
          if (!value || value < min || value > max) {
            return;
          }
          onPick(value);
          event.target.value = "";
          setVisible(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setVisible(false);
            event.currentTarget.value = "";
          }
        }}
      />
    </span>
  );
}
