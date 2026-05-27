import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  Clock3,
  Copy,
  Database,
  Download,
  FileText,
  GitCompare,
  Receipt,
  ShieldCheck,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import type { AdvisorRunEvent, AdvisorRunStatus, Dashboard } from "../../types";
import { number, shortDateTime, titleCase } from "../../lib/format";
import { Badge, CommandButton, SignalPanel } from "../ui/Primitives";

type ViewMode = "compact" | "verbose" | "errors";

function eventTone(status: string) {
  if (status === "success") return "live";
  if (status === "warning") return "watch";
  if (status === "error" || status === "failed") return "fail";
  if (status === "running") return "live";
  return "neutral";
}

function iconFor(step: string, phase?: string) {
  const key = `${step} ${phase ?? ""}`;
  if (/price|data|provider/i.test(key)) return Database;
  if (/risk|gate|quant/i.test(key)) return ShieldCheck;
  if (/ai|llm|decision|receipt|specialist/i.test(key)) return BrainCircuit;
  if (/backtest|factor|universe|candidate/i.test(key)) return Activity;
  return Clock3;
}

function elapsed(start?: string, timestamp?: string) {
  if (!start || !timestamp) return "00:00.0";
  const delta = Math.max(0, new Date(timestamp).getTime() - new Date(start).getTime());
  const seconds = delta / 1000;
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds - minutes * 60).toFixed(1).padStart(4, "0");
  return `${String(minutes).padStart(2, "0")}:${remainder}`;
}

function filterEvents(events: AdvisorRunEvent[], mode: ViewMode): AdvisorRunEvent[] {
  if (mode === "errors") {
    return events.filter((event) => event.status === "warning" || event.status === "error" || event.status === "failed");
  }
  if (mode === "compact") {
    return events.filter((event) => event.status !== "running");
  }
  return events;
}

async function copyAuditPayload(currentRun: AdvisorRunStatus | null, dashboard: Dashboard) {
  const payload = JSON.stringify(
    {
      run: currentRun,
      advisor_packet: dashboard.advisor_packet,
      generated_at: new Date().toISOString(),
    },
    null,
    2,
  );
  await navigator.clipboard?.writeText(payload);
}

async function copyTerminalLog(events: AdvisorRunEvent[], startedAt?: string) {
  const lines = events.map((event) => {
    const stamp = elapsed(startedAt, event.timestamp);
    return `${stamp}  ${event.phase.padEnd(11)} ${event.status.padEnd(11)} ${event.title} · ${event.detail}`;
  });
  const text = ["signal-prime run --mode balanced", ...lines].join("\n");
  await navigator.clipboard?.writeText(text);
}

function downloadReceipt(currentRun: AdvisorRunStatus | null, dashboard: Dashboard) {
  const payload = JSON.stringify(
    {
      receipt: dashboard.advisor_packet?.decisionReceipt,
      packetHash: dashboard.advisor_packet?.packetHash,
      runId: currentRun?.run_id ?? null,
      timestamp: new Date().toISOString(),
    },
    null,
    2,
  );
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `signal-prime-receipt-${currentRun?.run_id ?? "latest"}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function RunConsole({
  dashboard,
  run,
  busy,
  onRun,
  onDeepRun,
  onCompare,
  onViewPacket,
  onViewReceipt,
}: {
  dashboard: Dashboard;
  run: AdvisorRunStatus | null;
  busy: boolean;
  onRun: () => void;
  onDeepRun?: () => void;
  onCompare?: () => void;
  onViewPacket?: () => void;
  onViewReceipt?: () => void;
}) {
  const [mode, setMode] = useState<ViewMode>("verbose");

  const currentRun = run ?? dashboard.advisor_run_status;
  const allEvents = currentRun?.events ?? [];
  const events = useMemo(() => filterEvents(allEvents, mode), [allEvents, mode]);
  const finished = currentRun?.status && currentRun.status !== "running";
  const hasRun = Boolean(currentRun);
  const model = hasRun
    ? currentRun?.model || "Pending"
    : dashboard.advisor_packet?.decisionReceipt?.model ?? dashboard.ai_status.model_router.leadPM.model;
  const reasoning = hasRun
    ? currentRun?.reasoning || "medium"
    : dashboard.advisor_packet?.decisionReceipt?.reasoningEffort ?? dashboard.ai_status.model_router.leadPM.reasoningEffort;
  const tokens = hasRun ? currentRun?.token_usage ?? 0 : dashboard.advisor_decision?.total_tokens ?? 0;
  const universeSize = hasRun ? currentRun?.universe_size ?? 0 : dashboard.universe_status.included_assets;
  const priced = hasRun
    ? currentRun?.priced_symbols ?? 0
    : dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols;
  const idleSummary =
    dashboard.advisor_packet?.recommendedPriority?.headline ??
    dashboard.advisor_packet?.decisionReceipt?.summary ??
    "Run the advisor to create a fresh portfolio decision.";

  const eventTerminal = (
    <div className={`run-event-terminal mode-${mode}`} aria-label="Advisor run events" role="log">
      <header className="run-event-shell-line">
        <span>signal-prime run --mode {dashboard.policy?.selectedPolicy?.preset ?? "balanced"}</span>
      </header>
      <AnimatePresence initial={false}>
        {events.length ? (
          events.map((event) => {
            const Icon = iconFor(event.title, event.phase);
            const metricText = event.metrics?.records
              ? `${number(Number(event.metrics.records))} records`
              : titleCase(event.phase);
            const isActive = event.status === "running";
            return (
              <motion.article
                className={`${event.status} ${isActive ? "is-active" : ""}`}
                key={`${event.eventId ?? event.title}-${event.timestamp}-${event.phase}`}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
              >
                <span className="run-event-time">{elapsed(currentRun?.started_at, event.timestamp)}</span>
                <span className="run-event-phase">{event.phase || "step"}</span>
                <span className="run-event-status">{event.status}</span>
                <Icon size={14} aria-hidden="true" />
                <div>
                  <strong>{event.title}</strong>
                  <p>{event.detail}</p>
                </div>
                <span className="run-event-metric">{metricText}</span>
                <Badge tone={eventTone(event.status)}>{titleCase(event.status)}</Badge>
                {isActive && <span className="run-cursor" aria-hidden="true" />}
              </motion.article>
            );
          })
        ) : (
          <div className="run-event-empty">
            <Clock3 size={18} />
            <div>
              <strong>{busy ? "Waiting for first lifecycle event…" : "No advisor cycle has run yet."}</strong>
              <p>
                {mode === "errors"
                  ? "No warnings or errors recorded. Switch to verbose to see lifecycle events."
                  : "Run the advisor to see real lifecycle events from universe, prices, risk gates, specialists, and receipt creation."}
              </p>
            </div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );

  return (
    <SignalPanel className={`run-console terminal-style ${busy ? "running" : ""}`} testId="run-console">
      <div className="run-console-head">
        <div>
          <span>Run Console</span>
          <h2>{busy ? currentRun?.current_step?.step ?? "Advisor is building the packet" : "Latest advisor cycle"}</h2>
          <p>
            {busy
              ? currentRun?.current_step?.message ?? "Signal PM is checking data, scoring the universe, applying risk gates, and preparing the AI review."
              : idleSummary}
          </p>
        </div>
        <div className="run-console-actions">
          <CommandButton icon={BrainCircuit} variant="primary" disabled={busy} onClick={onRun}>
            {busy ? "Running" : "Run advisor"}
          </CommandButton>
          {onDeepRun && (
            <CommandButton icon={ShieldCheck} variant="secondary" disabled={busy} onClick={onDeepRun}>
              Deep competition review
            </CommandButton>
          )}
          {onCompare && (
            <CommandButton icon={GitCompare} variant="secondary" onClick={onCompare}>
              Compare previous
            </CommandButton>
          )}
        </div>
      </div>

      <div className="run-terminal-toolbar" role="toolbar" aria-label="Run console controls">
        <div className="run-terminal-modes" role="tablist">
          {(["compact", "verbose", "errors"] as ViewMode[]).map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              className={mode === option ? "active" : ""}
              aria-selected={mode === option}
              onClick={() => setMode(option)}
            >
              {titleCase(option)}
              {option === "errors" && <AlertTriangle size={11} aria-hidden="true" />}
            </button>
          ))}
        </div>
        <div className="run-terminal-extras">
          {onViewPacket && (
            <CommandButton icon={FileText} variant="quiet" onClick={onViewPacket}>
              View packet
            </CommandButton>
          )}
          {onViewReceipt && (
            <CommandButton icon={Receipt} variant="quiet" onClick={onViewReceipt}>
              View receipt
            </CommandButton>
          )}
          <CommandButton icon={Copy} variant="quiet" onClick={() => copyTerminalLog(events, currentRun?.started_at)}>
            Copy log
          </CommandButton>
          <CommandButton icon={Copy} variant="quiet" onClick={() => copyAuditPayload(currentRun, dashboard)}>
            Copy audit JSON
          </CommandButton>
          <CommandButton icon={Download} variant="quiet" onClick={() => downloadReceipt(currentRun, dashboard)}>
            Download receipt
          </CommandButton>
        </div>
      </div>

      {eventTerminal}

      <details className="run-audit-details">
        <summary>
          <span>{finished ? "View final receipt" : "View run data"}</span>
          <Badge tone={currentRun?.status === "failed" ? "fail" : currentRun?.status === "running" ? "live" : "neutral"}>
            {currentRun ? titleCase(currentRun.status) : "Ready"}
          </Badge>
        </summary>
        <div className="run-audit-grid">
          <div>
            <span>Model</span>
            <strong>{model}</strong>
          </div>
          <div>
            <span>Reasoning</span>
            <strong>{titleCase(reasoning)}</strong>
          </div>
          <div>
            <span>Tokens</span>
            <strong>{tokens ? number(tokens) : finished ? "None recorded" : "Pending"}</strong>
          </div>
          <div>
            <span>Universe</span>
            <strong>{universeSize ? number(universeSize) : "Pending"}</strong>
          </div>
          <div>
            <span>Priced symbols</span>
            <strong>{priced ? number(priced) : "Pending"}</strong>
          </div>
          <div>
            <span>SEC/FRED</span>
            <strong>{currentRun?.sec_used || currentRun?.fred_used ? "Used" : "Check receipt"}</strong>
          </div>
          <div>
            <span>Decision hash</span>
            <strong>
              {currentRun?.decision_hash ? currentRun.decision_hash.slice(0, 10) : dashboard.advisor_packet?.packetHash?.slice(0, 10) ?? "Pending"}
            </strong>
          </div>
          <div>
            <span>Completed</span>
            <strong>{currentRun?.finished_at ? shortDateTime(currentRun.finished_at) : "Running"}</strong>
          </div>
        </div>
        {(currentRun?.fallback_reason || currentRun?.error) && (
          <p className="run-fallback">{currentRun.fallback_reason || currentRun.error}</p>
        )}
      </details>
    </SignalPanel>
  );
}
