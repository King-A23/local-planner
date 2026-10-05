import test from 'node:test';
import assert from 'node:assert/strict';
import { AgentCompletionObserver } from '../src/agentCompletion.ts';

const run = (id, status = 'succeeded', changed = true, mode = 'execution') => ({ id, status, mode, result: { receipt: { changed } } });
test('historical completion at startup is silent and does not repeat', () => {
  const observer = new AgentCompletionObserver();
  assert.equal(observer.observe(run('old')), null);
  assert.equal(observer.observe(run('old')), null);
  assert.equal(observer.observe(run('new')).id, 'new');
  assert.equal(observer.observe(run('new')), null);
});
test('active and paused runs notify only when a final result arrives', () => {
  const observer = new AgentCompletionObserver();
  for (const status of ['starting', 'running', 'paused', 'stopping']) {
    assert.equal(observer.observe({ ...run('task', status), result: null }), null);
  }
  assert.equal(observer.observe(run('task')).title, '计划助手已完成');
  assert.equal(observer.observe(run('task')), null);
});
test('fast runs completing between polls still notify once', () => {
  const observer = new AgentCompletionObserver();
  assert.equal(observer.observe(null), null);
  assert.equal(observer.observe(run('fast')).id, 'fast');
  assert.equal(observer.observe(run('fast')), null);
});
test('failure, stopping, replies and unsaved planning are described accurately', () => {
  const observer = new AgentCompletionObserver(); observer.observe(null);
  assert.equal(observer.observe(run('failed', 'failed', false)).kind, 'error');
  assert.match(observer.observe(run('partial', 'failed_with_changes')).message, /部分改动/);
  assert.equal(observer.observe(run('stopped', 'stopped', false)).kind, 'stopped');
  assert.match(observer.observe(run('saved', 'stopped_with_changes')).message, /改动已保留/);
  assert.equal(observer.observe(run('reply', 'succeeded', false)).title, '计划助手已回复');
  assert.match(observer.observe(run('planning', 'succeeded', false, 'planning')).message, /草案需保存/);
});
