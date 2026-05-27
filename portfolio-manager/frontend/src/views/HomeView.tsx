import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { AlertTriangle, BrainCircuit, Database, Import, ListChecks, MessageCircle, ShieldCheck } from "lucide-react";
import type { AdvisorRunStatus, Dashboard } from "../types";
import { money, number, pct, shortDateTime, signedMoney, signedPct, titleCase } from "../lib/format";
import { primaryDecision, type AppTab } from "../lib/viewModels";
import { PortfolioTrendChart } from "../components/visuals/PortfolioTrendChart";
import { DecisionReceiptCard, trimMathFromPacket } from "../components/advisor/DecisionReceiptCard";
import { RunConsole } from "../components/advisor/RunConsole";
import { CompareRunDrawer } from "../components/advisor/CompareRunDrawer";
import { AdvisoryTicket } from "../components/advisor/AdvisoryTicket";
import { Badge, CommandButton, SignalPanel, StatusDot } from "../components/ui/Primitives";
import { savePacketSnapshot } from "../lib/packetSnapshot";
import { pickSelectedPolicy } from "../components/policy/SelectedPolicyCard";
import { DataQualityPill } from "../components/data/DataQualityPill";

function decisionTone(decision?: string) {
  if (!decision) return "neutral";
  if (["Trim", "Rotate", "Avoid"].includes(decision)) return "danger";
  if (decision === "Wait For Data") return "attention";
  if (["Add", "Stagger Entry"].includes(decision)) return "live";
  return "good";
}

function firstActionLabel(dashboard: Dashboard) {
  const first = dashboard.advisor_packet?.recommendedPriority?.firstAction;
  if (!first) return null;
  const decision =
    first.action === "TRIM" ? "Trim" : first.action === "ADD" ? "Add" : first.action === "STAGGER_ENTRY" ? "Stagger Entry" : first.action === "WAIT_FOR_DATA" ? "Wait For Data" : "Hold";
  return { symbol: first.symbol, decision };
}

function receiptMath(dashboard: Dashboard) {
  return trimMathFromPacket(dashboard);
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
  onRunAdvisor,
  onDeepReview
}: {
  dashboard: Dashboard;
  busy: boolean;
  activeRun: AdvisorRunStatus | null;
  onNavigate: (tab: AppTab) => void;
  onAsk: (question?: string) => void;
  onRunAdvisor: () => void;
  onDeepReview?: () => void;
}) {
  const decision = primaryDecision(dashboard);
  const [compareOpen, setCompareOpen] = useState(false);
  const currentPacket = dashboard.advisor_packet;
  const currentHash = currentPacket?.packetHash ?? "";
  useEffect(() => {
    if (currentPacket && currentHash) {
      savePacketSnapshot(currentPacket);
    }
  }, [currentHash, currentPacket]);
  const real = dashboard.real_portfolio;
  const hasHoldings = Boolean(real && real.positions.length > 0);
  const advisorDecision = dashboard.advisor_decision;
  const topAction = firstActionLabel(dashboard);
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
      : "Run the advisor to generate today's command.");
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
          <Badge tone="watch">Advisory-only</Badge>
        </div>
        <div className="mission-control-command">
          <span>Today's command</span>
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
          <span className="mission-pill neutral" role="listitem">
            <i />
            <strong>No order has been placed</strong>
          </span>
        </div>
      </header>

      <section className="mission-control-grid">
        <motion.div
          className="mission-first-action"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32 }}
          data-testid="advisor-brief"
        >
          {firstAction ? (
            <AdvisoryTicket
              action={firstAction}
              policy={selectedPolicy}
              onAsk={onAsk}
            />
          ) : (
            <SignalPanel className="mission-first-action-empty">
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
                <CommandButton icon={MessageCircle} variant="ghost" onClick={() => onAsk("Summarize what Signal PM thinks I should do now and why.")}>
                  Ask Signal
                </CommandButton>
              </div>
            </SignalPanel>
          )}
        </motion.div>

        <SignalPanel className="mission-decision-receipt" testId="advisor-decision-summary">
          <div className="panel-label-row">
            <span>Decision receipt</span>
            <Badge tone={advisorDecision?.status === "success" ? "live" : advisorDecision ? "watch" : "neutral"}>
              {advisorDecision ? titleCase(advisorDecision.status) : "Waiting"}
            </Badge>
          </div>
          <DecisionReceiptCard dashboard={dashboard} compact />
          <button className="mission-receipt-cta" onClick={() => onNavigate("actions")}>
            <Badge tone={decisionTone(topAction?.decision)}>{topAction?.decision ?? "Review"}</Badge>
            <span>Open full action detail</span>
          </button>
          {topRisk && (
            <div className="risk-callout">
              <AlertTriangle size={16} />
              <span>{topRisk.title}</span>
            </div>
          )}
        </SignalPanel>
      </section>

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
              ?? dashboard.ai_status.model_router.leadPM.model}
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

        <RunConsole
          dashboard={dashboard}
          run={activeRun}
          busy={busy}
          onRun={onRunAdvisor}
          onDeepRun={onDeepReview}
          onCompare={() => setCompareOpen(true)}
        />
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

      <CompareRunDrawer
        open={compareOpen}
        onOpenChange={setCompareOpen}
        packet={currentPacket}
      />

      {firstAction && (
        <div className="mission-mobile-bar" data-testid="mission-mobile-bar" aria-label="Today's first advisory action">
          <div>
            <strong>{titleCase(firstAction.action)} {firstAction.symbol}</strong>
            <span>
              {sizing
                ? `${money(sizing.sellValue)} est · ${pct(sizing.currentWeight)} → ${pct(sizing.postWeightCompliant || sizing.postWeight)}`
                : "Advisory-only · no order placed"}
            </span>
          </div>
          <button type="button" onClick={() => onNavigate("actions")}>Review</button>
        </div>
      )}
    </section>
  );
}
