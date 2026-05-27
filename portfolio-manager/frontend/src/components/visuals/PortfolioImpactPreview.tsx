import type { CSSProperties } from "react";
import { ArrowRight } from "lucide-react";
import type { AdvisorPacketAction, Portfolio, SelectedPolicy } from "../../types";
import { money, pct } from "../../lib/format";

type Props = {
  portfolio: Portfolio;
  action: AdvisorPacketAction;
  policy: SelectedPolicy | null;
  riskBreachCount?: { before: number; after: number };
};

function severityFromWeight(weight: number, policy: SelectedPolicy | null): "ok" | "warning" | "block" | "extreme" {
  if (!policy) return "ok";
  if (weight >= policy.singleStock.extreme) return "extreme";
  if (weight >= policy.singleStock.urgentReview) return "block";
  if (weight >= policy.singleStock.warning) return "warning";
  return "ok";
}

/**
 * Before / after preview of a single advisory action. Shows the position
 * weight, sector weight, and risk severity moving from current to suggested
 * state — using only numbers produced by the deterministic engine.
 */
export function PortfolioImpactPreview({ portfolio, action, policy, riskBreachCount }: Props) {
  const isTrim = action.action === "TRIM";
  const symbol = action.symbol;
  const beforeWeight = action.currentWeight ?? 0;
  const afterWeight =
    action.trimPlan?.estimatedPostWeightCompliant ??
    action.trimPlan?.estimatedPostWeight ??
    action.targetWeight ??
    beforeWeight;

  const sectorBefore = portfolio.stress?.sector_weights?.[action.sector ?? ""] ?? 0;
  const sectorDelta = (beforeWeight - afterWeight);
  const sectorAfter = Math.max(0, sectorBefore - sectorDelta);

  const cashBefore = portfolio.cash ?? 0;
  const trimCash = action.trimPlan?.estimatedSellValue ?? 0;
  const cashAfter = isTrim ? cashBefore + trimCash : cashBefore - trimCash;

  const beforeSeverity = severityFromWeight(beforeWeight, policy);
  const afterSeverity = severityFromWeight(afterWeight, policy);

  const ladderTop = Math.max(policy?.singleStock.extreme ?? 0.25, beforeWeight, afterWeight) * 1.05;

  return (
    <div className="portfolio-impact-preview" data-testid="portfolio-impact-preview">
      <header>
        <span>Portfolio impact preview</span>
        <strong>{isTrim ? "Trim" : "Add"} {symbol} · advisory-only</strong>
      </header>

      <div className="portfolio-impact-row">
        <div className={`portfolio-impact-side severity-${beforeSeverity}`}>
          <span>Before</span>
          <strong>{symbol}: {pct(beforeWeight)}</strong>
          <i style={{ "--bar-fill": `${(beforeWeight / ladderTop) * 100}%` } as CSSProperties} />
        </div>
        <ArrowRight size={18} aria-hidden="true" />
        <div className={`portfolio-impact-side severity-${afterSeverity}`}>
          <span>After {isTrim ? "trim" : "add"}</span>
          <strong>{symbol}: {pct(afterWeight)}</strong>
          <i style={{ "--bar-fill": `${(afterWeight / ladderTop) * 100}%` } as CSSProperties} />
        </div>
      </div>

      {action.sector && sectorBefore > 0 && (
        <div className="portfolio-impact-row secondary">
          <div className="portfolio-impact-side ghost">
            <span>{action.sector} before</span>
            <strong>{pct(sectorBefore)}</strong>
          </div>
          <ArrowRight size={14} aria-hidden="true" />
          <div className="portfolio-impact-side ghost">
            <span>{action.sector} after</span>
            <strong>{pct(sectorAfter)}</strong>
          </div>
        </div>
      )}

      <dl className="portfolio-impact-meta">
        <div>
          <dt>Cash</dt>
          <dd>{money(cashBefore)} → {money(cashAfter)}</dd>
        </div>
        {trimCash > 0 && (
          <div>
            <dt>{isTrim ? "Redeployable" : "Capital required"}</dt>
            <dd>{money(trimCash)}</dd>
          </div>
        )}
        {riskBreachCount && (
          <div>
            <dt>Risk issues</dt>
            <dd>{riskBreachCount.before} → {riskBreachCount.after}</dd>
          </div>
        )}
        {policy && (
          <div>
            <dt>Policy threshold</dt>
            <dd>{pct(policy.singleStock.hardBuyBlock)}</dd>
          </div>
        )}
      </dl>

      <footer>Estimated using the engine's deterministic math. No order has been placed.</footer>
    </div>
  );
}
