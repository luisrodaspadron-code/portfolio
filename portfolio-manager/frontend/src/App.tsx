import * as Tooltip from "@radix-ui/react-tooltip";
import { BrainCircuit, BriefcaseBusiness, KeyRound, ListChecks, MessageCircle, RefreshCw, ShieldAlert } from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { getAdvisorRun, getDashboard, refreshData, startAdvisorRun } from "./api";
import type { AdvisorRunStatus, Dashboard } from "./types";
import { CommandPalette, type PaletteAction } from "./components/shell/CommandPalette";
import { CommandRail, MobileDock, TopTelemetry } from "./components/shell/AppFrame";
import { HomeView } from "./views/HomeView";
import { PortfolioView } from "./views/PortfolioView";
import { ActionsView } from "./views/ActionsView";
import { ConnectionsView } from "./views/ConnectionsView";
import { RiskView } from "./views/RiskView";
import { AskSignalPanel } from "./components/advisor/AskSignalPanel";
import { primaryDecision, telemetryState, type AppTab } from "./lib/viewModels";

type Notice = { tone: "success" | "error"; message: string } | null;

export function App() {
  const [activeTab, setActiveTab] = useState<AppTab>("now");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [activeRun, setActiveRun] = useState<AdvisorRunStatus | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotQuestion, setCopilotQuestion] = useState<string | undefined>();
  const [copilotRunning, setCopilotRunning] = useState(false);

  async function load() {
    const data = await getDashboard();
    setDashboard(data);
  }

  useEffect(() => {
    load().catch((error) => setNotice({ tone: "error", message: error instanceof Error ? error.message : "Unable to load dashboard" }));
  }, []);

  useEffect(() => {
    if (!activeRunId) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const run = await getAdvisorRun(activeRunId);
        if (cancelled) return;
        setActiveRun(run);
        if (run.status !== "running") {
          setBusy(false);
          setBusyLabel("");
          setActiveRunId(null);
          await load();
          setNotice({
            tone: run.status === "failed" ? "error" : "success",
            message: run.status === "failed"
              ? run.error || run.fallback_reason || "Advisor cycle could not finish. The last valid dashboard is still available."
              : "Advisor cycle complete"
          });
        }
      } catch (error) {
        if (!cancelled) {
          setBusy(false);
          setBusyLabel("");
          setActiveRunId(null);
          setNotice({ tone: "error", message: error instanceof Error ? error.message : "Unable to read advisor progress" });
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 700);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeRunId]);

  async function act(label: string, action: () => Promise<unknown>) {
    setBusy(true);
    setBusyLabel(label);
    setNotice(null);
    try {
      const result = await action();
      await load();
      if (result && typeof result === "object" && "status" in result && (result as { status?: string }).status === "failed") {
        const failedRun = result as { error?: string; summary?: { fallback_reason?: string } };
        setNotice({ tone: "error", message: failedRun.error || failedRun.summary?.fallback_reason || `${label} could not finish. The last valid dashboard is still available.` });
        return;
      }
      const advisorStatus =
        result && typeof result === "object" && "summary" in result
          ? (result as { summary?: { advisor_decision_status?: string; fallback_reason?: string } }).summary?.advisor_decision_status
          : "";
      const fallbackReason =
        result && typeof result === "object" && "summary" in result
          ? (result as { summary?: { fallback_reason?: string } }).summary?.fallback_reason
          : "";
      setNotice({
        tone: "success",
        message: advisorStatus && advisorStatus !== "success"
          ? `${label} finished with quant fallback. ${fallbackReason || "Review the run receipt for details."}`
          : `${label} complete`
      });
    } catch (error) {
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Action failed" });
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  async function runAdvisorFlow() {
    setBusy(true);
    setBusyLabel("Advisor cycle");
    setNotice(null);
    try {
      const started = await startAdvisorRun();
      setActiveRunId(started.run_id);
      setActiveRun({
        run_id: started.run_id,
        status: started.status,
        trigger: "manual",
        started_at: started.started_at,
        finished_at: null,
        current_step: null,
        completed_steps: [],
        steps: [],
        events: [],
        records_processed: 0,
        fallback_reason: "",
        model: "",
        reasoning: dashboard?.ai_status.model_router.leadPM.reasoningEffort ?? "medium",
        token_usage: 0,
        universe_size: dashboard?.universe_status.included_assets ?? 0,
        priced_symbols: dashboard?.data_freshness.live_price_symbols ?? 0,
        sec_used: false,
        fred_used: false,
        decision_hash: "",
        summary: {},
        error: "",
      });
    } catch (error) {
      setBusy(false);
      setBusyLabel("");
      setNotice({ tone: "error", message: error instanceof Error ? error.message : "Unable to start advisor cycle" });
    }
  }

  async function reloadWithNotice(message: string) {
    await load();
    setNotice({ tone: "success", message });
  }

  function showError(message: string) {
    setNotice({ tone: "error", message });
  }

  const telemetry = useMemo(() => (dashboard ? telemetryState(dashboard) : []), [dashboard]);
  const displayedTelemetry = useMemo(
    () =>
      copilotRunning
        ? telemetry.map((item) =>
            item.label === "AI"
              ? { ...item, value: "Running", tone: "live" as const, detail: "Ask Signal is reading the latest advisor packet." }
              : item
          )
        : busy
          ? telemetry.map((item) =>
              item.label === "AI"
                ? { ...item, value: "Running", tone: "live" as const, detail: "Signal PM is running a local advisor workflow." }
                : item
            )
        : telemetry,
    [busy, copilotRunning, telemetry]
  );
  const decision = useMemo(() => (dashboard ? primaryDecision(dashboard) : null), [dashboard]);
  const screenContext = activeTab;
  const paletteActions = useMemo<PaletteAction[]>(
    () => [
      { id: "import", label: "Import holdings", detail: "Load real portfolio CSV", icon: BriefcaseBusiness, run: () => setActiveTab("portfolio") },
      { id: "connect", label: "Connect OpenAI", detail: "Add or test AI key", icon: KeyRound, run: () => setActiveTab("connections") },
      { id: "advisor", label: "Run advisor", detail: "Refresh robo advisor cycle", icon: BrainCircuit, run: () => void runAdvisorFlow() },
      { id: "risks", label: "Review risks", detail: "Open the visual risk cockpit", icon: ShieldAlert, run: () => setActiveTab("risks") },
      { id: "actions", label: "Review actions", detail: "Open advisor insight cards", icon: ListChecks, run: () => setActiveTab("actions") },
      { id: "ask", label: "Ask Signal", detail: "Ask a follow-up about the advisor packet", icon: MessageCircle, run: () => openCopilot() },
      { id: "refresh", label: "Refresh data", detail: "Run data refresh", icon: RefreshCw, run: () => void act("Refresh", refreshData) }
    ],
    []
  );

  function openCopilot(question?: string) {
    setCopilotQuestion(question);
    setCopilotOpen(true);
  }

  function openDecision(tab: AppTab) {
    setActiveTab(tab);
  }

  if (!dashboard) {
    return (
      <main className="signal-loading">
        <div className="loading-orbit" />
        <strong>Signal PM</strong>
        <span>Loading local command workspace</span>
      </main>
    );
  }

  return (
    <Tooltip.Provider delayDuration={120}>
      <div className="signal-app">
        <CommandRail activeTab={activeTab} onTab={setActiveTab} />
        <main className="signal-workspace">
          <TopTelemetry
            items={displayedTelemetry}
            busy={busy}
            onOpenPalette={() => setPaletteOpen(true)}
            primaryLabel={decision?.primaryLabel ?? "Open Now"}
            onPrimaryAction={() => openDecision(decision?.primaryTab ?? "now")}
          />
          {busy && <div className="process-banner compact" data-testid="process-banner">{busyLabel || "Signal PM is working"} · {activeRun?.current_step?.step ?? "Starting run"}</div>}
          {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
          {activeTab === "now" && (
            <HomeView
              dashboard={dashboard}
              busy={busy}
              onNavigate={setActiveTab}
              onAsk={openCopilot}
              activeRun={activeRun}
              onRunAdvisor={() => void runAdvisorFlow()}
            />
          )}
          {activeTab === "portfolio" && <PortfolioView dashboard={dashboard} onDone={reloadWithNotice} onError={showError} />}
          {activeTab === "risks" && <RiskView dashboard={dashboard} onAsk={openCopilot} />}
          {activeTab === "actions" && <ActionsView dashboard={dashboard} onAsk={openCopilot} />}
          {activeTab === "connections" && <ConnectionsView dashboard={dashboard} onSaved={reloadWithNotice} onError={showError} />}
        </main>
        <MobileDock activeTab={activeTab} onTab={setActiveTab} />
        <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} actions={paletteActions} />
        <AskSignalPanel
          dashboard={dashboard}
          open={copilotOpen}
          initialQuestion={copilotQuestion}
          screenContext={screenContext}
          onOpenChange={setCopilotOpen}
          onActivity={setCopilotRunning}
        />
      </div>
    </Tooltip.Provider>
  );
}
