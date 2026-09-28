import { useEffect, useRef, useState } from "react";
import { ApiError, editItemDetails, errorMessage } from "./api";
import { ComposerKeyboard } from "./composerKeyboard";
import { Modal } from "./Modal";

export type EditableItem = { id: string; kind: "task" | "errand"; title: string; notes: string; writable: boolean };
export function openItemEditor(item: EditableItem) {
  window.dispatchEvent(new CustomEvent("planner:edit-item", { detail: item }));
}
export function ItemEditorHost() {
  const [item, setItem] = useState<EditableItem | null>(null);
  useEffect(() => {
    const open = (event: Event) => setItem((event as CustomEvent<EditableItem>).detail);
    window.addEventListener("planner:edit-item", open);
    return () => window.removeEventListener("planner:edit-item", open);
  }, []);
  return item ? <ItemEditor key={`${item.kind}-${item.id}`} item={item} onClose={() => setItem(null)} /> : null;
}
function ItemEditor({ item, onClose }: { item: EditableItem; onClose: () => void }) {
  const [title, setTitle] = useState(item.title);
  const [notes, setNotes] = useState(item.notes);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const busy = useRef(false);
  const keyboard = useRef(new ComposerKeyboard());
  const notesRef = useRef<HTMLTextAreaElement>(null);
  const dirty = title.trim() !== item.title || notes !== item.notes;
  function close() {
    if (busy.current) return;
    if (dirty && item.writable) setDiscarding(true); else onClose();
  }
  async function save() {
    if (busy.current || !title.trim() || !item.writable) return;
    if (!dirty) { onClose(); return; }
    busy.current = true; setSaving(true); setError(null);
    try {
      await editItemDetails(item, title, notes);
      window.dispatchEvent(new Event("planner:items-changed"));
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      if (err instanceof ApiError && ["Conflict", "DaySealed", "NotFound"].includes(err.error)) {
        window.dispatchEvent(new Event("planner:items-changed"));
      }
    }
    finally { busy.current = false; setSaving(false); }
  }
  return <Modal label={item.writable ? "编辑事项" : "事项记录"} onClose={close} className="item-editor">
    <div className="modal-heading"><span>{item.writable ? "事项详情" : "过去的记录"}</span>
      <button type="button" className="icon-button" aria-label="关闭详情" disabled={saving} onClick={close}>×</button></div>
    <form onSubmit={(e) => e.preventDefault()}
      onCompositionStart={() => keyboard.current.compositionStart()}
      onCompositionEnd={() => keyboard.current.compositionEnd(performance.now())}
      onKeyUp={(event) => keyboard.current.keyUp(event.key)}
      onKeyDown={(event) => {
        const action = keyboard.current.keyDown(event.nativeEvent, "mod-enter", performance.now());
        if (action === "ime") { event.stopPropagation(); return; }
        if (action === "suppress") { event.preventDefault(); event.stopPropagation(); return; }
        if (action === "send") { event.preventDefault(); void save(); }
        else if (event.key === "Enter" && event.target instanceof HTMLInputElement) { event.preventDefault(); notesRef.current?.focus(); }
      }}>
      <input className="editor-title" aria-label="事项标题" value={title} data-autofocus maxLength={200}
        readOnly={!item.writable} disabled={saving} onChange={(e) => { setTitle(e.target.value); setDiscarding(false); }} />
      <textarea ref={notesRef} className="editor-notes" aria-label="事项备注" value={notes} maxLength={10000}
        placeholder={item.writable ? "添加备注…" : "没有备注"} readOnly={!item.writable} disabled={saving}
        onChange={(e) => { setNotes(e.target.value); setDiscarding(false); }} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="modal-footer">
        {discarding ? <><span className="muted">有未保存的修改</span><button type="button" className="linkish" onClick={onClose}>放弃修改</button></> : <span />}
        {item.writable ? <button type="button" className="button-primary" disabled={!title.trim() || saving}
          title="保存（⌘ / Ctrl + Enter）" onClick={() => void save()}>{saving ? "保存中…" : "保存"}</button>
          : <button type="button" onClick={onClose}>完成</button>}
      </div>
    </form>
  </Modal>;
}

export function NotesMark({ notes }: { notes: string }) {
  return notes.trim() ? <svg className="notes-mark" viewBox="0 0 16 16" width="14" height="14" aria-label="有备注" role="img">
    <path d="M3 2.5h10v11H3zM5.5 6h5M5.5 9h3" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
  </svg> : null;
}
