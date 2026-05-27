import { Database, Layers3, MessageCircle, ShieldAlert, TrendingDown } from "lucide-react";
import type { CSSProperties } from "react";
import type { Dashboard } from "../types";
import { money, pct, titleCase } from "../lib/format";
import { riskRadarMetrics } from "../lib/viewModels";
import { RiskRadar } from "../components/visuals/RiskRadar";
import { Badge, CommandButton, EmptyState, SignalPanel } from "../components/ui/Primitives";
import { SelectedPolicyCard, SingleStockLadder, pickSelectedPolicy } from "../components/policy/SelectedPolicyCard";
import { RiskBlockerCard, deriveRiskBlockers } from "../components/risk/RiskBlockerCard";

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
  const radarMetrics = riskRadarMetrics(dashboard);
  const selectedPolicy = pickSelectedPolicy(dashboard);
  const blockers = deriveRiskBlockers(packet, selectedPolicy);
  const maxSingleStock = selectedPolicy?.singleStock?.hardBuyBlock
    ?? Number(dashboard.risk_rules.max_single_stock_weight ?? 0.08);
  const unknownWeight = real?.stress.unknown_sector_weight ?? 0;
  const topRisk = dashboard.advisor_trace.top_risks[0];
  const firstAction = packet.recommendedPriority.firstAction;
  const firstTrimEstimate = firstAction?.action === "TRIM" ? trimPlanValue(firstAction, "estimatedSellValue") : 0;
  const primaryFix =
    firstAction?.action === "TRIM"
      ? `Create an advisory trim plan for ${firstAction.symbol}: estimated trim ${money(firstTrimEstimate)} toward the ${pct(firstAction.targetWeight)} cap. Advisory-only. No order has been placed.`
      : topPosition && topPosition.weight > maxSingleStock
        ? `Trim or avoid adding to ${topPosition.symbol} until it moves closer to the ${pct(maxSingleStock)} single-stock guardrail.`
      : topRisk?.what_to_do ?? (hasHoldings ? "No urgent hard-rule fix is required at this snapshot." : "Import holdings to activate real risk analysis.");
  const heroFix =
    firstAction?.action === "TRIM"
      ? `${firstAction.symbol} is ${pct(firstAction.currentWeight ?? 0)} versus the ${pct(firstAction.targetWeight)} cap. Create the trim plan before adding new exposure.`
      : primaryFix;
  const riskCards = [
    {
      icon: ShieldAlert,
      label: "Concentration",
      value: topPosition ? `${topPosition.symbol} at ${pct(topPosition.weight)}` : "Waiting",
      body: singleBreaches[0]?.message ?? (topPosition ? primaryFix : "No position weights yet."),
      tone: singleBreaches.length ? "danger" : hasHoldings ? "good" : "attention"
    },
    {
      icon: Layers3,
      label: "Sector pressure",
      value: sectors[0] ? `${sectors[0][0]} ${pct(sectors[0][1])}` : "Waiting",
      body: sectorBreaches[0]?.message ?? (unknownWeight > 0 ? `${pct(unknownWeight)} is in Unknown because Signal refuses to guess sector metadata.` : "Sector/theme caps use enriched metadata where available."),
      tone: sectorBreaches.length ? "danger" : unknownWeight > 0 ? "attention" : hasHoldings ? "good" : "attention"
    },
    {
      icon: Database,
      label: "Data reliability",
      value: titleCase(dashboard.data_freshness.provider_mode),
      body: dataBreaches[0]?.message ?? (dashboard.data_freshness.provider_mode === "live" ? `${dashboard.data_freshness.live_price_symbols} live/recent symbols are priced.` : "Sample or missing data lowers confidence until live market data is connected."),
      tone: dataBreaches.length ? "attention" : dashboard.data_freshness.provider_mode === "live" ? "good" : "attention"
    },
    {
      icon: TrendingDown,
      label: "Drawdown / liquidity",
      value: dashboard.quant_diagnostics.status === "healthy" ? "Checked" : "Review",
      body: dashboard.quant_diagnostics.checks.find((check) => check.name.toLowerCase().includes("risk"))?.detail ?? "Volatility, drawdown, and liquidity gates are applied before an idea can become eligible.",
      tone: dashboard.quant_diagnostics.status === "healthy" ? "good" : "attention"
    }
  ];

  return (
    <section className="risk-view risk-brief screen-enter">
      <SignalPanel className={`risk-brief-hero ${issueCount ? "danger" : hasHoldings ? "good" : "attention"}`}>
        <div>
          <span>Risk Brief</span>
          <h1>{issueCount ? "Fix the risk that can hurt compounding first." : hasHoldings ? "No hard risk breach is forcing action." : "Import holdings to see real portfolio risk."}</h1>
          <p>{heroFix}</p>
          {firstAction?.action === "TRIM" && (
            <div className="risk-hero-receipt">
              <span>Estimated trim</span>
              <strong>{money(firstTrimEstimate)}</strong>
              <p>
                {firstAction.symbol} {pct(firstAction.currentWeight ?? 0)} → {pct(firstAction.targetWeight)} · advisory-only
              </p>
            </div>
          )}
          <div className="inline-actions">
            <CommandButton icon={MessageCircle} variant="primary" onClick={() => onAsk("Give me a plain-English risk summary and the one thing I should change first.")}>
              Ask Signal about risk
            </CommandButton>
          </div>
        </div>
        <div className="risk-score-stack">
          <span>Issues</span>
          <strong>{issueCount}</strong>
          <p>{hasHoldings ? titleCase(packet.portfolioRisk.severity) : "Needs holdings"}</p>
        </div>
      </SignalPanel>

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

      <SignalPanel className="risk-radar-panel" testId="risk-radar-panel">
        <div className="panel-label-row">
          <span>Risk radar</span>
          <Badge tone={issueCount ? "watch" : "live"}>{issueCount ? `${issueCount} issues` : "Balanced"}</Badge>
        </div>
        <RiskRadar metrics={radarMetrics} />
        <p className="visual-explainer">
          Six axes: concentration · sector pressure · data quality · liquidity · drawdown · factor crowding.
          Each axis is driven by deterministic gates the engine already computed — the LLM only narrates.
        </p>
      </SignalPanel>

      {selectedPolicy && (
        <SelectedPolicyCard
          policy={selectedPolicy}
          footnote="Policy is the source of truth for caps, blocks, and remediation. The LLM advises in narrative; the deterministic engine enforces these bands."
        />
      )}

      {selectedPolicy && topPosition && (
        <SignalPanel className="risk-radar-panel">
          <div className="panel-label-row">
            <span>{topPosition.symbol} versus single-stock policy</span>
            <Badge tone={topPosition.weight >= selectedPolicy.singleStock.hardBuyBlock ? "fail" : topPosition.weight >= selectedPolicy.singleStock.warning ? "watch" : "live"}>
              {pct(topPosition.weight)}
            </Badge>
          </div>
          <SingleStockLadder
            policy={selectedPolicy.singleStock}
            currentWeight={topPosition.weight}
            symbol={topPosition.symbol}
          />
        </SignalPanel>
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
            {blockers.slice(0, 8).map((blocker) => (
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
            Signal also has {blocked.length} candidate ideas marked not eligible right now (insufficient history, liquidity, or risk gates). They surface again automatically when their conditions clear.
          </p>
        )}
      </SignalPanel>

    </section>
  );
}
