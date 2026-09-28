import { useRef, type KeyboardEvent } from "react";
import { ComposerKeyboard } from "./composerKeyboard";

// Guard both key handlers and the form's implicit submit. Safari may confirm an
// IME composition before dispatching Enter without an isComposing flag.
export function useEntryKeyboard(onEscape: () => void) {
  const keyboard = useRef(new ComposerKeyboard());
  const blocked = useRef(false);
  return {
    shouldIgnoreSubmit: () => blocked.current,
    allowSubmit: () => { blocked.current = false; },
    bind: {
      onCompositionStart: () => { blocked.current = true; keyboard.current.compositionStart(); },
      onCompositionEnd: () => { blocked.current = true; keyboard.current.compositionEnd(performance.now()); },
      onKeyUp: (e: KeyboardEvent<HTMLInputElement>) => keyboard.current.keyUp(e.key),
      onBlur: () => { keyboard.current.reset(); blocked.current = false; },
      onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => {
        const action = keyboard.current.keyDown(event.nativeEvent, "enter", performance.now());
        blocked.current = action === "ime" || action === "suppress";
        if (action === "ime") { event.stopPropagation(); return; }
        if (action === "suppress") { event.preventDefault(); event.stopPropagation(); return; }
        if (action === "send") { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
        else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onEscape(); }
        else if (event.key === "Enter") event.preventDefault();
      },
    },
  };
}
