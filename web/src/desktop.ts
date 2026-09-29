type SettingsEvent = "planner:launchers-changed" | "planner:restored" | "planner:theme-changed" | "planner:shortcuts-changed";

declare global {
  interface Window {
    __PLANNER_DESKTOP_WINDOW__?: "main" | "settings";
    __PLANNER_DESKTOP_THEME__?: string | null;
    webkit?: { messageHandlers?: { plannerDesktop?: { postMessage: (message: unknown) => void } } };
  }
}

export const isSettingsWindow = window.__PLANNER_DESKTOP_WINDOW__ === "settings";

const themeIds = ["warm-paper", "midnight", "nordic", "forest", "retro"];

export function preferredTheme(): string | null {
  const fromUrl = new URLSearchParams(window.location.search).get("theme");
  if (fromUrl && themeIds.includes(fromUrl)) return fromUrl;
  const native = window.__PLANNER_DESKTOP_THEME__;
  if (native && themeIds.includes(native)) return native;
  let saved: string | null = null;
  try { saved = localStorage.getItem("planner_theme"); } catch { /* optional preference */ }
  if (!saved || !themeIds.includes(saved)) return null;
  // Migrate a preference saved by an older desktop build on this port.
  if (window.__PLANNER_DESKTOP_WINDOW__ && !native)
    window.webkit?.messageHandlers?.plannerDesktop?.postMessage({ action: "setTheme", value: saved });
  return saved;
}

export function openDesktopSettings(href: string): boolean {
  const bridge = window.webkit?.messageHandlers?.plannerDesktop;
  if (!window.__PLANNER_DESKTOP_WINDOW__ || !bridge) return false;
  bridge.postMessage({ action: "openSettings", fragment: new URL(href, window.location.href).hash.slice(1) });
  return true;
}

export function closeDesktopSettings() {
  window.webkit?.messageHandlers?.plannerDesktop?.postMessage({ action: "closeSettings" });
}

export function notifySettingsChange(event: SettingsEvent, detail?: string) {
  window.dispatchEvent(new CustomEvent(event, { detail }));
  window.webkit?.messageHandlers?.plannerDesktop?.postMessage({ action: "settingsChanged", event, ...(detail === undefined ? {} : { detail }) });
}
