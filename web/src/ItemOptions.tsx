import { useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";
import { Modal } from "./Modal";

type Values = { date: string; start: string; end: string };
type Options = { title: string; kind: "date" | "target" | "time"; date?: string; start?: string | null; end?: string | null; min?: string; max?: string; save: (values: Values) => Promise<unknown> };

export function useItemOptions() {
  const [options, show] = useState<Options | null>(null);
  return { show, dialog: options ? <ItemOptions options={options} close={() => show(null)} /> : null };
}

function ItemOptions({ options, close }: { options: Options; close: () => void }) {
  const [values, setValues] = useState<Values>({ date: options.date ?? "", start: options.start ?? "", end: options.end ?? "" });
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  const label = options.kind === "time" ? "设置时间" : options.kind === "target" ? "参考日期" : "安排到日期";
  return <Modal label={label} className="item-options" onClose={() => { if (!saving.current) close(); }}>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (saving.current) return;
      saving.current = true; setBusy(true); setError("");
      try {
        await options.save(values);
        window.dispatchEvent(new Event("planner:items-changed")); close();
      } catch (err) { setError(errorMessage(err)); }
      finally { saving.current = false; setBusy(false); }
    }}>
      <h2>{label}</h2><p className="item-options-title">{options.title}</p>
      {options.kind === "time" ? <div className="item-options-times">
        <label>开始<input data-autofocus type="time" step="300" disabled={busy} value={values.start} onInput={(event) => { const start = event.currentTarget.value; setValues((current) => ({ ...current, start })); }} /></label>
        <label>结束<input type="time" step="300" disabled={busy} value={values.end} onInput={(event) => { const end = event.currentTarget.value; setValues((current) => ({ ...current, end })); }} /></label>
      </div> : <label>{options.kind === "target" ? "仅作参考，不会自动排入当天" : "日期"}
        <input data-autofocus type="date" required={options.kind === "date"} min={options.min} max={options.max} disabled={busy}
          value={values.date} onInput={(event) => { const date = event.currentTarget.value; setValues((current) => ({ ...current, date })); }} />
      </label>}
      {error && <p ref={errorRef} tabIndex={-1} role="alert" className="error">{error}</p>}
      <div className="item-options-footer">
        {options.kind !== "date" && <button type="button" className="linkish quiet" disabled={busy} onClick={() => setValues({ date: "", start: "", end: "" })}>清除</button>}
        <button type="button" className="linkish quiet" disabled={busy} onClick={close}>取消</button>
        <button type="submit" className="button-primary" disabled={busy}>{busy ? "保存中…" : "保存"}</button>
      </div>
    </form>
  </Modal>;
}
