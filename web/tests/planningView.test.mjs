import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleGoalIds, goalPath, nextGoalAction, normalizeFocusedIds, focusedGoals, nextActionCandidates } from '../src/planningView.ts';

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

test('focus remains user-selected, ordered and hidden while paused without discarding the preference', () => {
  const goals = [{ id: 'a', state: 'active' }, { id: 'b', state: 'paused' }, { id: 'c', state: 'ended' }];
  const ids = ['b', 'a', 'deleted', 'c', 'a'];
  assert.deepEqual(focusedGoals(goals, ids).map(g => g.id), ['a']);
  assert.deepEqual(focusedGoals(goals.map(g => ({ ...g, state: 'active' })), ids).map(g => g.id), ['b', 'a', 'c']);
  assert.deepEqual(focusedGoals(goals, []), []);
  assert.deepEqual(normalizeFocusedIds([null, {}, ' ', 'a', 'a', 'b', 'x'.repeat(101)]), ['a', 'b']);
  assert.deepEqual(normalizeFocusedIds('broken preference'), []);
});

test('next-step choices exclude completed, discarded and closed-stage actions, preserving formal Task identity', () => {
  const goal = {
    phases: [{ id: 'open', status: 'open' }, { id: 'done', status: 'done' }],
    actions: [
      { id: 'candidate', phaseId: 'open', completed: false, discarded: false, taskId: null },
      { id: 'formal', phaseId: null, completed: false, discarded: false, taskId: 'existing-task' },
      { id: 'completed', phaseId: 'open', completed: true, discarded: false },
      { id: 'discarded', phaseId: null, completed: false, discarded: true },
      { id: 'closed', phaseId: 'done', completed: false, discarded: false },
      { id: 'missing-stage', phaseId: 'missing', completed: false, discarded: false },
    ],
  };
  assert.deepEqual(nextActionCandidates(goal).map(a => a.id), ['candidate', 'formal']);
  assert.equal(nextActionCandidates(goal)[1].taskId, 'existing-task');
});
