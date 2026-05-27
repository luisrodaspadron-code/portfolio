import { motion } from "motion/react";
import { AlertTriangle, BrainCircuit, Database, Import, ListChecks, MessageCircle, ShieldCheck } from "lucide-react";
import type { AdvisorDecisionItem, AdvisorRunStatus, Dashboard } from "../types";
import { money, number, pct, shortDateTime, signedMoney, signedPct, titleCase } from "../lib/format";
import { primaryDecision, type AppTab } from "../lib/viewModels";
import { PortfolioTrendChart } from "../components/visuals/PortfolioTrendChart";
import { RunConsole } from "../components/advisor/RunConsole";
import { Badge, CommandButton, SignalPanel, StatusDot } from "../components/ui/Primitives";

function decisionTone(decision?: string) {
  if (!decision) return "neutral";
  if (["Trim", "Rotate", "Avoid"].includes(decision)) return "danger";
  if (decision === "Wait For Data") return "attention";
  if (["Add", "Stagger Entry"].includes(decision)) return "live";
  return "good";
}

function pickTopDecision(dashboard: Dashboard): AdvisorDecisionItem | undefined {
  const decision = dashboard.advisor_decision;
  return (
    decision?.holding_decisions.find((item) => item.decision === "Trim") ??
    decision?.opportunity_decisions.find((item) => item.decision === "Add" || item.decision === "Stagger Entry") ??
    decision?.holding_decisions.find((item) => item.decision === "Wait For Data") ??
    decision?.holding_decisions[0] ??
    decision?.opportunity_decisions[0]
  );
}

function receiptMath(dashboard: Dashboard) {
  const math = dashboard.advisor_packet?.decisionReceipt?.sizingMath;
  const first = dashboard.advisor_packet?.recommendedPriority?.firstAction;
  if (!math || !first) return null;
  return {
    symbol: first.symbol,
    currentWeight: first.currentWeight ?? 0,
    targetWeight: first.targetWeight ?? 0,
    sellValue: Number(math.estimatedSellValue ?? 0),
    exactShares: Number(math.sharesToSellExact ?? 0),
    wholeShares: Number(math.sharesToSellWhole ?? 0),
    postWeight: Number(math.estimatedPostWeight ?? 0),
    priceUsed: Number(math.priceUsed ?? 0),
    priceTimestamp: typeof math.priceTimestamp === "string" ? math.priceTimestamp : ""
  };
}

function changedItems(dashboard: Dashboard) {
  const latestProvider = dashboard.data_freshness.latest_provider_refresh;
  const trend = dashboard.portfolio_trend;
  return [
    {
      label: "Portfolio move",
      value: trend.points.length >= 2 ? `${signedMoney(trend.day_change)} ${trend.latest_change_label}` : "Trend building",
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
  onRunAdvisor
}: {
  dashboard: Dashboard;
  busy: boolean;
  activeRun: AdvisorRunStatus | null;
  onNavigate: (tab: AppTab) => void;
  onAsk: (question?: string) => void;
  onRunAdvisor: () => void;
}) {
  const decision = primaryDecision(dashboard);
  const real = dashboard.real_portfolio;
  const hasHoldings = Boolean(real && real.positions.length > 0);
  const advisorDecision = dashboard.advisor_decision;
  const topDecision = pickTopDecision(dashboard);
  const canonicalHeadline = dashboard.advisor_packet?.recommendedPriority?.headline;
  const canonicalReceipt = dashboard.advisor_packet?.decisionReceipt;
  const sizing = receiptMath(dashboard);
  const trend = dashboard.portfolio_trend;
  const topRisk = dashboard.advisor_trace.top_risks[0];
  const latestValue = trend.points.length ? trend.points[trend.points.length - 1].value : real?.total_value ?? 0;
  const hasTrendHistory = trend.points.length >= 2;
  const lastAiRun = advisorDecision?.created_at ?? dashboard.ai_status.last_run?.finished_at;
  const nextRun = dashboard.scheduler.next_run_at;
  const answerBody = sizing
    ? `${sizing.symbol} is ${pct(sizing.currentWeight)} of the portfolio versus the ${pct(sizing.targetWeight)} policy target. Repair concentration before considering new exposure.`
    : decision.body;
  const verdictSummary = sizing
    ? `${sizing.symbol} is the first action. The deterministic engine says trim toward the cap, then rerun the advisor before adding anything new.`
    : advisorDecision?.portfolio_verdict ?? "Signal needs the next advisor decision before it can summarize changes.";

  return (
    <section className="now-view now-decision-hub screen-enter">
      <div className="now-command-grid">
        <motion.div
          className="now-answer-panel"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          data-testid="advisor-brief"
        >
          <div className="command-kicker">
            <StatusDot tone={decision.tone} />
            <span>{decision.eyebrow}</span>
            <Badge tone={decision.tone}>{decision.confidence}</Badge>
          </div>
          <h1>{decision.title}</h1>
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
            <CommandButton icon={MessageCircle} variant="ghost" onClick={() => onAsk("Summarize what Signal PM thinks I should do now and why.")}>
              Ask Signal
            </CommandButton>
          </div>
          <div className="portfolio-pulse-grid">
            <div>
              <span>Portfolio</span>
              <strong>{hasHoldings && real ? money(real.total_value) : "Needs import"}</strong>
              <p>{hasHoldings && real ? `${real.positions.length} holdings tracked` : "Real holdings unlock the advisor."}</p>
            </div>
            <div>
              <span>{hasTrendHistory ? trend.latest_change_label : "Current value"}</span>
              <strong className={hasTrendHistory ? (trend.day_change >= 0 ? "positive" : "negative") : undefined}>
                {hasTrendHistory ? signedMoney(trend.day_change) : money(latestValue)}
              </strong>
              <p>{hasTrendHistory ? `${signedPct(trend.day_change_pct)} day · ${signedPct(trend.month_change_pct)} month` : "Trend needs another live/history point."}</p>
            </div>
            <div>
              <span>Next refresh</span>
              <strong>{nextRun ? shortDateTime(nextRun) : "Waiting"}</strong>
              <p>{dashboard.scheduler.enabled ? "Automatic daily review is on." : "Local scheduler is paused."}</p>
            </div>
            <div>
              <span>AI review</span>
              <strong>{advisorDecision ? titleCase(advisorDecision.status) : titleCase(dashboard.ai_activity)}</strong>
              <p>{lastAiRun ? shortDateTime(lastAiRun) : "No model review yet."}</p>
            </div>
          </div>
        </motion.div>

        <SignalPanel className="advisor-verdict-panel" testId="advisor-decision-summary">
          <div className="panel-label-row">
            <span>Should I change anything?</span>
            <Badge tone={advisorDecision?.status === "success" ? "live" : advisorDecision ? "watch" : "neutral"}>
              {advisorDecision ? titleCase(advisorDecision.status) : "Waiting"}
            </Badge>
          </div>
          <h2>{verdictSummary}</h2>
          {canonicalHeadline && (
            <div className="decision-receipt-summary">
              <span>Deterministic first action</span>
              <strong>{canonicalHeadline}</strong>
              <p>Advisory-only. No order has been placed.</p>
            </div>
          )}
          {sizing && (
            <div className="receipt-math-grid">
              <div>
                <span>Trim estimate</span>
                <strong>{money(sizing.sellValue)}</strong>
              </div>
              <div>
                <span>Shares</span>
                <strong>{sizing.exactShares.toFixed(4)}</strong>
                <p>{sizing.wholeShares ? `${sizing.wholeShares} whole-share floor` : "Fractional supported"}</p>
              </div>
              <div>
                <span>Weight</span>
                <strong>
                  {pct(sizing.currentWeight)} → {pct(sizing.targetWeight)}
                </strong>
                <p>Estimated post-action {pct(sizing.postWeight)}</p>
              </div>
              <div>
                <span>Price used</span>
                <strong>{money(sizing.priceUsed)}</strong>
                <p>{sizing.priceTimestamp ? shortDateTime(sizing.priceTimestamp) : "Reference timestamp unavailable"}</p>
              </div>
            </div>
          )}
          {topDecision ? (
            <button className={`verdict-open-action ${decisionTone(topDecision.decision)}`} onClick={() => onNavigate("actions")}>
              <Badge tone={decisionTone(topDecision.decision)}>{topDecision.decision}</Badge>
              <span>Open full {topDecision.symbol} action details</span>
            </button>
          ) : (
            <div className="verdict-open-action neutral">
              <Badge tone="watch">Setup</Badge>
              <span>Import holdings and run the advisor.</span>
            </div>
          )}
          <div className="verdict-reasons">
            {(advisorDecision?.execution_plan.length ? advisorDecision.execution_plan : ["No real trades are placed automatically.", "Signal prioritizes risk gates before upside.", "Use Ask Signal for clarification before acting."])
              .slice(0, 2)
              .map((item) => (
                <div key={item}>{item}</div>
              ))}
          </div>
          {topRisk && (
            <div className="risk-callout">
              <AlertTriangle size={16} />
              <span>{topRisk.title}</span>
            </div>
          )}
          {canonicalReceipt?.hardGatesTripped?.length ? (
            <div className="receipt-limitations">
              <span>Hard gates tripped</span>
              <p>{canonicalReceipt.hardGatesTripped.slice(0, 1).join(" ")}</p>
            </div>
          ) : null}
        </SignalPanel>
      </div>

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

      <section className="operating-grid lean">
        <SignalPanel className="trend-panel">
          <div className="panel-label-row">
            <span>Portfolio trend</span>
            <Badge tone={hasTrendHistory ? (trend.day_change >= 0 ? "live" : "fail") : "watch"}>{titleCase(trend.granularity)}</Badge>
          </div>
          <div className="trend-headline">
            <strong className={hasTrendHistory ? (trend.day_change >= 0 ? "positive" : "negative") : undefined}>
              {hasTrendHistory ? signedMoney(trend.day_change) : money(latestValue)}
            </strong>
            <span>{hasTrendHistory ? `${signedPct(trend.week_change_pct)} week · ${signedPct(trend.month_change_pct)} month` : trend.source_note}</span>
          </div>
          <PortfolioTrendChart trend={trend} />
          <p className="panel-note">{trend.source_note}</p>
        </SignalPanel>

        <RunConsole dashboard={dashboard} run={activeRun} busy={busy} onRun={onRunAdvisor} />
      </section>

      <details className="now-audit-drawer">
        <summary>
          <span>Audit the packet</span>
          <Badge tone="neutral">{dashboard.decision_packet_status.tool_count} tools</Badge>
        </summary>
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
