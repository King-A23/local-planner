import test from "node:test";
import assert from "node:assert/strict";
import { ComposerKeyboard, parseSendShortcut } from "../src/composerKeyboard.ts";

const enter = { key: "Enter", keyCode: 13, isComposing: false, repeat: false, shiftKey: false, altKey: false, ctrlKey: false, metaKey: false };

for (const shortcut of ["enter", "mod-enter"]) {
  for (const modifiers of [{}, { metaKey: true }, { ctrlKey: true }]) {
    test(`IME confirmation never sends: ${shortcut}, ${JSON.stringify(modifiers)}`, () => {
      const keyboard = new ComposerKeyboard();
      keyboard.compositionStart();
      assert.equal(keyboard.keyDown({ ...enter, ...modifiers }, shortcut, 100), "ime");
      keyboard.compositionEnd(110);
      assert.equal(keyboard.keyDown({ ...enter, ...modifiers, repeat: true }, shortcut, 500), "suppress");
      keyboard.keyUp("Enter");
      assert.equal(keyboard.keyDown({ ...enter, ...(shortcut === "mod-enter" ? { metaKey: true } : {}) }, shortcut, 501), "send");
    });
  }
  test(`WKWebView compositionend before unflagged Enter: ${shortcut}`, () => {
    const keyboard = new ComposerKeyboard();
    keyboard.compositionStart();
    keyboard.compositionEnd(100);
    const key = { ...enter, metaKey: shortcut === "mod-enter" };
    assert.equal(keyboard.keyDown(key, shortcut, 101), "suppress");
    assert.equal(keyboard.keyDown({ ...key, repeat: true }, shortcut, 600), "suppress");
    keyboard.keyUp("Enter");
    assert.equal(keyboard.keyDown(key, shortcut, 601), "send");
  });
}

test("native IME flags protect the boundary before compositionstart", () => {
  const keyboard = new ComposerKeyboard();
  assert.equal(keyboard.keyDown({ ...enter, isComposing: true }, "enter", 0), "ime");
  keyboard.reset();
  assert.equal(keyboard.keyDown({ ...enter, keyCode: 229 }, "enter", 0), "ime");
});

test("mouse confirmation expires without leaving Enter stuck", () => {
  const keyboard = new ComposerKeyboard();
  keyboard.compositionStart();
  keyboard.compositionEnd(100);
  assert.equal(keyboard.keyDown(enter, "enter", 301), "send");
});

test("typing or blurring clears stale confirmation state", () => {
  const keyboard = new ComposerKeyboard();
  keyboard.compositionStart();
  keyboard.compositionEnd(100);
  assert.equal(keyboard.keyDown({ ...enter, key: "a", keyCode: 65 }, "enter", 101), "native");
  assert.equal(keyboard.keyDown(enter, "enter", 102), "send");
  keyboard.compositionStart();
  keyboard.reset();
  assert.equal(keyboard.keyDown(enter, "enter", 103), "send");
});

test("IME Escape cancels composition without closing the panel", () => {
  const keyboard = new ComposerKeyboard();
  const escape = { ...enter, key: "Escape", keyCode: 27 };
  keyboard.compositionStart();
  assert.equal(keyboard.keyDown(escape, "enter", 1), "ime");
  keyboard.compositionEnd(2);
  assert.equal(keyboard.keyDown(escape, "enter", 3), "suppress");
  keyboard.keyUp("Escape");
  assert.equal(keyboard.keyDown(escape, "enter", 4), "native");
});

test("send choice preserves newline combinations and suppresses repeated submissions", () => {
  const keyboard = new ComposerKeyboard();
  assert.equal(keyboard.keyDown(enter, "enter", 0), "send");
  assert.equal(keyboard.keyDown(enter, "mod-enter", 0), "native");
  for (const key of [{ ...enter, metaKey: true }, { ...enter, ctrlKey: true }]) {
    assert.equal(keyboard.keyDown(key, "mod-enter", 0), "send");
    assert.equal(keyboard.keyDown(key, "enter", 0), "native");
    assert.equal(keyboard.keyDown({ ...key, shiftKey: true }, "mod-enter", 0), "native");
    assert.equal(keyboard.keyDown({ ...key, repeat: true }, "mod-enter", 0), "suppress");
  }
  assert.equal(keyboard.keyDown({ ...enter, shiftKey: true }, "enter", 0), "native");
  assert.equal(keyboard.keyDown({ ...enter, altKey: true }, "enter", 0), "native");
  assert.equal(keyboard.keyDown({ ...enter, repeat: true }, "enter", 0), "suppress");
});

test("missing or invalid persisted choice uses Enter", () => {
  assert.equal(parseSendShortcut("mod-enter"), "mod-enter");
  for (const value of [null, undefined, "", "invalid", "enter"]) assert.equal(parseSendShortcut(value), "enter");
});
