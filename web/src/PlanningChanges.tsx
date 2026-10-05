import type { PlanningChange } from "./api";

const kinds = { goal: "目标", phase: "阶段", action: "行动" };
const verbs = { added: "新增", modified: "调整", removed: "移除" };

export function PlanningChanges({ changes }: { changes: PlanningChange[] }) {
  return <details className="planning-draft-change-details">
    <summary>查看变更明细 · {changes.length} 项</summary>
    <div className="planning-review-list">
      {changes.map((change) => <section key={`${change.kind}-${change.id}`} className={`planning-review-change ${change.type}`}>
        <h3><span>{verbs[change.type]}{kinds[change.kind]}</span> {change.title}</h3>
        {change.kind === "goal" && change.type === "removed" && <p className="settings-caption">保存后归档，已有任务和完成记录保留。</p>}
        {!!change.fields?.length && <dl>
          {change.fields.map((field) => <div className="planning-review-field" key={field.field}>
            <dt>{field.label}</dt>
            <dd><small>原来</small><p>{field.before === null ? "无" : field.before || "未填写"}</p></dd>
            <dd><small>调整后</small><p>{field.after === null ? "移除" : field.after || "未填写"}</p></dd>
          </div>)}
        </dl>}
      </section>)}
    </div>
  </details>;
}
