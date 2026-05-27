import * as Tooltip from "@radix-ui/react-tooltip";
import { BrainCircuit, BriefcaseBusiness, GitCompare, KeyRound, ListChecks, MessageCircle, RefreshCw, ShieldAlert, Trophy } from "lucide-react";
import { useMemo, useState, useEffect, useCallback } from "react";
import { getAdvisorRun, getDashboard, refreshData, runAdvisorDeepReview, runBacktest, startAdvisorRun, streamAdvisorRunEvents } from "./api";
import type { AdvisorRunStatus, Dashboard } from "./types";
import { CommandPalette, type PaletteAction } from "./components/shell/CommandPalette";
import { CommandRail, MobileDock, TopTelemetry } from "./components/shell/AppFrame";
import { HomeView } from "./views/HomeView";
import { PortfolioView } from "./views/PortfolioView";
import { ActionsView } from "./views/ActionsView";
import { ConnectionsView } from "./views/ConnectionsView";
import { RiskView } from "./views/RiskView";
import { IntelligenceView } from "./views/IntelligenceView";
import { AskSignalPanel } from "./components/advisor/AskSignalPanel";
import { CompetitionBrief } from "./components/advisor/CompetitionBrief";
import { CompareRunDrawer } from "./components/advisor/CompareRunDrawer";
import { pickSelectedPolicy } from "./components/policy/SelectedPolicyCard";
import { LoadingSkeleton } from "./components/ui/LoadingSkeleton";
import { displayModeClass, type DisplayMode } from "./lib/displayModes";
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
  const [displayMode, setDisplayMode] = useState<DisplayMode>("command");
  const [competitionBriefOpen, setCompetitionBriefOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);

  async function load() {
    const data = await getDashboard();
    setDashboard(data);
  }

  useEffect(() => {
    load().catch((error) => setNotice({ tone: "error", message: error instanceof Error ? error.message : "Unable to load dashboard" }));
  }, []);

  useEffect(() => {
    if (!dashboard || document.hidden) return;
    const timer = window.setInterval(() => {
      void load();
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [dashboard?.real_portfolio?.total_value]);

  useEffect(() => {
    if (!activeRunId) {
      return;
    }
    let cancelled = false;
    const seenEventIds = new Set<number>();

    const finalize = async (terminalStatus: string) => {
      if (cancelled) return;
      try {
        const finalRun = await getAdvisorRun(activeRunId);
        if (cancelled) return;
        setActiveRun(finalRun);
        await load();
        setNotice({
          tone: finalRun.status === "failed" ? "error" : "success",
          message: finalRun.status === "failed"
            ? finalRun.error || finalRun.fallback_reason || "Advisor cycle could not finish. The last valid dashboard is still available."
            : "Advisor cycle complete"
        });
      } catch (error) {
        if (cancelled) return;
        setNotice({
          tone: terminalStatus === "failed" ? "error" : "success",
          message: error instanceof Error ? error.message : "Advisor cycle complete"
        });
      } finally {
        if (!cancelled) {
          setBusy(false);
          setBusyLabel("");
          setActiveRunId(null);
        }
      }
    };

    const close = streamAdvisorRunEvents(activeRunId, {
      onEvent(event) {
        if (event.eventId !== undefined) {
          if (seenEventIds.has(event.eventId)) return;
          seenEventIds.add(event.eventId);
        }
        setActiveRun((prev) => {
          if (!prev) return prev;
          const events = [...prev.events, event];
          const isStepRunning = event.type === "step" && event.status === "running";
          const currentStep = isStepRunning
            ? {
                step: event.title,
                status: "running",
                records: typeof event.metrics?.records === "number" ? Number(event.metrics.records) : 0,
                started_at: event.timestamp,
                finished_at: "",
                message: event.detail,
                technical_detail: event.source ?? "",
              }
            : prev.current_step;
          const status = event.type === "run" ? event.status : prev.status;
          return { ...prev, events, current_step: currentStep ?? prev.current_step, status };
        });
      },
      onTerminal(status) {
        void finalize(status);
      },
      onError(message) {
        if (cancelled) return;
        getAdvisorRun(activeRunId)
          .then((run) => {
            if (cancelled) return;
            setActiveRun(run);
            if (run.status !== "running") {
              void finalize(run.status);
            } else {
              setNotice({ tone: "error", message });
            }
          })
          .catch(() => {
            if (cancelled) return;
            setNotice({ tone: "error", message });
            setBusy(false);
            setBusyLabel("");
            setActiveRunId(null);
          });
      },
    });

    return () => {
      cancelled = true;
      close();
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

  async function runDeepReview() {
    await act("Deep competition review", runAdvisorDeepReview);
  }

  async function reloadWithNotice(message: string) {
    await load();
    setNotice({ tone: "success", message });
  }

  function showError(message: string) {
    setNotice({ tone: "error", message });
  }

  const telemetry = useMemo(() => (dashboard ? telemetryState(dashboard) : []), [dashboard]);
  const advisorStreaming = Boolean(activeRunId && activeRun?.status === "running");
  const telemetryWithActions = useMemo(
    () =>
      telemetry.map((item) => {
        if (item.label === "Portfolio") {
          return { ...item, onAction: () => setActiveTab("portfolio") };
        }
        if (item.label === "Model") {
          return { ...item, onAction: () => setActiveTab("connections") };
        }
        if (item.label === "Data") {
          return { ...item, onAction: () => setActiveTab("connections") };
        }
        if (item.label === "Risk") {
          return { ...item, onAction: () => setActiveTab("risks") };
        }
        if (item.label === "Quant") {
          return { ...item, onAction: () => setActiveTab("actions") };
        }
        return item;
      }),
    [telemetry],
  );
  const displayedTelemetry = useMemo(
    () =>
      copilotRunning
        ? telemetryWithActions.map((item) =>
            item.label === "Model"
              ? { ...item, value: "Reviewing", tone: "live" as const, detail: "Ask Signal is reading the latest advisor packet." }
              : item,
          )
        : advisorStreaming
          ? telemetryWithActions.map((item) =>
              item.label === "Model"
                ? { ...item, value: "Running", tone: "live" as const, detail: "Advisor cycle in progress with live run events." }
                : item,
            )
          : telemetryWithActions,
    [advisorStreaming, copilotRunning, telemetryWithActions],
  );
  const decision = useMemo(() => (dashboard ? primaryDecision(dashboard) : null), [dashboard]);
  const selectedPolicy = useMemo(() => (dashboard ? pickSelectedPolicy(dashboard) : null), [dashboard]);
  const screenContext = activeTab;
  const firstSymbol = dashboard?.advisor_packet?.recommendedPriority?.firstAction?.symbol;

  function handleDisplayMode(mode: DisplayMode) {
    setDisplayMode(mode);
    if (mode === "research") {
      setActiveTab("research");
    } else if (mode === "focus") {
      setActiveTab("now");
    }
  }

  const openCompareRuns = useCallback(() => {
    setActiveTab("now");
    setCompareOpen(true);
  }, []);

  const openCopilot = useCallback((question?: string) => {
    setCopilotQuestion(question);
    setCopilotOpen(true);
  }, []);

  const paletteActions = useMemo<PaletteAction[]>(
    () => [
      { id: "now", label: "Open Now", detail: "Mission control dashboard", icon: BrainCircuit, group: "Navigation", shortcut: "N", run: () => setActiveTab("now") },
      { id: "portfolio", label: "Open Portfolio", detail: "Holdings, map, and allocation", icon: BriefcaseBusiness, group: "Navigation", shortcut: "P", run: () => setActiveTab("portfolio") },
      { id: "risks", label: "Open Risks", detail: "Risk radar and blockers", icon: ShieldAlert, group: "Navigation", run: () => setActiveTab("risks") },
      { id: "actions", label: "Open Actions", detail: "Action timeline and tickets", icon: ListChecks, group: "Navigation", shortcut: "A", run: () => setActiveTab("actions") },
      { id: "research", label: "Open Research", detail: "Pipeline, backtest, and memos", icon: BrainCircuit, group: "Navigation", run: () => setActiveTab("research") },
      { id: "connections", label: "Open Connections", detail: "Source matrix and model routing", icon: KeyRound, group: "Navigation", run: () => setActiveTab("connections") },
      { id: "advisor", label: "Run advisor", detail: "Refresh advisor cycle and receipt", icon: BrainCircuit, group: "Actions", shortcut: "R", run: () => void runAdvisorFlow() },
      { id: "refresh", label: "Refresh data", detail: "Run provider refresh", icon: RefreshCw, group: "Actions", run: () => void act("Refresh", refreshData) },
      { id: "holding", label: firstSymbol ? `Open ${firstSymbol} ticket` : "Open first action", detail: "Jump to the highest-priority advisory ticket", icon: ListChecks, group: "Holdings", run: () => setActiveTab("actions") },
      { id: "receipt", label: "Open decision receipt", detail: "View sealed deterministic receipt", icon: ListChecks, group: "Receipts", shortcut: "D", run: () => setActiveTab("actions") },
      { id: "compare", label: "Compare last two runs", detail: "Diff portfolio, risk, and receipt hash", icon: GitCompare, group: "Receipts", run: () => openCompareRuns() },
      { id: "ask", label: "Ask Signal", detail: "Context-aware follow-up questions", icon: MessageCircle, group: "Ask Signal", shortcut: "K", run: () => openCopilot() },
      { id: "ask-first", label: "Ask Signal: explain first action", detail: "Why this is today's command", icon: MessageCircle, group: "Ask Signal", run: () => openCopilot("Why is this the first action?") },
      { id: "brief", label: "Open competition brief", detail: "Judge-ready portfolio summary", icon: Trophy, group: "Developer/Audit", run: () => setCompetitionBriefOpen(true) },
      { id: "focus", label: "Toggle focus mode", detail: "Show only first action and receipt", icon: BrainCircuit, group: "Developer/Audit", run: () => handleDisplayMode(displayMode === "focus" ? "command" : "focus") },
      { id: "research-mode", label: "Toggle research mode", detail: "Open research evidence screen", icon: BrainCircuit, group: "Developer/Audit", run: () => handleDisplayMode(displayMode === "research" ? "command" : "research") },
    ],
    [displayMode, firstSymbol, openCompareRuns, openCopilot],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.metaKey || event.ctrlKey) return;
      const key = event.key.toLowerCase();
      if (key === "r") {
        event.preventDefault();
        void runAdvisorFlow();
      } else if (key === "a") {
        event.preventDefault();
        setActiveTab("actions");
      } else if (key === "p") {
        event.preventDefault();
        setActiveTab("portfolio");
      } else if (key === "k") {
        event.preventDefault();
        openCopilot();
      } else if (key === "d") {
        event.preventDefault();
        setActiveTab("actions");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openCopilot]);

  function openDecision(tab: AppTab) {
    setActiveTab(tab);
  }

  if (!dashboard) {
    return <LoadingSkeleton />;
  }

  return (
    <Tooltip.Provider delayDuration={120}>
      <div className={`signal-app ${displayModeClass(displayMode)}`}>
        <CommandRail activeTab={activeTab} onTab={setActiveTab} />
        <main className="signal-workspace">
          <TopTelemetry
            items={displayedTelemetry}
            busy={busy}
            onOpenPalette={() => setPaletteOpen(true)}
            primaryLabel={decision?.primaryLabel ?? "Open Now"}
            onPrimaryAction={() => openDecision(decision?.primaryTab ?? "now")}
            selectedPolicy={selectedPolicy}
            displayMode={displayMode}
            onDisplayMode={handleDisplayMode}
            onPolicyChanged={reloadWithNotice}
            onPolicyError={showError}
          />
          {busy && <div className="process-banner compact" data-testid="process-banner">{busyLabel || "Signal Prime is working"} · {activeRun?.current_step?.step ?? "Starting run"}</div>}
          {notice && <div className={`notice ${notice.tone}`}>{notice.message}</div>}
          {activeTab === "now" && (
            <HomeView
              dashboard={dashboard}
              busy={busy}
              onNavigate={setActiveTab}
              onAsk={openCopilot}
              activeRun={activeRun}
              onRunAdvisor={() => void runAdvisorFlow()}
              onDeepReview={() => void runDeepReview()}
              displayMode={displayMode}
              onCompareOpenChange={setCompareOpen}
            />
          )}
          {activeTab === "portfolio" && (
            <PortfolioView dashboard={dashboard} onDone={reloadWithNotice} onError={showError} onAsk={openCopilot} />
          )}
          {activeTab === "risks" && <RiskView dashboard={dashboard} onAsk={openCopilot} />}
          {activeTab === "actions" && <ActionsView dashboard={dashboard} onAsk={openCopilot} />}
          {activeTab === "research" && (
            <IntelligenceView
              dashboard={dashboard}
              latestBacktest={dashboard.recent_backtests[0]}
              onRunBacktest={(symbols, maxPositions) => void act("Backtest", () => runBacktest(symbols, maxPositions))}
            />
          )}
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
        <CompetitionBrief open={competitionBriefOpen} onOpenChange={setCompetitionBriefOpen} dashboard={dashboard} />
        <CompareRunDrawer
          open={compareOpen}
          onOpenChange={setCompareOpen}
          packet={dashboard.advisor_packet}
        />
      </div>
    </Tooltip.Provider>
  );
}
