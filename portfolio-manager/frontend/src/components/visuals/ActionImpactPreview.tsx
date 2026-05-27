import type { Recommendation } from "../../types";
import { pct } from "../../lib/format";

export function ActionImpactPreview({ recommendation }: { recommendation: Recommendation }) {
  const before = Math.max(0.02, Number(recommendation.portfolio_impact?.current_weight ?? 0));
  const after = Math.max(0.02, recommendation.target_weight);
  const delta = after - before;

  return (
    <div className="impact-preview" aria-label="Action impact preview">
      <div>
        <span>Current</span>
        <strong>{pct(before)}</strong>
        <i style={{ width: `${Math.min(100, before * 100)}%` }} />
      </div>
      <div>
        <span>Target</span>
        <strong>{pct(after)}</strong>
        <i style={{ width: `${Math.min(100, after * 100)}%` }} />
      </div>
      <p>{delta >= 0 ? "Adds" : "Reduces"} {pct(Math.abs(delta))} portfolio weight if accepted.</p>
    </div>
  );
}
