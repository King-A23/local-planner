import { useEffect, useRef, useState } from "react";
import { errorMessage, searchItems, type SearchItem } from "./api";
import { ComposerKeyboard } from "./composerKeyboard";
import { Modal } from "./Modal";
import { navigate } from "./route";

export function SearchDialog({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [today, setToday] = useState("");
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const keyboard = useRef(new ComposerKeyboard());
  useEffect(() => {
    const abort = new AbortController();
    setResults([]); setSelected(0); setError(null); setTotal(0);
    if (!query.trim()) { setLoading(false); return; }
    setLoading(true);
    const timer = window.setTimeout(() => {
      searchItems(query.trim(), abort.signal).then((data) => {
        if (abort.signal.aborted) return;
        setResults(data.items); setTotal(data.total); setToday(data.today);
      }).catch((err) => { if (!abort.signal.aborted) setError(errorMessage(err)); })
        .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    }, 140);
    return () => { abort.abort(); window.clearTimeout(timer); };
  }, [query]);
  useEffect(() => {
    document.getElementById(`search-result-${selected}`)?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  function choose(item: SearchItem) {
    onClose();
    navigate(`${item.date ? `/d/${item.date}` : "/inventory"}?focus=${encodeURIComponent(item.id)}`);
  }
  return <Modal label="搜索事项" onClose={onClose} className="search-dialog">
    <div className="search-input-row">
      <SearchIcon />
      <input autoFocus aria-label="搜索未完成的事项" role="combobox" aria-autocomplete="list"
        aria-expanded={results.length > 0} aria-controls="search-results"
        aria-activedescendant={results[selected] ? `search-result-${selected}` : undefined}
        placeholder="搜索事项或备注…" value={query} maxLength={200}
        onChange={(e) => { setQuery(e.target.value); setResults([]); }}
        onCompositionStart={() => keyboard.current.compositionStart()}
        onCompositionEnd={() => keyboard.current.compositionEnd(performance.now())}
        onKeyUp={(e) => keyboard.current.keyUp(e.key)}
        onKeyDown={(event) => {
          const action = keyboard.current.keyDown(event.nativeEvent, "enter", performance.now());
          if (action === "ime") { event.stopPropagation(); return; }
          if (action === "suppress") { event.preventDefault(); return; }
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setSelected((i) => Math.max(0, Math.min(results.length - 1, i + (event.key === "ArrowDown" ? 1 : -1))));
          } else if (action === "send") { event.preventDefault(); if (results[selected]) choose(results[selected]); }
        }} />
      <button type="button" className="icon-button" aria-label="关闭搜索" onClick={onClose}>×</button>
    </div>
    <div className="search-results" id="search-results" role="listbox" aria-label="搜索结果">
      {results.map((item, index) => <div key={`${item.kind}-${item.id}`} id={`search-result-${index}`} role="option"
        aria-selected={index === selected} className="search-result" onMouseMove={() => setSelected(index)}
        onMouseDown={(event) => event.preventDefault()} onClick={() => choose(item)}>
        <div className="search-result-copy"><span>{item.title}</span>{item.notes.trim() && <small>{item.notes}</small>}</div>
        <span className="search-location">{item.date ? `${item.date === today ? "今天" : item.date}${item.kind === "errand" ? " · 零碎" : ""}` : "待办"}</span>
      </div>)}
    </div>
    <p className="search-status" role="status">{error || (loading ? "搜索中…" : !query.trim() ? "查找待办、今天和未来已创建的未完成事项" : !results.length ? "没有找到相关事项" : total > 50 ? `显示前 50 项，共 ${total} 项，请缩小搜索范围` : `${total} 项结果`)}</p>
  </Modal>;
}
export function SearchIcon() {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" strokeLinecap="round" /></svg>;
}
