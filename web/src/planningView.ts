import type { Goal } from "./api";

/** Active descendants retain the ancestor context needed to understand the map. */
export function visibleGoalIds(goals: Goal[], includeInactive = false): Set<string> {
  const byId = new Map(goals.map((goal) => [goal.id, goal]));
  const visible = new Set<string>();
  for (const goal of goals) {
    if (!includeInactive && goal.state !== "active") continue;
    let current: Goal | undefined = goal;
    const seen = new Set<string>();
    while (current && !seen.has(current.id)) {
      seen.add(current.id);
      visible.add(current.id);
      current = current.parentGoalId ? byId.get(current.parentGoalId) : undefined;
    }
  }
  return visible;
}

export function goalPath(goals: Goal[], goalId: string): Goal[] {
  const byId = new Map(goals.map((goal) => [goal.id, goal]));
  const path: Goal[] = [];
  const seen = new Set<string>();
  let current = byId.get(goalId);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    path.unshift(current);
    current = current.parentGoalId ? byId.get(current.parentGoalId) : undefined;
  }
  return path;
}

export function nextGoalAction(goal: Goal) {
  return goal.actions.find((action) => !action.completed && !action.discarded &&
    (action.id === goal.nextActionId || (goal.nextTaskId !== null && action.taskId === goal.nextTaskId)));
}
