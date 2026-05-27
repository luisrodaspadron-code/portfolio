import { useState } from "react";
import { BarChart3, BrainCircuit, Database, FileText, TestTube2 } from "lucide-react";
import type { BacktestRun, Dashboard, ResearchMemo } from "../types";
import { advisorPipelineSteps } from "../lib/viewModels";
import { number, pct, shortDateTime } from "../lib/format";
import { AdvisorPipeline } from "../components/visuals/AdvisorPipeline";
import { Badge, CommandButton, EmptyState, SignalPanel } from "../components/ui/Primitives";

function MemoReader({ memos }: { memos: ResearchMemo[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(memos[0]?.id ?? null);
  const selected = memos.find((memo) => memo.id === selectedId) ?? memos[0];
  if (!memos.length || !selected) {
    return <EmptyState title="No research memos yet" body="Run the advisor after connecting AI and market data to generate source-aware memos." />;
  }

  return (
    <div className="memo-intel">
      <div className="memo-tabs">
        {memos.slice(0, 8).map((memo) => (
          <button className={memo.id === selected.id ? "active" : ""} key={memo.id} onClick={() => setSelectedId(memo.id)}>
            <strong>{memo.symbol}</strong>
            <span>{shortDateTime(memo.created_at)}</span>
          </button>
        ))}
      </div>
      <article className="memo-content">
        <div>
          <span>{selected.symbol} · {selected.name}</span>
          <h3>{selected.title}</h3>
          <Badge tone={selected.generation_method === "openai" ? "live" : "watch"}>{selected.generation_method}</Badge>
        </div>
        <section>
          <strong>Thesis</strong>
          <p>{selected.thesis}</p>
        </section>
        <section>
          <strong>Evidence</strong>
          <p>{selected.evidence}</p>
        </section>
        <section>
          <strong>Risks</strong>
          <p>{selected.risks}</p>
        </section>
        <section>
          <strong>What would change my mind</strong>
          <p>{selected.change_mind}</p>
        </section>
      </article>
    </div>
  );
}

function BacktestEvidence({ latest }: { latest?: BacktestRun }) {
  if (!latest) return <EmptyState title="No recent backtest" body="Backtest evidence will appear here after the robo flow runs a deterministic check." />;
  const validation = latest.params.validation as
    | {
        no_lookahead?: boolean;
        signal_lag?: string;
        benchmark_symbol?: string;
        warnings?: string[];
      }
    | undefined;
  return (
    <div className="backtest-evidence-wrap">
      <div className="backtest-evidence">
        <div>
          <span>Total return</span>
          <strong>{pct(latest.metrics.total_return ?? 0)}</strong>
        </div>
        <div>
          <span>Benchmark relative</span>
          <strong>{pct(latest.metrics.benchmark_relative_return ?? 0)}</strong>
        </div>
        <div>
          <span>Max drawdown</span>
          <strong>{pct(latest.metrics.max_drawdown ?? 0)}</strong>
        </div>
        <div>
          <span>Sharpe / Sortino</span>
          <strong>{number(latest.metrics.sharpe ?? 0)} / {number(latest.metrics.sortino ?? 0)}</strong>
        </div>
        <div>
          <span>Calmar</span>
          <strong>{number(latest.metrics.calmar ?? 0)}</strong>
        </div>
        <div>
          <span>Turnover</span>
          <strong>{pct(latest.metrics.turnover ?? 0)}</strong>
        </div>
      </div>
      <div className="validation-note">
        <Badge tone={validation?.no_lookahead ? "live" : "watch"}>{validation?.no_lookahead ? "No-lookahead" : "Needs validation"}</Badge>
        <p>
          Run #{latest.id}
          {validation?.benchmark_symbol ? ` · benchmark ${validation.benchmark_symbol}` : ""}. {validation?.signal_lag ?? "Validation metadata unavailable."}
        </p>
        {validation?.warnings?.[0] && <small>{validation.warnings[0]}</small>}
      </div>
    </div>
  );
}

export function IntelligenceView({
  dashboard,
  latestBacktest,
  onRunBacktest
}: {
  dashboard: Dashboard;
  latestBacktest?: BacktestRun;
  onRunBacktest: (symbols: string, maxPositions: number) => void;
}) {
  return (
    <section className="intelligence-view screen-enter">
      <SignalPanel className="intelligence-command">
        <span>Automated intelligence</span>
        <h1>Robo flow you can audit</h1>
        <p>The advisor packet combines source freshness, feature generation, risk gates, backtest context, strategy sleeves, and AI review.</p>
      </SignalPanel>

      <section className="intelligence-grid">
        <SignalPanel className="pipeline-panel">
          <div className="panel-label-row">
            <span>Advisor pipeline</span>
            <BrainCircuit size={16} />
          </div>
          <AdvisorPipeline steps={advisorPipelineSteps(dashboard)} />
        </SignalPanel>
        <SignalPanel className="intel-panel">
          <div className="panel-label-row">
            <span>Quant health</span>
            <TestTube2 size={16} />
          </div>
          <div className="quant-health-grid">
            {dashboard.quant_diagnostics.checks.map((check) => (
              <div key={check.name}>
                <Badge tone={check.status === "pass" ? "pass" : check.status === "fail" ? "fail" : "watch"}>{check.status}</Badge>
                <strong>{check.name}</strong>
                <p>{check.detail}</p>
              </div>
            ))}
          </div>
        </SignalPanel>
      </section>

      <section className="intelligence-grid">
        <SignalPanel className="intel-panel">
          <div className="panel-label-row">
            <span>Backtest evidence</span>
            <BarChart3 size={16} />
          </div>
          <BacktestEvidence latest={latestBacktest} />
          <div className="inline-actions">
            <CommandButton variant="secondary" onClick={() => onRunBacktest("SPY,QQQ,IWM,TLT,GLD", 8)}>
              Run check now
            </CommandButton>
          </div>
        </SignalPanel>
        <SignalPanel className="intel-panel">
          <div className="panel-label-row">
            <span>Data coverage</span>
            <Database size={16} />
          </div>
          <div className="backtest-evidence">
            <div>
              <span>Scored</span>
              <strong>{number(dashboard.quant_diagnostics.coverage.scored_instruments)}</strong>
            </div>
            <div>
              <span>Price bars</span>
              <strong>{number(dashboard.data_freshness.price_bars)}</strong>
            </div>
            <div>
              <span>Live symbols</span>
              <strong>{number(dashboard.data_freshness.live_price_symbols)}</strong>
            </div>
            <div>
              <span>Tools</span>
              <strong>{number(dashboard.decision_packet_status.tool_count)}</strong>
            </div>
          </div>
        </SignalPanel>
      </section>

      <SignalPanel className="research-intel-panel">
        <div className="panel-label-row">
          <span>Research memos</span>
          <FileText size={16} />
        </div>
        <MemoReader memos={dashboard.research_memos} />
      </SignalPanel>
    </section>
  );
}
