import { money, pct } from "../../lib/format";

type Tranche = {
  trancheNumber?: number;
  targetDateOrCondition?: string;
  estimatedWeight?: number;
  estimatedDollarAmount?: number;
  trigger?: string;
  invalidation?: string;
};

export function StaggerTimeline({ schedule, symbol }: { schedule: Tranche[]; symbol: string }) {
  if (!schedule.length) return null;

  return (
    <div className="receipt-timeline" aria-label={`Stagger plan for ${symbol}`}>
      {schedule.map((tranche, index) => (
        <article className="receipt-timeline-item" key={`${symbol}-${tranche.trancheNumber ?? index}`}>
          <span className="receipt-timeline-marker">{tranche.trancheNumber ?? index + 1}</span>
          <div>
            <strong>
              Tranche {tranche.trancheNumber ?? index + 1} · {money(Number(tranche.estimatedDollarAmount ?? 0))}
            </strong>
            <p>
              Target weight {pct(Number(tranche.estimatedWeight ?? 0))} · {tranche.targetDateOrCondition ?? "On schedule"}
            </p>
            {tranche.trigger && <small>Trigger: {tranche.trigger}</small>}
            {tranche.invalidation && <small>Invalidation: {tranche.invalidation}</small>}
          </div>
        </article>
      ))}
    </div>
  );
}
