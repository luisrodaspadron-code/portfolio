import type { CSSProperties } from "react";
import { Shield, Layers, Database, Coins, Hourglass } from "lucide-react";
import type { Dashboard, SelectedPolicy } from "../../types";
import { pct } from "../../lib/format";
import { Badge, SignalPanel } from "../ui/Primitives";

export function pickSelectedPolicy(dashboard: Dashboard): SelectedPolicy | null {
  return (
    dashboard.advisor_packet?.selectedPolicy ??
    dashboard.policy?.selectedPolicy ??
    null
  );
}

type LadderInput = {
  symbol?: string;
  currentWeight?: number;
  policy: SelectedPolicy["singleStock"];
};

type LadderBand = {
  label: string;
  upperBound: number | null;
  state: "target" | "warning" | "hard_buy_block" | "urgent_review" | "extreme";
};

function buildBands(policy: SelectedPolicy["singleStock"]): LadderBand[] {
  return [
    { label: "Target", upperBound: policy.target, state: "target" },
    { label: "Warning", upperBound: policy.warning, state: "warning" },
    { label: "Hard buy block", upperBound: policy.hardBuyBlock, state: "hard_buy_block" },
    { label: "Urgent review", upperBound: policy.urgentReview, state: "urgent_review" },
    { label: "Extreme", upperBound: policy.extreme, state: "extreme" },
  ];
}

function activeBand(bands: LadderBand[], weight: number): LadderBand {
  for (const band of bands) {
    if (band.upperBound !== null && weight < band.upperBound) {
      return band;
    }
  }
  return bands[bands.length - 1];
}

export function SingleStockLadder({ policy, currentWeight, symbol }: LadderInput) {
  const bands = buildBands(policy);
  const ladderTop = Math.max(policy.extreme, currentWeight ?? 0) * 1.05;
  const weight = currentWeight ?? 0;
  const active = activeBand(bands, weight);

  return (
    <div className="policy-ladder" data-state={active.state} aria-label="Single-stock policy ladder">
      <div className="policy-ladder-track">
        {bands.map((band, idx) => {
          const prev = idx === 0 ? 0 : bands[idx - 1].upperBound ?? 0;
          const upper = band.upperBound ?? ladderTop;
          const widthPct = Math.max(0, Math.min(1, (upper - prev) / ladderTop));
          return (
            <span
              key={band.label}
              className={`policy-ladder-band band-${band.state}`}
              style={{ "--band-width": `${widthPct * 100}%` } as CSSProperties}
              title={`${band.label}: ${pct(prev)} – ${band.upperBound !== null ? pct(band.upperBound) : "+"}`}
            >
              <em>{band.label}</em>
              <small>{pct(band.upperBound ?? ladderTop)}</small>
            </span>
          );
        })}
        {weight > 0 && (
          <span
            className="policy-ladder-marker"
            style={{ "--marker-position": `${Math.min(100, (weight / ladderTop) * 100)}%` } as CSSProperties}
            aria-label={`${symbol ?? "Position"} at ${pct(weight)}`}
          >
            <i />
            <strong>{symbol ?? "Now"}</strong>
            <small>{pct(weight)}</small>
          </span>
        )}
      </div>
      <div className="policy-ladder-legend">
        <span><i className="band-target" /> Target</span>
        <span><i className="band-warning" /> Warning</span>
        <span><i className="band-hard_buy_block" /> Blocks new buys</span>
        <span><i className="band-urgent_review" /> Urgent review</span>
        <span><i className="band-extreme" /> Extreme</span>
      </div>
    </div>
  );
}

export function SelectedPolicyCard({ policy, footnote }: { policy: SelectedPolicy; footnote?: string }) {
  const presetTone =
    policy.preset === "conservative" ? "good" :
    policy.preset === "competition" ? "fail" :
    policy.preset === "aggressive" ? "watch" : "live";

  return (
    <SignalPanel className="selected-policy-card" testId="selected-policy-card">
      <header className="selected-policy-head">
        <div>
          <span>Risk policy</span>
          <h3>{policy.name}</h3>
          <p>
            {policy.advisoryOnly ? "Advisory-only. No order has been placed." : "Active policy"}
            {policy.version ? ` · ${policy.version}` : ""}
          </p>
        </div>
        <Badge tone={presetTone}>{policy.preset}</Badge>
      </header>

      <section className="selected-policy-section">
        <div className="selected-policy-section-head">
          <Shield size={16} />
          <strong>Single-stock cap ladder</strong>
        </div>
        <SingleStockLadder policy={policy.singleStock} />
      </section>

      <section className="selected-policy-grid">
        <div>
          <div className="selected-policy-section-head">
            <Layers size={16} />
            <strong>Sectors</strong>
          </div>
          <dl>
            <div><dt>Warning</dt><dd>{pct(policy.sector.warning)}</dd></div>
            <div><dt>Hard cap</dt><dd>{pct(policy.sector.hardCap)}</dd></div>
            <div><dt>Max active overweight</dt><dd>{pct(policy.sector.maxActiveOverweight)}</dd></div>
          </dl>
        </div>

        <div>
          <div className="selected-policy-section-head">
            <Database size={16} />
            <strong>Data freshness</strong>
          </div>
          <dl>
            <div><dt>Equity live window</dt><dd>{Math.round(policy.dataQuality.equityLiveSeconds / 60)} min</dd></div>
            <div><dt>Equity recent window</dt><dd>{Math.round(policy.dataQuality.equityRecentSeconds / 3600)} hr</dd></div>
            <div><dt>History (restricted)</dt><dd>{policy.dataQuality.minHistoryDaysRestricted}d</dd></div>
            <div><dt>History (full)</dt><dd>{policy.dataQuality.minHistoryDaysFull}d</dd></div>
          </dl>
        </div>

        <div>
          <div className="selected-policy-section-head">
            <Coins size={16} />
            <strong>Crypto + ETFs</strong>
          </div>
          <dl>
            <div><dt>Crypto enabled by default</dt><dd>{policy.crypto.enabledByDefault ? "Yes" : "No"}</dd></div>
            <div><dt>Crypto max total</dt><dd>{pct(policy.crypto.maxTotal)}</dd></div>
            <div><dt>Broad ETF cap</dt><dd>{pct(policy.broadEtf.maxSingleBroadEtf)}</dd></div>
            <div><dt>Thematic ETF cap</dt><dd>{pct(policy.thematicEtf.maxSingleThematicEtf)}</dd></div>
          </dl>
        </div>

        <div>
          <div className="selected-policy-section-head">
            <Hourglass size={16} />
            <strong>Remediation</strong>
          </div>
          <dl>
            <div><dt>Risk-reducing trades during breach</dt><dd>{policy.remediation.allowRiskReducingTradesDuringBreach ? "Allowed" : "Blocked"}</dd></div>
            <div><dt>Risk-increasing trades during breach</dt><dd>{policy.remediation.blockRiskIncreasingTradesDuringBreach ? "Blocked" : "Allowed"}</dd></div>
            <div><dt>Tax-aware warning</dt><dd>{policy.remediation.requireTaxWarningForTaxableAccounts ? "Required" : "Off"}</dd></div>
            {policy.remediation.defaultTranches !== undefined && (
              <div><dt>Default tranches</dt><dd>{policy.remediation.defaultTranches}</dd></div>
            )}
          </dl>
        </div>
      </section>

      {footnote && <p className="selected-policy-footnote">{footnote}</p>}
    </SignalPanel>
  );
}
