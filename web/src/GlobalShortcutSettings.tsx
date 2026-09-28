import { useEffect, useState } from "react";

type ShortcutState = { value: string; message: string; active: boolean };
export function GlobalShortcutSettings() {
  const [state, setState] = useState<ShortcutState | null>(null);
  const [pending, setPending] = useState(false);
  const bridge = window.webkit?.messageHandlers?.plannerDesktop;
  useEffect(() => {
    if (!bridge) return;
    const changed = (event: Event) => { setState((event as CustomEvent<ShortcutState>).detail); setPending(false); };
    const refresh = () => bridge.postMessage({ action: "getQuickShortcut" });
    window.addEventListener("planner:quick-shortcut-state", changed);
    window.addEventListener("planner:settings-opened", refresh);
    refresh();
    return () => { window.removeEventListener("planner:quick-shortcut-state", changed); window.removeEventListener("planner:settings-opened", refresh); };
  }, [bridge]);
  if (!bridge) return null;
  return <div className="global-shortcut-setting">
    <div className="settings-actions"><label htmlFor="global-shortcut">全局快速录入</label>
      <select id="global-shortcut" disabled={!state || pending} value={state?.value ?? "ctrl-option-space"} onChange={(event) => {
        setPending(true); bridge.postMessage({ action: "setQuickShortcut", value: event.target.value });
      }}>
        <option value="ctrl-option-space">⌃ ⌥ Space</option>
        <option value="ctrl-shift-space">⌃ ⇧ Space</option>
        <option value="off">关闭</option>
      </select>
    </div>
    <p className="settings-caption">应用运行时，在其他应用中也能唤出。关闭主窗口后仍可使用，⌘ Q 退出。</p>
    {state?.message && <p className="error" role="status">{state.message}</p>}
  </div>;
}
