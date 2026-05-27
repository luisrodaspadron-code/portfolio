import { AlertOctagon, ShieldOff, Clock, Layers, Database, Sparkles } from "lucide-react";
import type { AdvisorPacket, SelectedPolicy } from "../../types";
import { pct } from "../../lib/format";
import { Badge, CommandButton } from "../ui/Primitives";

export type RiskBlocker = {
  id: string;
  symbol: string;
  category: "single_name" | "sector" | "data" | "liquidity" | "drawdown" | "generic";
  severity: "warning" | "danger" | "neutral";
  why: string;
  /** plain-language: when this blocker auto-clears */
  clearsWhen: string;
  /** the next user action that would clear it */
  nextAction: string;
  observed?: number;
  limit?: number;
};

function iconFor(category: RiskBlocker["category"]) {
  switch (category) {
    case "sector": return Layers;
    case "data": return Database;
    case "drawdown": return Clock;
    case "liquidity": return Sparkles;
    case "single_name": return ShieldOff;
    default: return AlertOctagon;
  }
}

function severityTone(severity: RiskBlocker["severity"]) {
  if (severity === "danger") return "fail";
  if (severity === "warning") return "watch";
  return "neutral";
}

/**
 * Turn the deterministic engine's risk + blocked-action payload into the
 * normalized {@link RiskBlocker} model the UI cards consume.
 *
 * Pure mapping — no math, no thresholds invented.
 */
export function deriveRiskBlockers(packet: AdvisorPacket, policy: SelectedPolicy | null): RiskBlocker[] {
  const blockers: RiskBlocker[] = [];

  packet.portfolioRisk.singleNameBreaches.forEach((breach, idx) => {
    const symbol = breach.rule?.match(/\b[A-Z]{1,5}\b/)?.[0] ?? "Position";
    blockers.push({
      id: `single-${breach.id || idx}`,
      symbol,
      category: "single_name",
      severity: breach.severity === "extreme" || breach.severity === "high" ? "danger" : "warning",
      why: breach.message,
      clearsWhen: policy?.singleStock.hardBuyBlock
        ? `Position weight falls below ${pct(policy.singleStock.hardBuyBlock)} or the policy is changed.`
        : "Position weight falls below the policy threshold.",
      nextAction: "Trim or dilute with new diversified capital. Risk-reducing trades remain eligible.",
      observed: breach.observed,
      limit: breach.limit,
    });
  });

  packet.portfolioRisk.sectorBreaches.forEach((breach, idx) => {
    blockers.push({
      id: `sector-${breach.id || idx}`,
      symbol: breach.rule || "Sector",
      category: "sector",
      severity: breach.severity === "extreme" ? "danger" : "warning",
      why: breach.message,
      clearsWhen: policy?.sector.hardCap
        ? `Sector weight falls below ${pct(policy.sector.hardCap)}.`
        : "Sector weight falls below its policy cap.",
      nextAction: "Trim the largest contributor in this sector or add a diversifying broad ETF.",
      observed: breach.observed,
      limit: breach.limit,
    });
  });

  packet.portfolioRisk.staleDataWarnings.forEach((breach, idx) => {
    blockers.push({
      id: `data-${breach.id || idx}`,
      symbol: breach.rule || "Data",
      category: "data",
      severity: "warning",
      why: breach.message,
      clearsWhen: "Data source reports a recent / live snapshot for the affected symbols.",
      nextAction: "Refresh providers in Connections or review the source matrix.",
      observed: breach.observed,
      limit: breach.limit,
    });
  });

  packet.portfolioRisk.liquidityWarnings.forEach((breach, idx) => {
    blockers.push({
      id: `liquidity-${breach.id || idx}`,
      symbol: breach.rule || "Liquidity",
      category: "liquidity",
      severity: "warning",
      why: breach.message,
      clearsWhen: "Average dollar volume improves above the liquidity gate for two reviews.",
      nextAction: "Keep on watchlist or reduce intended position size.",
      observed: breach.observed,
      limit: breach.limit,
    });
  });

  packet.recommendedPriority.blockedActions.forEach((message, idx) => {
    if (blockers.find((b) => b.why === message)) return;
    blockers.push({
      id: `blocked-${idx}`,
      symbol: "Blocked action",
      category: "generic",
      severity: "warning",
      why: message,
      clearsWhen: "Underlying risk or data condition improves.",
      nextAction: "Address the upstream risk or data gap before re-running.",
    });
  });

  return blockers;
}

type Props = {
  blocker: RiskBlocker;
  onAsk?: (prompt: string) => void;
};

/**
 * Single risk blocker card. Always shows: why it is blocked, when it clears,
 * and the next action that the user can take. Avoids guesswork.
 */
export function RiskBlockerCard({ blocker, onAsk }: Props) {
  const Icon = iconFor(blocker.category);
  return (
    <article className={`risk-blocker-card severity-${blocker.severity}`} data-category={blocker.category}>
      <header>
        <span className="risk-blocker-icon">
          <Icon size={16} aria-hidden="true" />
        </span>
        <div>
          <strong>{blocker.symbol}</strong>
          <em>{blocker.category.replace(/_/g, " ")}</em>
        </div>
        <Badge tone={severityTone(blocker.severity)}>
          {blocker.severity === "danger" ? "Blocked" : "Watch"}
        </Badge>
      </header>

      <dl>
        <div>
          <dt>Why</dt>
          <dd>{blocker.why}</dd>
        </div>
        <div>
          <dt>Clears when</dt>
          <dd>{blocker.clearsWhen}</dd>
        </div>
        <div>
          <dt>Next action</dt>
          <dd>{blocker.nextAction}</dd>
        </div>
        {blocker.observed !== undefined && blocker.limit !== undefined && (
          <div>
            <dt>Observed vs limit</dt>
            <dd>{pct(blocker.observed)} vs {pct(blocker.limit)}</dd>
          </div>
        )}
      </dl>

      {onAsk && (
        <footer>
          <CommandButton
            variant="quiet"
            icon={Sparkles}
            onClick={() => onAsk(`What clears the ${blocker.symbol} blocker (${blocker.category.replace(/_/g, " ")})? List the smallest action that would unblock it.`)}
          >
            Ask Signal what clears this
          </CommandButton>
        </footer>
      )}
    </article>
  );
}
