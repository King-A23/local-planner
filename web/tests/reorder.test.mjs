import { test } from 'node:test';
import assert from 'node:assert/strict';
import { moveItem } from '../src/reorder.ts';

test('drag insertion preserves other rows and never mutates the source', () => {
  const ids = ['a', 'b', 'c', 'd'];
  assert.deepEqual(moveItem(ids, 'a', 'c', true), ['b', 'c', 'a', 'd']);
  assert.deepEqual(moveItem(ids, 'd', 'b', false), ['a', 'd', 'b', 'c']);
  assert.deepEqual(moveItem(ids, 'b', 'a', false), ['b', 'a', 'c', 'd']);
  assert.deepEqual(moveItem(ids, 'b', 'c', true), ['a', 'c', 'b', 'd']);
  assert.deepEqual(ids, ['a', 'b', 'c', 'd']);
});

test('self drop, stale source and cross-list drop keep original ordering', () => {
  const ids = ['a', 'b'];
  assert.deepEqual(moveItem(ids, 'a', 'a', true), ids);
  assert.deepEqual(moveItem(ids, 'missing', 'b', false), ids);
  assert.deepEqual(moveItem(ids, 'a', 'another-list', false), ids);
});
