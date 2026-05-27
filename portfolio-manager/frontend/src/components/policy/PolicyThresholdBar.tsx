import type { CSSProperties } from "react";
import type { SelectedSingleStockPolicy } from "../../types";
import { pct } from "../../lib/format";

export type ThresholdBand = {
  label: string;
  upperBound: number | null;
  state: "target" | "warning" | "hard_buy_block" | "urgent_review" | "extreme" | string;
};

type Props = {
  policy: SelectedSingleStockPolicy;
  currentWeight: number;
  symbol?: string;
  /**
   * Show a secondary "after" marker at this weight. Useful for before/after
   * impact previews.
   */
  afterWeight?: number;
  compact?: boolean;
  showLegend?: boolean;
  className?: string;
};

export function buildSingleStockBands(policy: SelectedSingleStockPolicy): ThresholdBand[] {
  return [
    { label: "Target", upperBound: policy.target, state: "target" },
    { label: "Warning", upperBound: policy.warning, state: "warning" },
    { label: "Hard buy block", upperBound: policy.hardBuyBlock, state: "hard_buy_block" },
    { label: "Urgent review", upperBound: policy.urgentReview, state: "urgent_review" },
    { label: "Extreme", upperBound: policy.extreme, state: "extreme" },
  ];
}

export function activeBandFor(policy: SelectedSingleStockPolicy, weight: number): ThresholdBand {
  const bands = buildSingleStockBands(policy);
  for (const band of bands) {
    if (band.upperBound !== null && weight < band.upperBound) {
      return band;
    }
  }
  return bands[bands.length - 1];
}

/**
 * A single-stock policy ladder bar that visualises where a position sits
 * versus every V8 threshold (target → warning → hard buy block → urgent review
 * → extreme). Designed to be reused inside tables, drawers, advisory tickets,
 * and impact previews.
 */
export function PolicyThresholdBar({
  policy,
  currentWeight,
  symbol,
  afterWeight,
  compact = false,
  showLegend = true,
  className = "",
}: Props) {
  const bands = buildSingleStockBands(policy);
  const ladderTop = Math.max(
    policy.extreme,
    currentWeight,
    afterWeight ?? 0,
  ) * 1.05;
  const active = activeBandFor(policy, currentWeight);

  return (
    <div
      className={`policy-threshold-bar ${compact ? "compact" : ""} ${className}`.trim()}
      data-state={active.state}
      aria-label={symbol ? `${symbol} cap ladder` : "Single-stock cap ladder"}
    >
      <div className="policy-threshold-track">
        {bands.map((band, idx) => {
          const prev = idx === 0 ? 0 : bands[idx - 1].upperBound ?? 0;
          const upper = band.upperBound ?? ladderTop;
          const widthPct = Math.max(0, Math.min(1, (upper - prev) / ladderTop));
          return (
            <span
              key={band.label}
              className={`policy-threshold-band band-${band.state}`}
              style={{ "--band-width": `${widthPct * 100}%` } as CSSProperties}
              title={`${band.label}: ${pct(prev)} – ${band.upperBound !== null ? pct(band.upperBound) : "max"}`}
            >
              {!compact && (
                <>
                  <em>{band.label}</em>
                  <small>{pct(band.upperBound ?? ladderTop)}</small>
                </>
              )}
            </span>
          );
        })}

        {afterWeight !== undefined && (
          <span
            className="policy-threshold-marker after"
            style={{ "--marker-position": `${Math.min(100, (afterWeight / ladderTop) * 100)}%` } as CSSProperties}
            aria-label={`Suggested after: ${pct(afterWeight)}`}
          >
            <i />
            {!compact && <strong>After</strong>}
            <small>{pct(afterWeight)}</small>
          </span>
        )}

        {currentWeight > 0 && (
          <span
            className="policy-threshold-marker current"
            style={{ "--marker-position": `${Math.min(100, (currentWeight / ladderTop) * 100)}%` } as CSSProperties}
            aria-label={`${symbol ?? "Position"} now at ${pct(currentWeight)}`}
          >
            <i />
            {!compact && <strong>{symbol ?? "Now"}</strong>}
            <small>{pct(currentWeight)}</small>
          </span>
        )}
      </div>

      {showLegend && !compact && (
        <div className="policy-threshold-legend">
          <span><i className="band-target" /> Target {pct(policy.target)}</span>
          <span><i className="band-warning" /> Warning {pct(policy.warning)}</span>
          <span><i className="band-hard_buy_block" /> Blocks new buys {pct(policy.hardBuyBlock)}</span>
          <span><i className="band-urgent_review" /> Urgent {pct(policy.urgentReview)}</span>
          <span><i className="band-extreme" /> Extreme {pct(policy.extreme)}</span>
        </div>
      )}
    </div>
  );
}
