import { Activity, BrainCircuit, CheckCircle2, Clock3, Copy, Database, ShieldCheck } from "lucide-react";
import type { AdvisorRunEvent, AdvisorRunStatus, AdvisorRunStep, Dashboard } from "../../types";
import { number, shortDateTime, titleCase } from "../../lib/format";
import { Badge, CommandButton, SignalPanel } from "../ui/Primitives";

function stepTone(status: string) {
  if (["updated", "complete", "success", "used"].includes(status)) return "live";
  if (["warning", "partial", "reused", "skipped"].includes(status)) return "watch";
  if (["failed", "error"].includes(status)) return "fail";
  return "neutral";
}

function stepClass(status: string) {
  return status === "running" ? "running" : stepTone(status);
}

function eventTone(status: string) {
  if (status === "success") return "live";
  if (status === "warning") return "watch";
  if (status === "error") return "fail";
  if (status === "running") return "live";
  return "neutral";
}

function iconFor(step: string, phase?: string) {
  const key = `${step} ${phase ?? ""}`;
  if (/price|data|provider/i.test(key)) return Database;
  if (/risk|gate|quant/i.test(key)) return ShieldCheck;
  if (/ai|llm|decision|receipt/i.test(key)) return BrainCircuit;
  if (/backtest|factor|universe|candidate/i.test(key)) return Activity;
  return Clock3;
}

function fallbackSteps(dashboard: Dashboard): AdvisorRunStep[] {
  return dashboard.advisor.summary.step_receipts ?? [];
}

function fallbackEvents(dashboard: Dashboard): AdvisorRunEvent[] {
  return fallbackSteps(dashboard).map((step) => ({
    runId: String(dashboard.advisor.last_run?.id ?? "latest"),
    timestamp: step.finished_at || step.started_at,
    phase: /price/i.test(step.step) ? "prices" : /risk/i.test(step.step) ? "risk" : /ai|decision/i.test(step.step) ? "llm" : "complete",
    status: step.status === "failed" ? "error" : step.status === "warning" || step.status === "skipped" ? "warning" : "success",
    title: step.step,
    detail: step.message,
    metrics: step.records ? { records: step.records } : undefined,
    source: step.technical_detail
  }));
}

function elapsed(start?: string, timestamp?: string) {
  if (!start || !timestamp) return "00:00.0";
  const delta = Math.max(0, new Date(timestamp).getTime() - new Date(start).getTime());
  const seconds = delta / 1000;
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds - minutes * 60).toFixed(1).padStart(4, "0");
  return `${String(minutes).padStart(2, "0")}:${remainder}`;
}

async function copyAuditPayload(currentRun: AdvisorRunStatus | null, dashboard: Dashboard) {
  const payload = JSON.stringify(
    {
      run: currentRun,
      advisor_packet: dashboard.advisor_packet,
      advisor_decision: dashboard.advisor_decision,
      generated_at: new Date().toISOString()
    },
    null,
    2
  );
  await navigator.clipboard?.writeText(payload);
}

export function RunConsole({
  dashboard,
  run,
  busy,
  onRun
}: {
  dashboard: Dashboard;
  run: AdvisorRunStatus | null;
  busy: boolean;
  onRun: () => void;
}) {
  const currentRun = run ?? dashboard.advisor_run_status;
  const steps = currentRun?.steps?.length ? currentRun.steps : fallbackSteps(dashboard);
  const events = currentRun?.events?.length ? currentRun.events : fallbackEvents(dashboard);
  const current = currentRun?.current_step;
  const finished = currentRun?.status && currentRun.status !== "running";
  const hasRun = Boolean(currentRun);
  const model = hasRun ? currentRun?.model || "Pending" : dashboard.advisor_decision?.model || dashboard.ai_status.settings.model;
  const reasoning = hasRun ? currentRun?.reasoning || "high" : (dashboard.advisor.summary as { ai_reasoning?: string }).ai_reasoning || "high";
  const tokens = hasRun ? currentRun?.token_usage ?? 0 : dashboard.advisor_decision?.total_tokens ?? 0;
  const universeSize = hasRun ? currentRun?.universe_size ?? 0 : dashboard.universe_status.included_assets;
  const priced = hasRun ? currentRun?.priced_symbols ?? 0 : dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols;
  const idleSummary = dashboard.advisor_decision?.portfolio_verdict
    ? `${dashboard.advisor_decision.portfolio_verdict.split(". ")[0]}.`
    : "Run the advisor to create a fresh portfolio decision.";
  const eventTerminal = (
    <div className="run-event-terminal" aria-label="Advisor run events">
      {(events.length ? events : [
        { runId: "pending", phase: "holdings", status: "warning", title: "Portfolio loaded", detail: "Run the advisor to load holdings.", timestamp: "", metrics: { records: dashboard.real_portfolio?.positions.length ?? 0 } },
        { runId: "pending", phase: "prices", status: "warning", title: "Prices checked", detail: "Run the advisor to refresh provider state.", timestamp: "", metrics: { records: dashboard.data_freshness.price_bars } },
        { runId: "pending", phase: "llm", status: "warning", title: "AI review generated", detail: "Run the advisor to produce the model review.", timestamp: "", metrics: {} }
      ]).map((event) => {
        const Icon = iconFor(event.title, event.phase);
        const metricText = event.metrics?.records ? `${number(Number(event.metrics.records))} records` : titleCase(event.phase);
        return (
          <article className={event.status} key={`${event.title}-${event.timestamp}`}>
            <span className="run-event-time">{elapsed(currentRun?.started_at, event.timestamp)}</span>
            <Icon size={16} />
            <div>
              <strong>{event.title}</strong>
              <p>{event.detail}</p>
            </div>
            <span className="run-event-metric">{metricText}</span>
            <Badge tone={eventTone(event.status)}>{titleCase(event.status)}</Badge>
          </article>
        );
      })}
    </div>
  );

  return (
    <SignalPanel className={`run-console ${busy ? "running" : ""}`} testId="run-console">
      <div className="run-console-head">
        <div>
          <span>Run Console</span>
          <h2>{busy ? current?.step ?? "Advisor is building the packet" : "Latest advisor cycle"}</h2>
          <p>
            {busy
              ? current?.message ?? "Signal PM is checking data, scoring the universe, applying risk gates, and preparing the AI review."
              : idleSummary}
          </p>
        </div>
        <div className="run-console-actions">
          <CommandButton icon={BrainCircuit} variant="primary" disabled={busy} onClick={onRun}>
            {busy ? "Running" : "Run advisor"}
          </CommandButton>
          <CommandButton icon={Copy} variant="secondary" onClick={() => copyAuditPayload(currentRun, dashboard)}>
            Copy audit JSON
          </CommandButton>
        </div>
      </div>

      {busy ? (
        eventTerminal
      ) : (
        <details className="run-audit-details run-events-details">
          <summary>
            <span>View lifecycle events</span>
            <Badge tone={events.length ? "live" : "watch"}>{events.length} events</Badge>
          </summary>
          {eventTerminal}
        </details>
      )}

      <details className="run-audit-details">
        <summary>
          <span>{finished ? "View final receipt" : "View run data"}</span>
          <Badge tone={currentRun?.status === "failed" ? "fail" : currentRun?.status === "running" ? "live" : "neutral"}>
            {currentRun ? titleCase(currentRun.status) : "Ready"}
          </Badge>
        </summary>
        <div className="run-audit-grid">
          <div><span>Model</span><strong>{model}</strong></div>
          <div><span>Reasoning</span><strong>{titleCase(reasoning)}</strong></div>
          <div><span>Tokens</span><strong>{tokens ? number(tokens) : finished ? "None recorded" : "Pending"}</strong></div>
          <div><span>Universe</span><strong>{universeSize ? number(universeSize) : "Pending"}</strong></div>
          <div><span>Priced symbols</span><strong>{priced ? number(priced) : "Pending"}</strong></div>
          <div><span>SEC/FRED</span><strong>{currentRun?.sec_used || currentRun?.fred_used ? "Used" : "Check receipt"}</strong></div>
          <div><span>Decision hash</span><strong>{currentRun?.decision_hash ? currentRun.decision_hash.slice(0, 10) : "Pending"}</strong></div>
          <div><span>Completed</span><strong>{currentRun?.finished_at ? shortDateTime(currentRun.finished_at) : "Running"}</strong></div>
        </div>
        {(currentRun?.fallback_reason || currentRun?.error) && <p className="run-fallback">{currentRun.fallback_reason || currentRun.error}</p>}
      </details>
    </SignalPanel>
  );
}
