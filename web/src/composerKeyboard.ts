export type SendShortcut = "enter" | "mod-enter";

type Key = Pick<KeyboardEvent, "key" | "keyCode" | "isComposing" | "repeat" | "shiftKey" | "altKey" | "ctrlKey" | "metaKey">;

export function parseSendShortcut(value: unknown): SendShortcut {
  return value === "mod-enter" ? "mod-enter" : "enter";
}

// WKWebView can dispatch compositionend before the Enter keydown that committed
// the text, with neither isComposing nor keyCode 229. Keyup releases the guard
// so the next deliberate Enter works immediately, including a quick second tap.
export class ComposerKeyboard {
  private composing = false;
  private endedAt = -Infinity;
  private confirmingKey: string | null = null;

  compositionStart() { this.composing = true; this.endedAt = -Infinity; }
  compositionEnd(now: number) { this.composing = false; this.endedAt = now; }
  reset() { this.composing = false; this.endedAt = -Infinity; this.confirmingKey = null; }
  keyUp(key: string) {
    if (key === "Enter" || key === "Escape") {
      this.confirmingKey = null;
      this.endedAt = -Infinity;
    }
  }

  keyDown(event: Key, shortcut: SendShortcut, now: number): "ime" | "suppress" | "send" | "native" {
    const confirmation = event.key === "Enter" || event.key === "Escape";
    if (this.composing || event.isComposing || event.keyCode === 229) {
      if (confirmation) this.confirmingKey = event.key;
      return "ime";
    }
    if (confirmation && (this.confirmingKey === event.key || now - this.endedAt < 200)) {
      this.confirmingKey = event.key;
      return "suppress";
    }
    if (!confirmation && !["Shift", "Control", "Meta", "Alt"].includes(event.key)) this.endedAt = -Infinity;
    if (event.key !== "Enter" || event.shiftKey || event.altKey) return "native";
    const matches = shortcut === "enter" ? !event.metaKey && !event.ctrlKey : event.metaKey || event.ctrlKey;
    if (!matches) return "native";
    return event.repeat ? "suppress" : "send";
  }
}
