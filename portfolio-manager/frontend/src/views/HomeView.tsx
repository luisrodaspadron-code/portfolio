import { useEffect } from "react";
import { Database, Import, ListChecks, MessageCircle } from "lucide-react";
import type { AdvisorRunStatus, Dashboard } from "../types";
import { money, number, pct, shortDateTime, signedPct, titleCase } from "../lib/format";
import { primaryDecision, type AppTab } from "../lib/viewModels";
import { PortfolioImpactPreview } from "../components/visuals/PortfolioImpactPreview";
import { trimMathFromPacket } from "../components/advisor/DecisionReceiptCard";
import { RunConsole } from "../components/advisor/RunConsole";
import { Badge, CommandButton, SignalPanel, StatusDot } from "../components/ui/Primitives";
import { savePacketSnapshot } from "../lib/packetSnapshot";
import { pickSelectedPolicy } from "../components/policy/SelectedPolicyCard";

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
  const canonicalReceipt = dashboard.advisor_packet?.decisionReceipt;
  const sizing = receiptMath(dashboard);
  const topRisk = dashboard.advisor_trace.top_risks[0];
  const nextRun = dashboard.scheduler.next_run_at;
  const answerBody = sizing
    ? "Sized from portfolio value, policy thresholds, and reference price. Actions includes staged limit guidance."
    : decision.body;

  const selectedPolicy = pickSelectedPolicy(dashboard);
  const firstAction = dashboard.advisor_packet?.recommendedPriority?.firstAction ?? null;
  const blockedCount = canonicalReceipt?.riskIncreasingActionsBlocked?.length ?? 0;
  const allowedCount = canonicalReceipt?.riskReducingActionsAllowed?.length ?? 0;
  const policyLabel = selectedPolicy?.name ?? dashboard.policy?.selectedPolicy?.name ?? titleCase(selectedPolicy?.preset ?? "balanced");
  const policyPreset = selectedPolicy?.preset ?? dashboard.policy?.selectedPolicy?.preset ?? "balanced";
  const commandCopy = firstAction?.action === "TRIM"
    ? "Repair concentration before adding risk"
    : firstAction?.action === "WAIT_FOR_DATA"
      ? "Refresh data before sizing new action"
      : firstAction
        ? "Review the first deterministic action"
        : "Run the advisor to generate the first priority";
  const dataSourceLabel = titleCase(dashboard.data_freshness.preferred_price_source || dashboard.data_freshness.provider_mode);
  const sourceModeLabel = titleCase(dashboard.data_freshness.provider_mode);
  const nextReviewLabel = nextRun ? shortDateTime(nextRun) : "Manual run anytime";

  return (
    <section className="now-view now-decision-hub screen-enter mission-control">
      <header className="mission-control-bar" data-testid="mission-control-header">
        <div className="mission-control-eyebrow">
          <strong>Now</strong>
          <Badge tone={policyPreset === "competition" ? "fail" : policyPreset === "aggressive" ? "watch" : "live"}>
            Policy · {policyLabel}
          </Badge>
        </div>
        <div className="mission-control-command">
          <h1>{commandCopy}</h1>
        </div>
        <div className="mission-control-pills" role="list">
          <span className={`mission-pill ${blockedCount ? "blocked" : "calm"}`} role="listitem">
            <i />
            <strong>{blockedCount ? "Blocked exposure" : "No active block"}</strong>
            {blockedCount > 0 && <em>{blockedCount}</em>}
          </span>
          <span className={`mission-pill ${allowedCount ? "allowed" : "calm"}`} role="listitem">
            <i />
            <strong>{allowedCount ? "Risk-reducing path" : "No risk-reducing path"}</strong>
            {allowedCount > 0 && <em>{allowedCount}</em>}
          </span>
        </div>
      </header>

      <section className="mission-context-strip" aria-label="Current portfolio context">
        <article>
          <span>Portfolio</span>
          <strong>{real ? money(real.total_value) : "Not loaded"}</strong>
          <p>{real ? `${real.positions.length} holdings · ${money(real.cash)} cash` : "Import holdings to start"}</p>
        </article>
        <article>
          <span>Risk driver</span>
          <strong>{firstAction ? firstAction.symbol : "Pending"}</strong>
          <p>{firstAction ? `${pct(firstAction.currentWeight ?? 0)} current · ${pct(firstAction.targetWeight ?? 0)} target` : "No packet action yet"}</p>
        </article>
        <article>
          <span>Data</span>
          <strong>{sourceModeLabel}</strong>
          <p>{dataSourceLabel} · {dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols} priced symbols</p>
        </article>
        <article>
          <span>Next review</span>
          <strong>{nextReviewLabel}</strong>
          <p>{dashboard.advisor_packet?.workflowAudit?.status ? titleCase(dashboard.advisor_packet.workflowAudit.status) : "Workflow ready"}</p>
        </article>
      </section>

      <SignalPanel className="mission-action-card" testId="advisor-brief">
        {firstAction ? (
          <>
            <div className="mission-action-main">
              <span>Recommended action</span>
              <h2>{titleCase(firstAction.action)} {firstAction.symbol}</h2>
              <p>{answerBody}</p>
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
              {topRisk && <p>Primary risk: {topRisk.title}</p>}
              <small>Quote guardrails and staged sizing live in Actions.</small>
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

      <section className="mission-insight-grid" aria-label="Impact and latest changes">
        {firstAction && real && (
          <SignalPanel className="mission-impact-panel">
            <PortfolioImpactPreview
              portfolio={real}
              action={firstAction}
              policy={selectedPolicy}
              riskBreachCount={{
                before: currentPacket.portfolioRisk.issueCount,
                after: Math.max(0, currentPacket.portfolioRisk.issueCount - 1),
              }}
            />
          </SignalPanel>
        )}
        <SignalPanel className="what-changed-panel mission-changes-panel">
          <div className="panel-label-row">
            <span>What changed</span>
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
      </section>

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

    </section>
  );
}
