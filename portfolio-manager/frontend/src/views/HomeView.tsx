import { useEffect } from "react";
import { BrainCircuit, Database, Import, ListChecks, MessageCircle, ShieldCheck } from "lucide-react";
import type { AdvisorRunStatus, Dashboard } from "../types";
import { modelRouteLabel, money, number, pct, shortDateTime, signedPct, titleCase } from "../lib/format";
import { primaryDecision, type AppTab } from "../lib/viewModels";
import { PortfolioImpactPreview } from "../components/visuals/PortfolioImpactPreview";
import { DecisionMap } from "../components/visuals/DecisionMap";
import { trimMathFromPacket } from "../components/advisor/DecisionReceiptCard";
import { RunConsole } from "../components/advisor/RunConsole";
import { Badge, CommandButton, SignalPanel, StatusDot } from "../components/ui/Primitives";
import { savePacketSnapshot } from "../lib/packetSnapshot";
import { pickSelectedPolicy } from "../components/policy/SelectedPolicyCard";
import { DataQualityPill } from "../components/data/DataQualityPill";

function receiptMath(dashboard: Dashboard) {
  return trimMathFromPacket(dashboard);
}

function changedItems(dashboard: Dashboard) {
  const latestProvider = dashboard.data_freshness.latest_provider_refresh;
  const trend = dashboard.portfolio_trend;
  return [
    {
      label: "Portfolio move",
      value: trend.points.length >= 2 ? `${signedPct(trend.day_change_pct)} ${trend.latest_change_label}` : "Trend building",
      body: trend.points.length >= 2 ? `${signedPct(trend.day_change_pct)} day · ${signedPct(trend.week_change_pct)} week` : trend.source_note,
      tone: trend.points.length >= 2 ? (trend.day_change >= 0 ? "live" : "fail") : "watch"
    },
    {
      label: "Risk state",
      value: dashboard.decision_packet_status.risk_breaches ? `${dashboard.decision_packet_status.risk_breaches} review` : "Clear",
      body: dashboard.real_portfolio?.stress.warnings[0] ?? "No hard-rule breach in the current packet.",
      tone: dashboard.decision_packet_status.risk_breaches ? "fail" : "live"
    },
    {
      label: "Data update",
      value: latestProvider ? titleCase(latestProvider.status) : titleCase(dashboard.data_freshness.provider_mode),
      body: latestProvider ? latestProvider.message || `${latestProvider.records} records from ${titleCase(latestProvider.provider)}.` : "No provider refresh has run yet.",
      tone: latestProvider?.status === "failed" ? "fail" : latestProvider?.status === "partial" ? "watch" : dashboard.data_freshness.provider_mode === "live" ? "live" : "watch"
    },
    {
      label: "AI review",
      value: dashboard.advisor_decision ? titleCase(dashboard.advisor_decision.status) : titleCase(dashboard.ai_activity),
      body: dashboard.advisor_decision?.fallback_reason || dashboard.ai_status.user_message || dashboard.ai_status.message,
      tone: dashboard.advisor_decision?.status === "success" ? "live" : dashboard.ai_status.state === "error" ? "watch" : dashboard.ai_status.configured ? "live" : "watch"
    }
  ];
}

export function HomeView({
  dashboard,
  busy,
  activeRun,
  onNavigate,
  onAsk,
  onRunAdvisor,
  onCompareOpenChange,
}: {
  dashboard: Dashboard;
  busy: boolean;
  activeRun: AdvisorRunStatus | null;
  onNavigate: (tab: AppTab) => void;
  onAsk: (question?: string) => void;
  onRunAdvisor: () => void;
  onCompareOpenChange?: (open: boolean) => void;
}) {
  const decision = primaryDecision(dashboard);
  const currentPacket = dashboard.advisor_packet;
  const setCompareOpen = onCompareOpenChange ?? (() => undefined);
  const currentHash = currentPacket?.packetHash ?? "";
  useEffect(() => {
    if (currentPacket && currentHash) {
      savePacketSnapshot(currentPacket);
    }
  }, [currentHash, currentPacket]);
  const real = dashboard.real_portfolio;
  const hasHoldings = Boolean(real && real.positions.length > 0);
  const advisorDecision = dashboard.advisor_decision;
  const canonicalHeadline = dashboard.advisor_packet?.recommendedPriority?.headline;
  const canonicalReceipt = dashboard.advisor_packet?.decisionReceipt;
  const sizing = receiptMath(dashboard);
  const trend = dashboard.portfolio_trend;
  const topRisk = dashboard.advisor_trace.top_risks[0];
  const hasTrendHistory = trend.points.length >= 2;
  const lastAiRun = advisorDecision?.created_at ?? dashboard.ai_status.last_run?.finished_at;
  const nextRun = dashboard.scheduler.next_run_at;
  const answerBody = sizing
    ? `${sizing.symbol} is ${pct(sizing.currentWeight)} of the portfolio versus the ${pct(sizing.targetWeight)} policy target. Repair concentration before considering new exposure.`
    : decision.body;

  const selectedPolicy = pickSelectedPolicy(dashboard);
  const firstAction = dashboard.advisor_packet?.recommendedPriority?.firstAction ?? null;
  const blockedCount = canonicalReceipt?.riskIncreasingActionsBlocked?.length ?? 0;
  const allowedCount = canonicalReceipt?.riskReducingActionsAllowed?.length ?? 0;
  const policyLabel = selectedPolicy?.name ?? dashboard.policy?.selectedPolicy?.name ?? titleCase(selectedPolicy?.preset ?? "balanced");
  const policyPreset = selectedPolicy?.preset ?? dashboard.policy?.selectedPolicy?.preset ?? "balanced";
  const today = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date());
  const commandCopy = canonicalReceipt?.summary
    ?? canonicalHeadline
    ?? (firstAction
      ? `${titleCase(firstAction.action)} ${firstAction.symbol} before increasing single-stock exposure.`
      : "Run the advisor to generate the first priority.");
  const dataLabel = titleCase(dashboard.data_freshness.provider_mode);

  return (
    <section className="now-view now-decision-hub screen-enter mission-control">
      <header className="mission-control-bar" data-testid="mission-control-header">
        <div className="mission-control-eyebrow">
          <strong>SIGNAL PRIME</strong>
          <span>{today}</span>
          <Badge tone={policyPreset === "competition" ? "fail" : policyPreset === "aggressive" ? "watch" : "live"}>
            Policy · {policyLabel}
          </Badge>
        </div>
        <div className="mission-control-command">
          <span>Now</span>
          <h1>{commandCopy}</h1>
        </div>
        <div className="mission-control-pills" role="list">
          <span className={`mission-pill ${blockedCount ? "blocked" : "calm"}`} role="listitem">
            <i />
            <strong>Risk-increasing trades {blockedCount ? "blocked" : "open"}</strong>
            {blockedCount > 0 && <em>{blockedCount}</em>}
          </span>
          <span className={`mission-pill ${allowedCount ? "allowed" : "calm"}`} role="listitem">
            <i />
            <strong>Risk-reducing trades {allowedCount ? "allowed" : "no candidates"}</strong>
            {allowedCount > 0 && <em>{allowedCount}</em>}
          </span>
        </div>
      </header>

      <SignalPanel className="mission-action-card" testId="advisor-brief">
        {firstAction ? (
          <>
            <div className="mission-action-main">
              <span>Recommended action</span>
              <h2>{titleCase(firstAction.action)} {firstAction.symbol}</h2>
              <p>{firstAction.explanation}</p>
            </div>
            {sizing && (
              <div className="mission-action-metrics">
                <div><span>Current</span><strong>{pct(sizing.currentWeight)}</strong></div>
                <div><span>Target</span><strong>{pct(sizing.targetWeight)}</strong></div>
                <div><span>Trim</span><strong>{money(sizing.sellValue)}</strong></div>
                <div><span>Shares</span><strong>{number(sizing.wholeSharesCompliant)}</strong><small>whole</small></div>
                {sizing.priceUsed > 0 && <div><span>Price</span><strong>{money(sizing.priceUsed)}</strong></div>}
              </div>
            )}
            <div className="mission-action-side">
              <button type="button" onClick={() => onNavigate("actions")}>Open action plan</button>
              {topRisk && <p>{topRisk.title}</p>}
              <small>{nextRun ? `Next review ${shortDateTime(nextRun)}` : "Run again anytime."}</small>
            </div>
          </>
        ) : (
          <div className="mission-first-action-empty">
            <div className="command-kicker">
              <StatusDot tone={decision.tone} />
              <span>{decision.eyebrow}</span>
              <Badge tone={decision.tone}>{decision.confidence}</Badge>
            </div>
            <h2>{decision.title}</h2>
            <p>{answerBody}</p>
            <div className="now-primary-row">
              <CommandButton
                icon={decision.primaryTab === "portfolio" ? Import : decision.primaryTab === "connections" ? Database : ListChecks}
                variant="primary"
                data-testid="home-primary-action"
                onClick={() => onNavigate(decision.primaryTab)}
              >
                {decision.primaryLabel}
              </CommandButton>
              <CommandButton icon={MessageCircle} variant="ghost" onClick={() => onAsk("Summarize what Signal Prime thinks I should do now and why.")}>
                Ask Signal
              </CommandButton>
            </div>
          </div>
        )}
      </SignalPanel>

      <section className="mission-telemetry-strip" data-testid="mission-telemetry">
        <article>
          <span>Portfolio</span>
          <strong>{hasHoldings && real ? money(real.total_value) : "Needs import"}</strong>
          <p>
            {hasHoldings && real
              ? `${real.positions.length} holdings · ${hasTrendHistory ? signedPct(trend.day_change_pct) + " day" : "trend building"}`
              : "Import a portfolio to unlock the advisor."}
          </p>
        </article>
        <article>
          <span>Data quality</span>
          <DataQualityPill freshness={dashboard.data_freshness.provider_mode === "live" ? "live" : dashboard.data_freshness.provider_mode === "partial" ? "partial" : dashboard.data_freshness.provider_mode === "sample" ? "sample" : "recent"} compact />
          <p>
            {number(dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols)} priced symbols · {dataLabel}
          </p>
        </article>
        <article>
          <span>AI route</span>
          <strong>
            {dashboard.advisor_packet?.decisionReceipt?.modelRoute
              ? modelRouteLabel(dashboard.advisor_packet.decisionReceipt.modelRoute)
              : dashboard.ai_status.model_router.leadPM.model}
          </strong>
          <p>
            {titleCase(dashboard.advisor_packet?.decisionReceipt?.reasoningEffort
              ?? dashboard.ai_status.model_router.leadPM.reasoningEffort)} reasoning
            {lastAiRun ? ` · ${shortDateTime(lastAiRun)}` : ""}
          </p>
        </article>
        <article>
          <span>Policy</span>
          <strong>{policyLabel}</strong>
          <p>
            Cap ladder · {selectedPolicy ? pct(selectedPolicy.singleStock.hardBuyBlock) : "—"} hard buy block · {nextRun ? shortDateTime(nextRun) : "no scheduled run"}
          </p>
        </article>
      </section>

      {firstAction && real && (
        <details className="portfolio-impact-disclosure">
          <summary>
            <span>Portfolio impact preview</span>
            <Badge tone="neutral">Before / after</Badge>
          </summary>
          <PortfolioImpactPreview
            portfolio={real}
            action={firstAction}
            policy={selectedPolicy}
            riskBreachCount={{
              before: currentPacket.portfolioRisk.issueCount,
              after: Math.max(0, currentPacket.portfolioRisk.issueCount - 1),
            }}
          />
        </details>
      )}

      <SignalPanel className="what-changed-panel">
        <div className="panel-label-row">
          <span>What changed since last review</span>
          <Badge tone={dashboard.data_freshness.provider_mode === "live" ? "live" : "watch"}>{titleCase(dashboard.data_freshness.provider_mode)}</Badge>
        </div>
        <div className="change-grid">
          {changedItems(dashboard).map((item) => (
            <article key={item.label} className={item.tone}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </SignalPanel>

      <details className="now-run-disclosure" open={busy || activeRun?.status === "running"}>
        <summary>
          <span>Advisor run console</span>
          <Badge tone={busy || activeRun?.status === "running" ? "live" : activeRun?.status === "failed" ? "fail" : "neutral"}>
            {busy || activeRun?.status === "running" ? "Running" : activeRun ? titleCase(activeRun.status) : "Optional"}
          </Badge>
        </summary>
        <RunConsole
          dashboard={dashboard}
          run={activeRun}
          busy={busy}
          onRun={onRunAdvisor}
          onCompare={() => setCompareOpen(true)}
        />
      </details>

      <details className="now-audit-drawer">
        <summary>
          <span>Technical details</span>
          <Badge tone="neutral">{dashboard.decision_packet_status.tool_count} tools</Badge>
        </summary>
        <SignalPanel className="decision-map-panel">
          <div className="panel-label-row">
            <span>Decision map</span>
            <Badge tone="neutral">Deterministic flow</Badge>
          </div>
          <DecisionMap dashboard={dashboard} />
        </SignalPanel>
        <section className="now-trace-grid">
          <SignalPanel className="trace-card compact">
            <div className="trace-icon-row">
              <ShieldCheck size={17} />
              <span>Positions analyzed</span>
            </div>
            <strong>{dashboard.advisor_trace.holdings_analyzed.count} holdings</strong>
            <p>{dashboard.advisor_trace.holdings_analyzed.top_holding ? `Largest exposure: ${dashboard.advisor_trace.holdings_analyzed.top_holding.symbol}.` : "Import holdings to turn this into a real portfolio review."}</p>
          </SignalPanel>
          <SignalPanel className="trace-card compact">
            <div className="trace-icon-row">
              <Database size={17} />
              <span>Data used</span>
            </div>
            <strong>{number(dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols)} priced symbols</strong>
            <p>{dashboard.data_freshness.provider_mode === "live" ? `${titleCase(dashboard.data_freshness.preferred_price_source)} is preferred. SEC facts are used when company coverage exists.` : "Sample mode downgrades confidence until live market data is connected."}</p>
          </SignalPanel>
          <SignalPanel className="trace-card compact">
            <div className="trace-icon-row">
              <BrainCircuit size={17} />
              <span>Decision engine</span>
            </div>
            <strong>{dashboard.decision_packet_status.tool_count} quant tools</strong>
            <p>Universe, prices, factors, sizing, risk gates, macro, SEC facts, and AI review are tied to the same packet.</p>
          </SignalPanel>
        </section>
      </details>

    </section>
  );
}
