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

export function normalizeFocusedIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((id): id is string => typeof id === "string" && !!id.trim() && id.length <= 100))].slice(0, 100);
}

export function focusedGoals<T extends Pick<Goal, "id" | "state">>(goals: T[], ids: string[]): T[] {
  const byId = new Map(goals.map((goal) => [goal.id, goal]));
  return normalizeFocusedIds(ids).flatMap((id) => {
    const goal = byId.get(id);
    return goal?.state === "active" ? [goal] : [];
  });
}

export function nextActionCandidates(goal: Goal) {
  const openPhases = new Set(goal.phases.filter((item) => item.status === "open").map((item) => item.id));
  return goal.actions.filter((action) => !action.completed && !action.discarded &&
    (action.phaseId === null || openPhases.has(action.phaseId)));
}
