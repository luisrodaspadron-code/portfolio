import { motion } from "motion/react";
import { AlertTriangle, BrainCircuit, Database, Receipt, ShieldCheck, Sparkles, Target } from "lucide-react";
import type { Dashboard } from "../../types";
import { modelRouteLabel, shortDateTime, titleCase } from "../../lib/format";

type DecisionNode = {
  label: string;
  status: "complete" | "active" | "blocked" | "waiting";
  detail: string;
  source?: string;
  warnings?: number;
};

function buildNodes(dashboard: Dashboard): DecisionNode[] {
  const packet = dashboard.advisor_packet;
  const receipt = packet.decisionReceipt;
  const matrixRows = packet.sourceMatrix?.matrix ?? {};
  const pricesEntry = matrixRows.prices;
  const factorsEntry = matrixRows.factors;
  const priceSource = (pricesEntry?.provider as string | undefined) ?? dashboard.data_freshness.preferred_price_source;
  const priceFreshness = (pricesEntry?.freshness as string | undefined) ?? dashboard.data_freshness.provider_mode;
  const riskIssues = packet.portfolioRisk.issueCount;
  const first = packet.recommendedPriority.firstAction;
  const eligible = packet.candidates.filter((item) => item.action === "ADD" || item.action === "STAGGER_ENTRY").length;
  const blocked = packet.candidates.filter((item) => item.blockers.length).length;

  return [
    {
      label: "Data",
      status: dashboard.data_freshness.price_bars ? "complete" : "waiting",
      detail: `${dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols} symbols · ${titleCase(priceFreshness)}`,
      source: titleCase(priceSource),
      warnings: pricesEntry?.warnings?.length ?? 0,
    },
    {
      label: "Factors",
      status: dashboard.quant_diagnostics.coverage.scored_instruments ? "complete" : "waiting",
      detail: `${dashboard.quant_diagnostics.coverage.scored_instruments} scored instruments`,
      source: factorsEntry?.provider ? titleCase(String(factorsEntry.provider)) : "Local engine",
      warnings: factorsEntry?.warnings?.length ?? 0,
    },
    {
      label: "Risk gates",
      status: riskIssues ? "active" : "complete",
      detail: riskIssues ? `${riskIssues} threshold${riskIssues === 1 ? "" : "s"} breached` : "Hard gates clear",
      source: packet.selectedPolicy?.name ?? "Balanced",
      warnings: riskIssues,
    },
    {
      label: "Sizing",
      status: first?.trimPlan || first?.addPlan ? "complete" : first ? "active" : "waiting",
      detail: first?.trimPlan
        ? `Trim ticket · ${first.trimPlan.sharesToSellWholeCompliant ?? first.trimPlan.sharesToSellWhole} whole shares`
        : first
          ? `${first.action} ${first.symbol}`
          : "Waiting for advisor run",
      warnings: 0,
    },
    {
      label: "Candidates",
      status: eligible ? "complete" : blocked ? "blocked" : "waiting",
      detail: `${eligible} eligible · ${blocked} blocked`,
      warnings: blocked,
    },
    {
      label: "Model summary",
      status: receipt?.modelRoute ? "complete" : dashboard.ai_status.configured ? "waiting" : "blocked",
      detail: receipt?.modelRoute
        ? `${modelRouteLabel(receipt.modelRoute)} · ${titleCase(receipt.reasoningEffort ?? "medium")}`
        : dashboard.ai_status.configured
          ? "Ready for narrative review"
          : "Quant-only fallback",
      source: dashboard.ai_status.provider || "local",
      warnings: receipt?.dataLimitations?.length ?? 0,
    },
    {
      label: "Receipt",
      status: receipt?.packetHash ? "complete" : "waiting",
      detail: receipt?.packetHash ? `Sealed · ${receipt.packetHash.slice(0, 8)}…` : "Not sealed yet",
      source: shortDateTime(receipt?.timestamp ?? packet.generatedAt),
      warnings: receipt?.hardGatesTripped?.length ?? 0,
    },
  ];
}

function nodeIcon(label: string) {
  if (label === "Data") return Database;
  if (label === "Factors") return Sparkles;
  if (label === "Risk gates") return ShieldCheck;
  if (label === "Sizing") return Target;
  if (label === "Candidates") return AlertTriangle;
  if (label === "Model summary") return BrainCircuit;
  return Receipt;
}

export function DecisionMap({ dashboard }: { dashboard: Dashboard }) {
  const nodes = buildNodes(dashboard);

  return (
    <div className="decision-map" data-testid="decision-map">
      {nodes.map((node, index) => {
        const Icon = nodeIcon(node.label);
        return (
          <motion.div
            key={node.label}
            className={`decision-map-node ${node.status}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.04 }}
          >
            <Icon size={16} />
            <div>
              <strong>{node.label}</strong>
              <span>{node.detail}</span>
              {node.source && <em>{node.source}</em>}
            </div>
            {node.warnings ? <b>{node.warnings}</b> : null}
            {index < nodes.length - 1 && <i aria-hidden="true" />}
          </motion.div>
        );
      })}
    </div>
  );
}
