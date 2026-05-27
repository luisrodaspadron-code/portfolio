import { CheckCircle2, Circle, Clock3, Lock, ShieldAlert } from "lucide-react";
import type { Dashboard } from "../../types";
import { money, pct, shortDateTime, titleCase } from "../../lib/format";
import { Badge } from "../ui/Primitives";

type TimelineStep = {
  id: string;
  title: string;
  detail: string;
  status: "required" | "allowed" | "blocked" | "waiting" | "complete";
  math?: string;
};

function stepIcon(status: TimelineStep["status"]) {
  if (status === "complete") return CheckCircle2;
  if (status === "blocked") return Lock;
  if (status === "required") return ShieldAlert;
  if (status === "allowed") return CheckCircle2;
  return Clock3;
}

function buildTimeline(dashboard: Dashboard): TimelineStep[] {
  const packet = dashboard.advisor_packet;
  const first = packet.recommendedPriority.firstAction;
  const receipt = packet.decisionReceipt;
  const trimPlan = first?.trimPlan;
  const blocked = (receipt?.riskIncreasingActionsBlocked?.length ?? 0) > 0;
  const allowed = (receipt?.riskReducingActionsAllowed?.length ?? 0) > 0;
  const addCandidates = packet.candidates.filter(
    (item) => item.action === "ADD" || item.action === "STAGGER_ENTRY",
  );

  const steps: TimelineStep[] = [];

  if (first?.action === "TRIM") {
    steps.push({
      id: "repair",
      title: "Repair concentration",
      detail: `Trim ${first.symbol} toward the ${pct(first.targetWeight ?? 0)} policy threshold.`,
      status: "required",
      math: trimPlan
        ? `${trimPlan.sharesToSellWholeCompliant ?? trimPlan.sharesToSellWhole} compliant whole shares · ${money(trimPlan.estimatedSellValue)} est.`
        : undefined,
    });
  } else if (blocked) {
    steps.push({
      id: "repair",
      title: "Resolve active breaches",
      detail: receipt?.riskIncreasingActionsBlocked?.[0] ?? "Clear hard gates before increasing exposure.",
      status: "required",
    });
  }

  steps.push({
    id: "recheck",
    title: "Recheck gates",
    detail: blocked
      ? "Confirm sector and single-name caps after remediation."
      : "Risk gates are clear at this snapshot.",
    status: blocked ? "waiting" : "complete",
  });

  steps.push({
    id: "redeploy",
    title: "Redeploy carefully",
    detail: allowed
      ? "Broad ETFs may remain eligible if risk-reducing and data gates pass."
      : "No risk-reducing adds are eligible yet.",
    status: allowed ? "allowed" : "blocked",
  });

  if (addCandidates.length) {
    const tranches = addCandidates[0]?.addPlan?.trancheCount ?? 4;
    steps.push({
      id: "stage",
      title: "Stage entries",
      detail: `${addCandidates.length} candidate${addCandidates.length === 1 ? "" : "s"} · ${tranches} tranches by default.`,
      status: blocked ? "blocked" : "allowed",
    });
  }

  steps.push({
    id: "review",
    title: "Next review",
    detail: dashboard.scheduler.next_run_at
      ? shortDateTime(dashboard.scheduler.next_run_at)
      : "Schedule a daily review to keep the receipt current.",
    status: "waiting",
  });

  return steps;
}

export function ActionTimeline({ dashboard }: { dashboard: Dashboard }) {
  const steps = buildTimeline(dashboard);

  return (
    <div className="action-timeline" data-testid="action-timeline">
      {steps.map((step, index) => {
        const Icon = stepIcon(step.status);
        return (
          <article key={step.id} className={`action-timeline-step status-${step.status}`}>
            <div className="action-timeline-marker">
              <span>{index + 1}</span>
              <Icon size={16} />
            </div>
            <div className="action-timeline-body">
              <div className="action-timeline-head">
                <strong>{step.title}</strong>
                <Badge tone={step.status === "required" ? "fail" : step.status === "allowed" || step.status === "complete" ? "live" : step.status === "blocked" ? "fail" : "watch"}>
                  {titleCase(step.status.replace(/_/g, " "))}
                </Badge>
              </div>
              <p>{step.detail}</p>
              {step.math && <code>{step.math}</code>}
            </div>
          </article>
        );
      })}
    </div>
  );
}
