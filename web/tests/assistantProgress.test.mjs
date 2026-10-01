import test from 'node:test';
import assert from 'node:assert/strict';
import { matchesAssistantShortcut } from '../src/assistantKeyboard.ts';
import { mergeProcessEvents } from '../src/agentProgressEvents.ts';

const key = { key: 'L', metaKey: true, ctrlKey: false, shiftKey: true, altKey: false, isComposing: false, keyCode: 76, repeat: false };
test('assistant chord is platform specific and excludes IME and repeats', () => {
  assert.equal(matchesAssistantShortcut(key, true), true);
  assert.equal(matchesAssistantShortcut(key, false), false);
  assert.equal(matchesAssistantShortcut({ ...key, metaKey: false, ctrlKey: true }, false), true);
  for (const change of [{ isComposing: true }, { keyCode: 229 }, { repeat: true }, { altKey: true }, { shiftKey: false }, { key: 'k' }, { ctrlKey: true }]) {
    assert.equal(matchesAssistantShortcut({ ...key, ...change }, true), false);
  }
});
test('operation updates replace one row and reconnect does not duplicate', () => {
  const started = { itemId: 'tool', sequence: 1, kind: 'operation', status: 'running', summary: '读取计划' };
  const done = { ...started, sequence: 2, status: 'completed' };
  const batch = { items: [done], truncated: false, nextSequence: 2, source: 'codex' };
  assert.deepEqual(mergeProcessEvents([started], batch), [done]);
  assert.deepEqual(mergeProcessEvents([done], batch), [done]);
  assert.deepEqual(mergeProcessEvents([done], { ...batch, items: [started] }), [done]);
  assert.deepEqual(mergeProcessEvents([done], { ...batch, items: [], truncated: true }), []);
});
test('client progress rows remain bounded', () => {
  const items = Array.from({ length: 600 }, (_, sequence) => ({ itemId: String(sequence), sequence, kind: 'message', status: 'completed', summary: 'ok' }));
  assert.equal(mergeProcessEvents([], { items, truncated: false }).length, 500);
});
