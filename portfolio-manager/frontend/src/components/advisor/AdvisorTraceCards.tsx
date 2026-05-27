import { BrainCircuit, Database, Globe2, MessageCircle, ShieldCheck } from "lucide-react";
import type { Dashboard } from "../../types";
import { money, number, titleCase } from "../../lib/format";
import { Badge, CommandButton, IconSlot, SignalPanel } from "../ui/Primitives";

export function AdvisorTraceCards({
  dashboard,
  onAsk
}: {
  dashboard: Dashboard;
  onAsk: (question?: string) => void;
}) {
  const trace = dashboard.advisor_trace;
  const coverage = trace.market_universe.coverage ?? dashboard.universe_status;
  const topHolding = trace.holdings_analyzed.top_holding;
  const checkedTools = trace.quant_tools.filter((tool) => tool.status === "checked").length;
  const provider = titleCase(trace.provider_freshness.preferred_source);
  const topClasses = Object.entries(trace.market_universe.asset_classes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([label, count]) => `${count} ${label}`)
    .join(" · ");

  return (
    <section className="advisor-trace-grid" data-testid="advisor-trace-cards">
      <SignalPanel className="trace-card">
        <div className="trace-icon-row">
          <IconSlot icon={BrainCircuit} />
          <Badge tone={trace.ai_activity === "reviewed" ? "live" : trace.ai_activity === "rate_limited" ? "watch" : "neutral"}>
            {titleCase(trace.ai_activity)}
          </Badge>
        </div>
        <span>What AI analyzed</span>
        <strong>{trace.holdings_analyzed.count} real positions</strong>
        <p>
          {topHolding
            ? `Largest holding: ${topHolding.symbol} at ${money(topHolding.market_value)}.`
            : "Import holdings to make this portfolio-specific."}
        </p>
        <CommandButton icon={MessageCircle} variant="ghost" onClick={() => onAsk("Is the advisor analyzing my current positions?")}>
          Ask how
        </CommandButton>
      </SignalPanel>

      <SignalPanel className="trace-card">
        <div className="trace-icon-row">
          <IconSlot icon={ShieldCheck} />
          <Badge tone={checkedTools >= 7 ? "live" : "watch"}>{checkedTools}/{trace.quant_tools.length}</Badge>
        </div>
        <span>Quant tools used</span>
        <strong>{checkedTools} checks complete</strong>
        <p>Data refresh, feature generation, risk gates, sizing, strategy sleeves, and macro regime feed the advisor.</p>
        <div className="trace-tool-strip">
          {trace.quant_tools.slice(0, 5).map((tool) => (
            <i key={tool.name} className={tool.status}>
              {tool.label}
            </i>
          ))}
        </div>
      </SignalPanel>

      <SignalPanel className="trace-card">
        <div className="trace-icon-row">
          <IconSlot icon={Globe2} />
          <Badge tone={coverage.sources?.alpaca ? "live" : "watch"}>{coverage.sources?.alpaca ? "All-US" : "Seeded"}</Badge>
        </div>
        <span>Market universe</span>
        <strong>{number(coverage.included_assets || trace.market_universe.enabled_instruments)} assets</strong>
        <p>{coverage.scope_label || topClasses || "Universe is waiting for enabled instruments."}</p>
        <small>{number(coverage.priced_symbols)} priced · {number(coverage.ipo_assets)} IPO/special · {provider || "Sample"} price source</small>
      </SignalPanel>

      <SignalPanel className="trace-card sec-card">
        <div className="trace-icon-row">
          <IconSlot icon={Database} />
          <Badge tone={trace.sec_edgar.configured ? "live" : "watch"}>{trace.sec_edgar.configured ? "Configured" : "Needs identity"}</Badge>
        </div>
        <span>SEC EDGAR</span>
        <strong>{trace.sec_edgar.facts_count} fact groups</strong>
        <p>{trace.sec_edgar.purpose}</p>
      </SignalPanel>
    </section>
  );
}
