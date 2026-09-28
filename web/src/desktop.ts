type SettingsEvent = "planner:launchers-changed" | "planner:restored" | "planner:theme-changed" | "planner:shortcuts-changed";

declare global {
  interface Window {
    __PLANNER_DESKTOP_WINDOW__?: "main" | "settings";
    webkit?: { messageHandlers?: { plannerDesktop?: { postMessage: (message: unknown) => void } } };
  }
}

export const isSettingsWindow = window.__PLANNER_DESKTOP_WINDOW__ === "settings";

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
