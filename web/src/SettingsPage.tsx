import { useEffect, useRef, useState } from "react";
import { errorMessage, type Backup, type Launcher, type LauncherCheck, settingsRequest } from "./api";
import { ThemeSwitcher } from "./ThemeSwitcher";
import { HelpAndAbout } from "./HelpAndAbout";
import { notifySettingsChange } from "./desktop";
import { navigate } from "./route";
import { parseSendShortcut } from "./composerKeyboard";
import { useSendShortcut } from "./useSendShortcut";

const BACKUP_LABELS: Record<string, string> = { auto: "自动备份", manual: "手动备份", "before-restore": "恢复前备份", imported: "导入的备份", migration: "升级前备份" };

export function SettingsPage({ onClose }: { onClose?: () => void }) {
  const { shortcut, choose: chooseShortcut, modifierLabel, newlineLabel } = useSendShortcut();
  const [backups, setBackups] = useState<Backup[]>([]);
  const [items, setItems] = useState<Launcher[]>([]);
  const [selected, setSelected] = useState("");
  const [checks, setChecks] = useState<Record<string, LauncherCheck>>({});
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<Backup | null>(null);
  const [editor, setEditor] = useState<{ id?: string; name: string; command: string } | null>(null);
  const [removing, setRemoving] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const restoreRef = useRef<HTMLDivElement>(null);
  const actionRef = useRef(false);
  const checkRef = useRef(false);
  const selectedItem = items.find((item) => item.id === selected);

  async function refresh(preferSaved = false) {
    const [backupData, launcherData] = await Promise.all([
      settingsRequest<{ items: Backup[] }>("/api/backups"), settingsRequest<{ items: Launcher[] }>("/api/launchers"),
    ]);
    setBackups(backupData.items); setItems(launcherData.items); setLoaded(true);
    let saved = "";
    try { saved = localStorage.getItem("planner_agent_launcher") ?? ""; } catch { /* optional preference */ }
    setSelected((current) => {
      const choice = preferSaved ? saved : current || saved;
      return launcherData.items.some((item) => item.id === choice) ? choice : launcherData.items[0]?.id ?? "";
    });
  }
  useEffect(() => {
    const opened = () => { void refresh(true).catch((err) => setError(errorMessage(err))); };
    opened();
    window.addEventListener("planner:settings-opened", opened);
    return () => window.removeEventListener("planner:settings-opened", opened);
  }, []);
  useEffect(() => { setEditor(null); setRemoving(false); }, [selected]);
  useEffect(() => { if (restoreTarget) restoreRef.current?.focus(); }, [restoreTarget]);
  async function perform(work: () => Promise<void>) {
    if (actionRef.current) return;
    actionRef.current = true; setBusy(true); setError(null); setNotice(null);
    try { await work(); } catch (err) { setError(errorMessage(err)); }
    finally { actionRef.current = false; setBusy(false); }
  }
  async function check() {
    if (!selected || checkRef.current) return;
    checkRef.current = true; setChecking(true); setError(null);
    const id = selected;
    try { const result = await settingsRequest<LauncherCheck>(`/api/launchers/${id}/check`, "POST"); setChecks((all) => ({ ...all, [id]: result })); }
    catch (err) { setError(errorMessage(err)); }
    finally { checkRef.current = false; setChecking(false); }
  }
  function choose(id: string) {
    setSelected(id);
    try { localStorage.setItem("planner_agent_launcher", id); } catch { /* optional preference */ }
    notifySettingsChange("planner:launchers-changed", id);
  }
  function importFile(file: File) {
    void perform(async () => {
      if (file.size > 32 * 1024 * 1024) throw new Error("备份文件不能超过 32 MB");
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(new Error("无法读取所选文件"));
        reader.readAsDataURL(file);
      });
      const backup = await settingsRequest<Backup>("/api/backups/import", "POST", { content });
      await refresh(); setHistoryOpen(true); setRestoreTarget(backup);
      setNotice("备份已检查，可以确认恢复。当前数据尚未改变。");
    });
  }

  return <main className="page settings-page">
    <div className="settings-heading"><div><h1>设置</h1><p className="muted">按你的习惯，安心使用。</p></div>
      <button type="button" className="linkish" onClick={onClose ?? (() => navigate("/"))}>{onClose ? "完成" : "返回今天"}</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p className="settings-notice" role="status">{notice}</p>}
    {!loaded && <p role="status">{error ? <button onClick={() => void perform(refresh)}>重新加载</button> : "正在加载…"}</p>}

    <section className="settings-section" aria-labelledby="data-title">
      <h2 id="data-title">数据与备份</h2>
      <p className="muted">数据保存在这台 Mac。每天首次使用时自动备份，保留最近 14 份。</p>
      <div className="settings-actions">
        <button type="button" disabled={busy || !loaded} onClick={() => void perform(async () => {
          await settingsRequest<Backup>("/api/backups", "POST"); await refresh(); setNotice("备份已保存到本机。");
        })}>立即备份</button>
        <button type="button" className="linkish" disabled={busy} onClick={() => fileRef.current?.click()}>选择备份文件…</button>
        <input ref={fileRef} hidden type="file" accept=".sqlite,.db,application/octet-stream" aria-label="选择备份文件" onChange={(event) => {
          const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) importFile(file);
        }} />
      </div>
      {backups[0] && <p className="settings-caption">最近备份：{backups[0].createdLabel}</p>}
      <details open={historyOpen} onToggle={(event) => setHistoryOpen(event.currentTarget.open)} className="settings-details">
        <summary>查看与恢复备份{backups.length ? `（${backups.length}）` : ""}</summary>
        <p className="muted">备份包含事项和历史记录。下载到其他位置，可在换电脑时恢复；助手配置与主题不包含在内。</p>
        <ul className="backup-list">{backups.map((backup) => <li key={backup.name}>
          <div><span>{backup.createdLabel}</span><small>{BACKUP_LABELS[backup.kind] ?? "备份"} · {Math.max(1, Math.round(backup.bytes / 1024))} KB</small></div>
          <a href={`/api/backups/${encodeURIComponent(backup.name)}/download`} download={backup.name}>下载</a>
          <button type="button" className="linkish" disabled={busy} onClick={() => { setRestoreTarget(backup); setError(null); }}>恢复</button>
        </li>)}</ul>
      </details>
      {restoreTarget && <div ref={restoreRef} tabIndex={-1} className="restore-confirm" role="group" aria-label="确认恢复备份">
        <strong>{restoreTarget.kind === "imported" ? "恢复所选备份文件？" : `恢复到 ${restoreTarget.createdLabel}？`}</strong>
        <p>将替换当前的事项和历史记录。恢复前会先备份现有数据，之后仍可找回。</p>
        <div className="settings-actions"><button type="button" disabled={busy} onClick={() => void perform(async () => {
          await settingsRequest("/api/backups/restore", "POST", { name: restoreTarget.name });
          setRestoreTarget(null); notifySettingsChange("planner:restored"); await refresh();
          setNotice("已恢复。恢复前的数据也已保存为备份。");
        })}>{busy ? "正在处理…" : "确认恢复"}</button>
          <button type="button" className="linkish" disabled={busy} onClick={() => { setRestoreTarget(null); setNotice(null); }}>取消</button></div>
      </div>}
    </section>

    <section className="settings-section" aria-labelledby="assistant-title">
      <h2 id="assistant-title">计划助手 <span className="settings-optional">可选</span></h2>
      <p className="muted">用一句话添加或调整计划。你也可以一直手动记录。</p>
      <div className="settings-actions">
        <select aria-label="配置哪个助手" value={selected} disabled={busy || !items.length} onChange={(event) => choose(event.target.value)}>
          {!items.length && <option value="">尚未添加助手</option>}
          {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <button type="button" disabled={checking || busy || !selected} onClick={() => void check()}>{checking ? "正在检测…" : "检测环境"}</button>
      </div>
      {checks[selected] && <p className="settings-check" role="status">{checks[selected].message}</p>}
      <p className="settings-caption">只检查本机安装和可确认的登录状态，不调用模型。</p>
      <details className="settings-details"><summary>连接说明与高级配置</summary>
        <p>先安装并登录所选工具，再点击“检测环境”。使用该工具已设置的默认模型。</p>
        <p><a href="https://learn.chatgpt.com/docs/developer-commands" target="_blank" rel="noreferrer">Codex 使用说明 ↗</a> · <a href="https://opencode.ai/docs/" target="_blank" rel="noreferrer">OpenCode 使用说明 ↗</a></p>
        <p className="muted">发送指令时，会把指令和计划上下文交给所选助手及其模型服务，可能产生该服务的费用。暂停本机执行不保证远端请求停止。</p>
        {!editor && <div className="settings-actions">
          {selectedItem && <button type="button" onClick={() => setEditor(selectedItem)}>编辑配置</button>}
          <button type="button" className="linkish" onClick={() => setEditor({ name: "", command: "" })}>添加其他助手</button>
          {selectedItem && <button type="button" className="linkish quiet" disabled={busy} onClick={() => setRemoving(true)}>移除此助手</button>}
        </div>}
        {removing && <div className="restore-confirm"><p>移除“{selectedItem?.name}”的配置？事项不会受影响。</p><div className="settings-actions">
          <button type="button" disabled={busy} onClick={() => void perform(async () => {
            await settingsRequest(`/api/launchers/${selected}`, "DELETE"); setRemoving(false); setSelected("");
            try { localStorage.removeItem("planner_agent_launcher"); } catch { /* preference */ }
            await refresh(); notifySettingsChange("planner:launchers-changed", "");
          })}>确认移除</button><button type="button" className="linkish" onClick={() => setRemoving(false)}>取消</button>
        </div></div>}
        {editor && <form className="launcher-editor" onSubmit={(event) => { event.preventDefault(); void perform(async () => {
          const saved = await settingsRequest<Launcher>(editor.id ? `/api/launchers/${editor.id}` : "/api/launchers", editor.id ? "PATCH" : "POST", editor);
          setEditor(null); setChecks({}); await refresh(); choose(saved.id); setNotice("助手配置已保存。");
        }); }}>
          <label>名称<input value={editor.name} required maxLength={80} onChange={(event) => setEditor({ ...editor, name: event.target.value })} /></label>
          <label>启动命令<textarea value={editor.command} required rows={3} onChange={(event) => setEditor({ ...editor, command: event.target.value })} /></label>
          <p className="settings-caption">用 {"{prompt}"} 传入指令。自定义命令会在本机执行，请只配置你信任的工具。</p>
          <div className="settings-actions"><button type="submit" disabled={busy || !editor.name.trim() || !editor.command.trim()}>保存配置</button><button type="button" className="linkish" disabled={busy} onClick={() => setEditor(null)}>取消</button></div>
        </form>}
      </details>
    </section>

    <section className="settings-section" aria-labelledby="shortcuts-title">
      <h2 id="shortcuts-title">快捷键</h2>
      <div className="settings-actions">
        <label htmlFor="send-shortcut">发送助手指令</label>
        <select id="send-shortcut" value={shortcut} onChange={(event) => chooseShortcut(parseSendShortcut(event.target.value))}>
          <option value="enter">Enter 发送</option>
          <option value="mod-enter">{modifierLabel} 发送</option>
        </select>
      </div>
      <p className="settings-caption">{newlineLabel} 换行。输入法确认文字时不会发送。选择后立即生效。</p>
    </section>
    <section className="settings-section"><div className="settings-inline"><h2>外观</h2><ThemeSwitcher /></div></section>
    <HelpAndAbout />
  </main>;
}
