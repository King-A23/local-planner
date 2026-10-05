export type CompletionRun = {
  id: string; status: string; mode?: "execution" | "planning";
  result: { receipt?: { changed?: boolean } } | null;
};
export type AgentCompletionNotice = {
  id: string; kind: "success" | "error" | "stopped"; title: string; message: string;
};

const TERMINAL = new Set(["succeeded", "failed", "failed_with_changes", "stopped", "stopped_with_changes"]);

export class AgentCompletionObserver {
  private initialized = false;
  private completed = new Set<string>();

  observe(run: CompletionRun | null): AgentCompletionNotice | null {
    const initial = !this.initialized;
    this.initialized = true;
    if (!run?.result || !TERMINAL.has(run.status) || this.completed.has(run.id)) return null;
    this.completed.add(run.id);
    if (this.completed.size > 100) this.completed.delete(this.completed.values().next().value!);
    // A completed run on the first snapshot is history, not a new completion.
    if (initial) return null;
    const changed = Boolean(run.result.receipt?.changed);
    if (run.status.startsWith("failed")) return {
      id: run.id, kind: "error", title: "计划助手未完成",
      message: changed || run.status === "failed_with_changes" ? "已有部分改动已保留，请查看执行回执。" : "请查看助手回复和执行详情后重试。",
    };
    if (run.status.startsWith("stopped")) return {
      id: run.id, kind: "stopped", title: "计划助手已停止",
      message: changed || run.status === "stopped_with_changes" ? "已有改动已保留，请查看执行回执。" : "本次执行已停止。",
    };
    return run.mode === "planning" ? {
      id: run.id, kind: "success", title: "规划助手已回复",
      message: "请查看规划草案或需要补充的信息；草案需保存后生效。",
    } : {
      id: run.id, kind: "success", title: changed ? "计划助手已完成" : "计划助手已回复",
      message: changed ? "任务处理已结束，请查看改动回执。" : "本次处理已结束，请查看助手回复。",
    };
  }
}
