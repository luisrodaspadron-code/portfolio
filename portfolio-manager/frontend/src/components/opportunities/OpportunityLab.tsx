import { useMemo } from "react";
import { ArrowRight, Sparkles, ShieldCheck, Hourglass, Ban, Eye } from "lucide-react";
import type { AdvisorPacketAction } from "../../types";
import { titleCase } from "../../lib/format";
import { Badge, SignalPanel } from "../ui/Primitives";
import { ScoreBreakdownBars, type ScoreComponent } from "../visuals/ScoreBreakdownBars";
import { DataQualityPill } from "../data/DataQualityPill";

type Lane = "eligible" | "risk_reducing" | "watch" | "blocked" | "limited_history";

const LANE_ORDER: Lane[] = ["eligible", "risk_reducing", "watch", "limited_history", "blocked"];

const LANE_META: Record<Lane, { label: string; tone: string; description: string; icon: typeof Sparkles }> = {
  eligible: {
    label: "Eligible now",
    tone: "live",
    description: "Pass risk, data, and concentration gates. Advisory-only.",
    icon: Sparkles,
  },
  risk_reducing: {
    label: "Risk-reducing",
    tone: "good",
    description: "Broad / equal-weight diversifiers that reduce concentration risk.",
    icon: ShieldCheck,
  },
  watch: {
    label: "Watch",
    tone: "watch",
    description: "Interesting, but not strong or clean enough to recommend yet.",
    icon: Eye,
  },
  limited_history: {
    label: "Limited history",
    tone: "neutral",
    description: "Recent IPOs or sparse data — insufficient history to score reliably.",
    icon: Hourglass,
  },
  blocked: {
    label: "Blocked",
    tone: "fail",
    description: "Risk, data, or policy gate prevents recommendation.",
    icon: Ban,
  },
};

const BROAD_ETFS = new Set(["SPY", "VTI", "VOO", "RSP", "IVV", "SCHB", "ITOT"]);

function freshnessScore(freshness?: string): number {
  switch ((freshness || "").toLowerCase()) {
    case "live":
    case "recent":
      return 0.95;
    case "partial":
      return 0.55;
    case "sample":
      return 0.4;
    case "stale":
      return 0.3;
    default:
      return 0.15;
  }
}

function classifyLane(candidate: AdvisorPacketAction): Lane {
  const freshness = (candidate.dataQuality?.freshness || "").toLowerCase();
  if (candidate.action === "BLOCKED_BY_RISK") return "blocked";
  if (candidate.action === "WAIT_FOR_DATA" || freshness === "missing") return "limited_history";
  if (candidate.action === "REVIEW_MANUALLY") return "watch";
  if (
    (candidate.action === "ADD" || candidate.action === "STAGGER_ENTRY") &&
    (candidate.assetClass === "etf_broad" || BROAD_ETFS.has(candidate.symbol))
  ) {
    return "risk_reducing";
  }
  if (candidate.action === "ADD" || candidate.action === "STAGGER_ENTRY") return "eligible";
  if (candidate.blockers && candidate.blockers.length > 0) return "watch";
  return "watch";
}

function buildScoreComponents(candidate: AdvisorPacketAction): ScoreComponent[] {
  const conviction = Math.max(0, Math.min(1, candidate.confidence ?? 0));
  const riskGate = candidate.blockers && candidate.blockers.length > 0 ? Math.max(0, 0.5 - candidate.blockers.length * 0.1) : 0.92;
  const data = freshnessScore(candidate.dataQuality?.freshness);
  const drivers = candidate.confidenceDrivers ?? [];
  const driverStrength = Math.min(1, drivers.length / 4);
  const diversify =
    candidate.assetClass === "etf_broad" ? 0.88 :
    candidate.assetClass === "etf_thematic" ? 0.58 : 0.42;
  return [
    { label: "Conviction", value: conviction, weight: 0.95, detail: candidate.confidenceDrivers?.join(" · ") },
    { label: "Risk gate", value: riskGate, weight: 0.85, detail: candidate.blockers?.join(" · ") || "No blockers." },
    { label: "Data quality", value: data, weight: 0.7, detail: `Freshness: ${candidate.dataQuality?.freshness ?? "n/a"}` },
    { label: "Drivers", value: driverStrength, weight: 0.55, detail: drivers.join(" · ") || "No drivers recorded." },
    { label: "Diversifies", value: diversify, weight: 0.65, detail: candidate.sector ?? candidate.assetClass ?? "Asset class hint" },
  ];
}

function totalScore(components: ScoreComponent[]): number {
  const totalWeight = components.reduce((sum, c) => sum + (c.weight ?? 1), 0);
  const weighted = components.reduce((sum, c) => sum + c.value * (c.weight ?? 1), 0);
  return totalWeight > 0 ? weighted / totalWeight : 0;
}

type Props = {
  candidates: AdvisorPacketAction[];
  onSelect?: (candidate: AdvisorPacketAction) => void;
};

/**
 * Opportunity Lab: lanes of candidate ideas with a quant-style score
 * breakdown for each. Pure visualization on top of the deterministic
 * candidate list — never re-ranks or invents new math.
 */
export function OpportunityLab({ candidates, onSelect }: Props) {
  const lanes = useMemo(() => {
    const grouped: Record<Lane, AdvisorPacketAction[]> = {
      eligible: [],
      risk_reducing: [],
      watch: [],
      limited_history: [],
      blocked: [],
    };
    candidates.forEach((candidate) => {
      grouped[classifyLane(candidate)].push(candidate);
    });
    return grouped;
  }, [candidates]);

  if (!candidates.length) {
    return (
      <SignalPanel className="opportunity-lab-panel" testId="opportunity-lab">
        <div className="panel-label-row">
          <span>Opportunity Lab</span>
          <Badge tone="watch">No candidates</Badge>
        </div>
        <p className="visual-explainer">
          The deterministic engine did not surface outside ideas this cycle. They appear here when
          risk-reducing diversifiers or higher-quality candidates beat the current portfolio after gates.
        </p>
      </SignalPanel>
    );
  }

  return (
    <SignalPanel className="opportunity-lab-panel" testId="opportunity-lab">
      <div className="panel-label-row">
        <span>Opportunity Lab</span>
        <Badge tone="live">{candidates.length} candidates</Badge>
      </div>

      <div className="opportunity-lab-lanes">
        {LANE_ORDER.map((lane) => {
          const list = lanes[lane];
          const meta = LANE_META[lane];
          const Icon = meta.icon;
          return (
            <section key={lane} className={`opportunity-lane lane-${lane}`}>
              <header>
                <span className="opportunity-lane-icon">
                  <Icon size={14} aria-hidden="true" />
                </span>
                <strong>{meta.label}</strong>
                <Badge tone={meta.tone}>{list.length}</Badge>
              </header>
              <p>{meta.description}</p>

              {list.length === 0 ? (
                <div className="opportunity-lane-empty">No candidates in this lane.</div>
              ) : (
                <div className="opportunity-lane-grid">
                  {list.slice(0, 6).map((candidate) => {
                    const components = buildScoreComponents(candidate);
                    const score = totalScore(components);
                    return (
                      <article key={candidate.symbol} className="opportunity-card">
                        <header>
                          <strong>{candidate.symbol}</strong>
                          <Badge tone={meta.tone}>{titleCase(candidate.action.replace(/_/g, " "))}</Badge>
                        </header>
                        <em>{candidate.name ?? candidate.assetClass ?? candidate.sector ?? "Candidate"}</em>
                        <ScoreBreakdownBars total={score} components={components} compact />
                        <div className="opportunity-card-badges">
                          {candidate.assetClass && <Badge tone="neutral">{titleCase(candidate.assetClass.replace(/_/g, " "))}</Badge>}
                          {candidate.dataQuality?.freshness && (
                            <DataQualityPill freshness={candidate.dataQuality.freshness} compact />
                          )}
                          {candidate.blockers?.length ? (
                            <Badge tone="watch">{candidate.blockers.length} blockers</Badge>
                          ) : null}
                        </div>
                        <p>{candidate.explanation}</p>
                        {onSelect && (
                          <button
                            type="button"
                            className="opportunity-card-action"
                            onClick={() => onSelect(candidate)}
                            aria-label={`Open ${candidate.symbol} candidate detail`}
                          >
                            Open detail
                            <ArrowRight size={14} aria-hidden="true" />
                          </button>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </SignalPanel>
  );
}
