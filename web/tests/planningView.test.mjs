import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleGoalIds, goalPath, nextGoalAction } from '../src/planningView.ts';

test('active descendants retain paused ancestors while unrelated archived branches collapse', () => {
  const goals = [
    { id: 'long', state: 'paused', parentGoalId: null },
    { id: 'near', state: 'active', parentGoalId: 'long' },
    { id: 'old', state: 'ended', parentGoalId: null },
    { id: 'deep', state: 'active', parentGoalId: 'near' },
  ];
  assert.deepEqual([...visibleGoalIds(goals)].sort(), ['deep', 'long', 'near']);
  assert.equal(visibleGoalIds(goals, true).size, 4);
  assert.deepEqual(goalPath(goals, 'deep').map(g => g.id), ['long', 'near', 'deep']);
});

test('a materialized next action uses its Task identity without duplicate next selections', () => {
  const action = { id: 'action', taskId: 'task', completed: false, discarded: false };
  const goal = { actions: [action], nextActionId: null, nextTaskId: 'task' };
  assert.equal(nextGoalAction(goal), action);
  assert.equal(nextGoalAction({ ...goal, actions: [{ ...action, completed: true }] }), undefined);
  assert.equal(nextGoalAction({ ...goal, nextActionId: null, nextTaskId: null }), undefined);
});
