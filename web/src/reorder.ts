/** Move relative to a row edge; never mutate the caller's list. */
export function moveItem(ids: string[], source: string, target: string, after: boolean): string[] {
  if (source === target || !ids.includes(source) || !ids.includes(target)) return ids;
  const next = ids.filter((id) => id !== source);
  next.splice(next.indexOf(target) + (after ? 1 : 0), 0, source);
  return next;
}

/** Reorder visible rows in their existing slots, retaining folded rows and full membership. */
export function mergeVisibleOrder(all: string[], visible: string[]): string[] {
  const subset = new Set(visible);
  if (subset.size !== visible.length || visible.some((id) => !all.includes(id))) return all;
  let index = 0;
  return all.map((id) => subset.has(id) ? visible[index++] : id);
}
