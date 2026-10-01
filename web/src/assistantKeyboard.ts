export const ASSISTANT_SHORTCUT = "⌘ / Ctrl + Shift + L";

export function matchesAssistantShortcut(event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "isComposing" | "keyCode" | "repeat">, mac: boolean): boolean {
  return event.key.toLowerCase() === "l" && event.shiftKey && !event.altKey &&
    (mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey) &&
    !event.isComposing && event.keyCode !== 229 && !event.repeat;
}
