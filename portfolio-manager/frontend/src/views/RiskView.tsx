import { Database, Layers3, ShieldAlert, TrendingDown } from "lucide-react";
import type { CSSProperties } from "react";
import type { Dashboard } from "../types";
import { money, pct, titleCase } from "../lib/format";
import { riskRadarMetrics } from "../lib/viewModels";
import { Badge, EmptyState, SignalPanel } from "../components/ui/Primitives";
import { SingleStockLadder, pickSelectedPolicy } from "../components/policy/SelectedPolicyCard";
import { RiskBlockerCard, deriveRiskBlockers } from "../components/risk/RiskBlockerCard";
import { RiskRadar } from "../components/visuals/RiskRadar";

function riskBadgeLabel(tone: string) {
  if (tone === "danger") return "Fix now";
  if (tone === "attention") return "Monitor";
  return "Clear";
}

function trimPlanValue(action: unknown, key: string) {
  const plan = (action as { trimPlan?: Record<string, number> } | null)?.trimPlan;
  return Number(plan?.[key] ?? 0);
}

export function RiskView({ dashboard, onAsk }: { dashboard: Dashboard; onAsk: (question?: string) => void }) {
  const real = dashboard.real_portfolio;
  const packet = dashboard.advisor_packet;
  const hasHoldings = Boolean(real && real.positions.length > 0);
  const singleBreaches = packet.portfolioRisk.singleNameBreaches;
  const sectorBreaches = packet.portfolioRisk.sectorBreaches;
  const dataBreaches = packet.portfolioRisk.staleDataWarnings;
  const issueCount = packet.portfolioRisk.issueCount;
  const sectors = Object.entries(real?.stress.sector_weights ?? {}).sort((a, b) => b[1] - a[1]);
  const topPositions = [...(real?.positions ?? [])].sort((a, b) => b.weight - a.weight).slice(0, 6);
  const topPosition = topPositions[0];
  const blocked = [
    ...packet.recommendedPriority.blockedActions.map((message, index) => ({ id: `packet-${index}`, symbol: "Gate", reason: message, risk_flags: ["Hard risk gate active."] })),
    ...dashboard.recent_recommendations.filter((item) => item.status === "fail" || item.action === "AVOID")
  ].slice(0, 4);
  const selectedPolicy = pickSelectedPolicy(dashboard);
  const blockers = deriveRiskBlockers(packet, selectedPolicy);
  const maxSingleStock = selectedPolicy?.singleStock?.hardBuyBlock
    ?? Number(dashboard.risk_rules.max_single_stock_weight ?? 0.08);
  const unknownWeight = real?.stress.unknown_sector_weight ?? 0;
  const topRisk = dashboard.advisor_trace.top_risks[0];
  const firstAction = packet.recommendedPriority.firstAction;
  const firstTrimEstimate = firstAction?.action === "TRIM" ? trimPlanValue(firstAction, "estimatedSellValue") : 0;
  const radarMetrics = riskRadarMetrics(dashboard);
  const primaryFix =
    firstAction?.action === "TRIM"
      ? `Create a trim plan for ${firstAction.symbol}: estimated trim ${money(firstTrimEstimate)} toward the ${pct(firstAction.targetWeight)} cap.`
      : topPosition && topPosition.weight > maxSingleStock
        ? `Trim or avoid adding to ${topPosition.symbol} until it moves closer to the ${pct(maxSingleStock)} single-stock guardrail.`
      : topRisk?.what_to_do ?? (hasHoldings ? "No urgent hard-rule fix is required at this snapshot." : "Import holdings to activate real risk analysis.");
  const heroFix =
    firstAction?.action === "TRIM"
      ? `${firstAction.symbol} is ${pct(firstAction.currentWeight ?? 0)} versus the ${pct(firstAction.targetWeight)} cap. Create the trim plan before adding new exposure.`
      : primaryFix;
  const concentrationBody = topPosition
    ? topPosition.weight > maxSingleStock
      ? `${pct(topPosition.weight - maxSingleStock)} over the buy-block threshold. Use Actions for the trim ticket and quote rules.`
      : "Largest position remains inside the current buy-block threshold."
    : "No position weights yet.";
  const sectorBody = sectorBreaches[0]
    ? `${sectorBreaches[0].rule} is above policy. New same-sector exposure stays blocked until this clears.`
    : unknownWeight > 0
      ? `${pct(unknownWeight)} is intentionally labeled Unknown.`
      : "Sector caps use enriched metadata where available.";
  const riskCards = [
    {
      icon: ShieldAlert,
      label: "Concentration",
      value: topPosition ? `${topPosition.symbol} at ${pct(topPosition.weight)}` : "Waiting",
      body: singleBreaches.length ? concentrationBody : (topPosition ? concentrationBody : "No position weights yet."),
      tone: singleBreaches.length ? "danger" : hasHoldings ? "good" : "attention"
    },
    {
      icon: Layers3,
      label: "Sector pressure",
      value: sectors[0] ? `${sectors[0][0]} ${pct(sectors[0][1])}` : "Waiting",
      body: sectorBody,
      tone: sectorBreaches.length ? "danger" : unknownWeight > 0 ? "attention" : hasHoldings ? "good" : "attention"
    },
    {
      icon: Database,
      label: "Data reliability",
      value: titleCase(dashboard.data_freshness.provider_mode),
      body: dataBreaches[0]?.message ?? (dashboard.data_freshness.provider_mode === "live" ? `${dashboard.data_freshness.live_price_symbols} symbols priced.` : "Sample or missing data lowers confidence."),
      tone: dataBreaches.length ? "attention" : dashboard.data_freshness.provider_mode === "live" ? "good" : "attention"
    },
    {
      icon: TrendingDown,
      label: "Drawdown / liquidity",
      value: dashboard.quant_diagnostics.status === "healthy" ? "Checked" : "Review",
      body: "Eligibility uses volatility, drawdown, and liquidity gates.",
      tone: dashboard.quant_diagnostics.status === "healthy" ? "good" : "attention"
    }
  ];

  return (
    <section className="risk-view risk-brief screen-enter">
      <SignalPanel className={`risk-brief-hero ${issueCount ? "danger" : hasHoldings ? "good" : "attention"}`}>
        <div>
          <span>Risk</span>
          <h1>{issueCount && firstAction ? `Top risk: ${firstAction.symbol} concentration` : hasHoldings ? "No forced risk repair" : "Import holdings to see risk"}</h1>
          <p>{heroFix}</p>
          {firstAction?.action === "TRIM" && (
            <div className="risk-hero-receipt">
              <span>Estimated trim</span>
              <strong>{money(firstTrimEstimate)}</strong>
              <p>
                {firstAction.symbol} {pct(firstAction.currentWeight ?? 0)} → {pct(firstAction.targetWeight)}
              </p>
            </div>
          )}
        </div>
        <div className="risk-score-stack">
          <span>Issues</span>
          <strong>{issueCount}</strong>
          <p>{hasHoldings ? titleCase(packet.portfolioRisk.severity) : "Needs holdings"}</p>
        </div>
      </SignalPanel>

      <section className="risk-command-center">
        <SignalPanel className="risk-radar-panel risk-radar-feature">
          <div className="panel-label-row">
            <span>Risk radar</span>
            <Badge tone={issueCount ? "watch" : "live"}>{issueCount ? `${issueCount} active` : "Clear"}</Badge>
          </div>
          <RiskRadar metrics={radarMetrics} />
        </SignalPanel>
        <SignalPanel className="risk-next-move-card">
          <div className="panel-label-row">
            <span>Next move</span>
            <Badge tone={firstAction?.action === "TRIM" ? "fail" : "neutral"}>
              {firstAction ? titleCase(firstAction.action.replace(/_/g, " ")) : "Review"}
            </Badge>
          </div>
          <strong>{firstAction ? `${firstAction.symbol} first` : "No forced repair"}</strong>
          <p>{firstAction?.action === "TRIM" ? `${money(firstTrimEstimate)} estimated trim. Actions shows share count, limit guidance, and rerun triggers.` : primaryFix}</p>
        </SignalPanel>
      </section>

      <section className="risk-brief-grid">
        {riskCards.map(({ icon: Icon, ...card }) => (
          <SignalPanel className={`risk-brief-card ${card.tone}`} key={card.label}>
            <div className="risk-card-top">
              <Icon size={18} />
              <span>{card.label}</span>
              <Badge tone={card.tone}>{riskBadgeLabel(card.tone)}</Badge>
            </div>
            <strong>{card.value}</strong>
            <p>{card.body}</p>
          </SignalPanel>
        ))}
      </section>

      {selectedPolicy && topPosition && (
        <section className="risk-policy-surface compact-policy-row">
          <SignalPanel className="risk-policy-compact">
            <div className="panel-label-row">
              <span>Policy lens</span>
              <Badge tone="neutral">{selectedPolicy.name}</Badge>
            </div>
            <div className="risk-policy-mini-grid">
              <div><span>Target</span><strong>{pct(selectedPolicy.singleStock.target)}</strong></div>
              <div><span>Warning</span><strong>{pct(selectedPolicy.singleStock.warning)}</strong></div>
              <div><span>Block</span><strong>{pct(selectedPolicy.singleStock.hardBuyBlock)}</strong></div>
              <div><span>Sector cap</span><strong>{pct(selectedPolicy.sector.hardCap)}</strong></div>
            </div>
            <p>These thresholds explain why META is first and why risk-increasing exposure is blocked.</p>
          </SignalPanel>
          <SignalPanel className="exposure-stack-panel risk-top-exposure-card">
            <div className="panel-label-row">
              <span>Largest exposure</span>
              <Badge tone={topPosition.weight >= selectedPolicy.singleStock.hardBuyBlock ? "fail" : topPosition.weight >= selectedPolicy.singleStock.warning ? "watch" : "live"}>
                {pct(topPosition.weight)}
              </Badge>
            </div>
            <div className="risk-largest-summary">
              <strong>{topPosition.symbol}</strong>
              <span>{money(topPosition.market_value)} · {topPosition.sector}</span>
              <p>{pct(Math.max(0, topPosition.weight - maxSingleStock))} over the current {pct(maxSingleStock)} buy-block threshold.</p>
            </div>
            <details className="inline-threshold-disclosure">
              <summary>Show threshold ladder</summary>
              <SingleStockLadder
                policy={selectedPolicy.singleStock}
                currentWeight={topPosition.weight}
                symbol={topPosition.symbol}
              />
            </details>
          </SignalPanel>
        </section>
      )}

      <section className="risk-workbench">
        <SignalPanel className="exposure-stack-panel">
          <div className="panel-label-row">
            <span>Top exposures</span>
            <Badge tone={topPosition && topPosition.weight > maxSingleStock ? "fail" : topPositions.length ? "live" : "watch"}>{topPositions.length ? `${topPositions.length} holdings` : "Waiting"}</Badge>
          </div>
          <div className="exposure-stack">
            {topPositions.length ? (
              topPositions.map((position) => (
                <div key={position.symbol} className={position.weight > maxSingleStock ? "over" : ""}>
                  <div>
                    <strong>{position.symbol}</strong>
                    <span>
                      {money(position.market_value)} · {position.sector}
                      {position.weight > maxSingleStock ? ` · ${pct(position.weight - maxSingleStock)} over ${pct(maxSingleStock)} cap` : ""}
                    </span>
                  </div>
                  <i style={{ "--weight": Math.min(100, position.weight * 100) } as CSSProperties} />
                  <b>{pct(position.weight)}</b>
                </div>
              ))
            ) : (
              <EmptyState title="No concentration data" body="Import holdings to see position weight." />
            )}
          </div>
        </SignalPanel>

        <SignalPanel className="sector-stack-panel">
          <div className="panel-label-row">
            <span>Sector and theme pressure</span>
            <Badge tone={sectors[0]?.[1] > 0.3 ? "fail" : sectors.length ? "live" : "watch"}>{sectors.length ? `${sectors.length} groups` : "Waiting"}</Badge>
          </div>
          <div className="sector-stack">
            {sectors.length ? (
              sectors.slice(0, 7).map(([sector, weight]) => (
                <div key={sector} className={sector === "Unknown" || sector === "Unclassified ETF" ? "unknown" : ""}>
                  <span>{sector}</span>
                  <i style={{ "--weight": Math.min(100, weight * 100) } as CSSProperties} />
                  <strong>{pct(weight)}</strong>
                </div>
              ))
            ) : (
              <EmptyState title="No sector map yet" body="Import holdings to see theme pressure." />
            )}
          </div>
          {unknownWeight > 0 && <p className="visual-explainer">Unknown is intentional. Signal Prime labels missing metadata instead of inventing sector exposure.</p>}
        </SignalPanel>
      </section>

      <SignalPanel className="risk-blockers-panel" testId="risk-blockers-panel">
        <div className="panel-label-row">
          <span>Blockers · what clears each one</span>
          <Badge tone={blockers.length ? "watch" : "pass"}>
            {blockers.length ? `${blockers.length} active` : "All clear"}
          </Badge>
        </div>
          {blockers.length ? (
            <div className="risk-blocker-grid">
              {blockers.slice(0, 4).map((blocker) => (
                <RiskBlockerCard key={blocker.id} blocker={blocker} onAsk={onAsk} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No active blockers"
              body="When a risk or data gate trips, the deterministic engine names the exact condition that would clear it."
            />
          )}
          {blocked.length > 0 && (
            <p className="visual-explainer">
              {blocked.length} candidate ideas are not eligible right now. They surface again when data and risk gates clear.
            </p>
          )}
      </SignalPanel>

    </section>
  );
}
