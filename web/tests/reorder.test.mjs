import { test } from 'node:test';
import assert from 'node:assert/strict';
import { moveItem, mergeVisibleOrder } from '../src/reorder.ts';

test('drag insertion preserves other rows and never mutates the source', () => {
  const ids = ['a', 'b', 'c', 'd'];
  assert.deepEqual(moveItem(ids, 'a', 'c', true), ['b', 'c', 'a', 'd']);
  assert.deepEqual(moveItem(ids, 'd', 'b', false), ['a', 'd', 'b', 'c']);
  assert.deepEqual(moveItem(ids, 'b', 'a', false), ['b', 'a', 'c', 'd']);
  assert.deepEqual(moveItem(ids, 'b', 'c', true), ['a', 'c', 'b', 'd']);
  assert.deepEqual(ids, ['a', 'b', 'c', 'd']);
});

test('folded completed rows keep their slots and full server membership when active rows move', () => {
  const all = ['done-first', 'a', 'done-middle', 'b', 'c', 'done-last'];
  assert.deepEqual(mergeVisibleOrder(all, ['c', 'a', 'b']), ['done-first', 'c', 'done-middle', 'a', 'b', 'done-last']);
  assert.deepEqual(all, ['done-first', 'a', 'done-middle', 'b', 'c', 'done-last']);
  assert.deepEqual(mergeVisibleOrder(all, []), all);
  assert.deepEqual(mergeVisibleOrder(all, ['a']), all);
});

test('stale or duplicate visible ids cannot drop hidden rows from a reorder request', () => {
  const all = ['a', 'done', 'b'];
  assert.deepEqual(mergeVisibleOrder(all, ['a', 'missing']), all);
  assert.deepEqual(mergeVisibleOrder(all, ['a', 'a']), all);
});

test('self drop, stale source and cross-list drop keep original ordering', () => {
  const ids = ['a', 'b'];
  assert.deepEqual(moveItem(ids, 'a', 'a', true), ids);
  assert.deepEqual(moveItem(ids, 'missing', 'b', false), ids);
  assert.deepEqual(moveItem(ids, 'a', 'another-list', false), ids);
});
