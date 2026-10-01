export type ProcessEvent = {
  sequence: number; itemId: string; kind: "message" | "operation" | "status";
  status: string; summary: string; details?: string;
};
export type ProcessBatch = {
  items: ProcessEvent[]; nextSequence: number; truncated: boolean; source: "none" | "codex" | "opencode";
};

export function mergeProcessEvents(current: ProcessEvent[], batch: ProcessBatch): ProcessEvent[] {
  const rows = new Map((batch.truncated ? [] : current).map((item) => [item.itemId, item]));
  for (const item of batch.items) {
    const previous = rows.get(item.itemId);
    if (!previous || previous.sequence < item.sequence) rows.set(item.itemId, item);
  }
  return [...rows.values()].slice(-500);
}
