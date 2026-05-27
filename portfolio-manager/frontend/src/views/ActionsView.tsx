import { useMemo, useState } from "react";
import { BrainCircuit, CheckCircle2, MessageCircle, ShieldAlert } from "lucide-react";
import type { AdvisorDecisionItem, Dashboard, Recommendation } from "../types";
import { actionPriorityTone, recommendationLane } from "../lib/viewModels";
import { money, pct, shortDateTime, titleCase } from "../lib/format";
import { ActionImpactPreview } from "../components/visuals/ActionImpactPreview";
import { Badge, CommandButton, DetailDrawer, EmptyState, SignalPanel } from "../components/ui/Primitives";

function laneTone(lane: string) {
  if (lane === "Candidate Adds") return "live";
  if (lane === "Must Review") return "danger";
  if (lane === "Blocked") return "danger";
  return "attention";
}

function confidenceLabel(item: Recommendation) {
  if (item.status === "fail") return "Blocked";
  if (item.confidence >= 0.72 && item.risk_score < 0.35) return "High conviction";
  if (item.confidence >= 0.58) return "Constructive";
  return "Needs evidence";
}

function confidenceFactors(item: Recommendation) {
  return [
    item.data_confidence === "fresh" ? "Fresh data" : item.data_confidence === "sample_only" ? "Sample data penalty" : "Stale data penalty",
    item.expected_return > 0.08 ? "Strong return signal" : "Moderate return signal",
    item.risk_score > 0.42 ? "Risk penalty" : "Risk controlled",
    item.status === "pass" ? "Risk gate passed" : item.status === "watch" ? "Watch gate" : "Risk gate blocked",
  ];
}

function cleanFactor(value: string) {
  const cleaned = value.replace(/_/g, " ");
  if (cleaned.length > 28 || /[.!?]/.test(cleaned)) {
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }
  return titleCase(cleaned);
}

function groupRecommendations(items: Recommendation[]) {
  return [
    {
      lane: "Must Review",
      body: "Portfolio-aware issues and high-impact changes that deserve attention first.",
      items: items.filter((item) => item.action === "TRIM" || (item.risk_flags.length && item.status !== "fail"))
    },
    {
      lane: "Candidate Adds",
      body: "Passed candidates worth researching before any brokerage decision.",
      items: items.filter((item) => recommendationLane(item) === "Do" && item.action !== "TRIM" && !item.risk_flags.length)
    },
    {
      lane: "Watch",
      body: "Interesting, but not strong enough or clean enough to act on now.",
      items: items.filter((item) => recommendationLane(item) === "Watch")
    },
    {
      lane: "Blocked",
      body: "Ideas that cannot be approved because risk or data gates failed.",
      items: items.filter((item) => recommendationLane(item) === "Blocked")
    }
  ];
}

function decisionTone(decision: string) {
  if (["Trim", "Rotate", "Avoid"].includes(decision)) return "danger";
  if (decision === "Wait For Data") return "attention";
  if (["Add", "Stagger Entry"].includes(decision)) return "live";
  return "good";
}

function decisionRank(item: AdvisorDecisionItem) {
  if (item.decision === "Trim") return 0;
  if (item.decision === "Rotate") return 1;
  if (item.decision === "Avoid") return 2;
  if (item.decision === "Add" || item.decision === "Stagger Entry") return 3;
  if (item.decision === "Wait For Data") return 4;
  return 5;
}

export function ActionsView({ dashboard, onAsk }: { dashboard: Dashboard; onAsk: (question?: string) => void }) {
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<AdvisorDecisionItem | null>(null);
  const lanes = useMemo(() => groupRecommendations(dashboard.recent_recommendations), [dashboard.recent_recommendations]);
  const advisorDecision = dashboard.advisor_decision;
  const canonicalFirst = dashboard.advisor_packet.recommendedPriority.firstAction;
  const receipt = dashboard.advisor_packet.decisionReceipt;

  if (advisorDecision) {
    const allDecisions = [...advisorDecision.holding_decisions, ...advisorDecision.opportunity_decisions].sort((a, b) => decisionRank(a) - decisionRank(b));
    const topAction = allDecisions[0];
    const topTrimPlan = topAction?.detail_payload?.trimPlan;
    const canonicalTrimPlan = canonicalFirst?.trimPlan as NonNullable<AdvisorDecisionItem["detail_payload"]>["trimPlan"] | undefined;
    const displayTrimPlan = canonicalTrimPlan ?? topTrimPlan;
    const addCandidates = advisorDecision.opportunity_decisions.filter((item) => item.decision === "Add" || item.decision === "Stagger Entry").slice(0, 4);
    const trims = allDecisions.filter((item) => item.decision === "Trim" || item.decision === "Rotate");
    const holds = advisorDecision.holding_decisions.filter((item) => item.decision === "Hold");
    const waits = allDecisions.filter((item) => item.decision === "Wait For Data" || item.decision === "Avoid");
    return (
      <section className="actions-view actions-redesign screen-enter">
        <SignalPanel className="actions-hero-v2">
          <div>
            <span>Action Brief</span>
            <h1>{canonicalFirst ? `${titleCase(canonicalFirst.action)} ${canonicalFirst.symbol}` : topAction ? `${topAction.decision} ${topAction.symbol}` : "No portfolio action needed yet"}</h1>
            <p>{dashboard.advisor_packet.recommendedPriority.headline || advisorDecision.portfolio_verdict}</p>
            <div className="inline-actions">
              <CommandButton icon={MessageCircle} variant="primary" onClick={() => onAsk("Explain the latest portfolio decision and what I should do first.")}>
                Ask Signal about this decision
              </CommandButton>
            </div>
          </div>
          {topAction && (
            <div className="action-weight-card">
              <span>{displayTrimPlan ? "Estimated trim" : "Current to target"}</span>
              <strong>{displayTrimPlan ? money(displayTrimPlan.estimatedSellValue) : `${pct(topAction.current_weight)} → ${pct(topAction.target_weight)}`}</strong>
              <p>
                {displayTrimPlan
                  ? `${displayTrimPlan.sharesToSellExact} exact shares · ${displayTrimPlan.sharesToSellWhole} whole-share check`
                  : topAction.plain_action}
              </p>
            </div>
          )}
        </SignalPanel>

        <details className="decision-receipt-drawer">
          <summary>
            <span>Decision receipt</span>
            <Badge tone={(receipt.hardGatesTripped?.length ?? 0) ? "watch" : "live"}>
              {(receipt.hardGatesTripped?.length ?? 0) ? `${receipt.hardGatesTripped?.length} gates` : "Clear"}
            </Badge>
          </summary>
          <div className="decision-receipt-strip">
            <div>
              <span>First action</span>
              <strong>{receipt.firstAction ?? "No first action yet"}</strong>
              <p>Advisory-only. No order has been placed.</p>
            </div>
            <div>
              <span>Hard gates</span>
              <strong>{receipt.hardGatesTripped?.length ?? 0}</strong>
              <p>{receipt.hardGatesTripped?.[0] ?? "No hard gate is currently forcing an action."}</p>
            </div>
            <div>
              <span>Model route</span>
              <strong>{dashboard.ai_status.model_router.leadPM.model}</strong>
              <p>
                {titleCase(dashboard.ai_status.model_router.leadPM.reasoningEffort)} reasoning
                {receipt.model ? ` · latest run ${receipt.model}` : ""} · {receipt.promptVersion ?? "prompt tracked"}
              </p>
            </div>
            <div>
              <span>Packet</span>
              <strong>{dashboard.advisor_packet.packetHash.slice(0, 10)}</strong>
              <p>{receipt.nextScheduledReview ? `Next review ${shortDateTime(receipt.nextScheduledReview)}` : "Scheduled review tracked locally."}</p>
            </div>
          </div>
        </details>

        <SignalPanel className="actions-summary-strip">
          <div>
            <span>Reviewed</span>
            <strong>{advisorDecision.holding_decisions.length} holdings</strong>
            <p>{advisorDecision.opportunity_decisions.length} outside candidates compared against the portfolio.</p>
          </div>
          <div>
            <span>Change pressure</span>
            <strong>{trims.length ? `${trims.length} trim/rotate` : "No forced trim"}</strong>
            <p>{trims[0]?.reason ?? "Signal is not forcing a reduction unless risk or evidence changes."}</p>
          </div>
          <div>
            <span>Potential adds</span>
            <strong>{addCandidates.length ? `${addCandidates.length} staged/add` : "No adds now"}</strong>
            <p>{addCandidates[0]?.reason ?? "Outside ideas must beat current holdings after risk, freshness, and turnover."}</p>
          </div>
          <div>
            <span>Wait list</span>
            <strong>{waits.length} not ready</strong>
            <p>{holds.length} holdings can stay as-is at this snapshot.</p>
          </div>
        </SignalPanel>

        <section className="execution-grid" data-testid="action-queue">
          <SignalPanel className="execution-plan-panel">
            <div className="panel-label-row">
              <span>Do next</span>
              <Badge tone={advisorDecision.status === "success" ? "live" : "watch"}>{titleCase(advisorDecision.status)}</Badge>
            </div>
            <div className="execution-steps">
              {advisorDecision.execution_plan.slice(0, 2).map((item, index) => (
                <div key={item}>
                  <strong>{index + 1}</strong>
                  <p>{item}</p>
                </div>
              ))}
            </div>
            {advisorDecision.execution_plan.length > 2 && (
              <details className="mini-disclosure">
                <summary>Show the rest of the plan</summary>
                <div className="risk-note-stack">
                  {advisorDecision.execution_plan.slice(2).map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              </details>
            )}
          </SignalPanel>

          <SignalPanel className="decision-list-panel">
            <div className="panel-label-row">
              <span>Position decisions</span>
              <Badge tone="live">{advisorDecision.holding_decisions.length}</Badge>
            </div>
            <div className="execution-list">
              {advisorDecision.holding_decisions.sort((a, b) => decisionRank(a) - decisionRank(b)).map((item) => (
                <button className={`execution-row ${decisionTone(item.decision)}`} key={`${item.item_type}-${item.id}-${item.symbol}`} onClick={() => setSelectedDecision(item)}>
                  <div className="execution-symbol">
                    <Badge tone={decisionTone(item.decision)}>{item.decision}</Badge>
                    <strong>{item.symbol}</strong>
                    <span>{item.confidence_label}</span>
                  </div>
                  <p>{item.reason}</p>
                  <div className="execution-weight">
                    <span>{pct(item.current_weight)} → {pct(item.target_weight)}</span>
                    {item.detail_payload?.capDistance?.breached && <em>{pct(item.detail_payload.capDistance.over_by)} over cap</em>}
                    <i><b style={{ width: `${Math.min(100, Math.max(4, item.current_weight * 100))}%` }} /></i>
                  </div>
                </button>
              ))}
            </div>
          </SignalPanel>
        </section>

        <SignalPanel className="opportunity-strip-panel">
          <div className="panel-label-row">
            <span>Outside opportunities</span>
            <Badge tone={addCandidates.length ? "live" : "watch"}>{addCandidates.length ? `${addCandidates.length} candidates` : "No adds now"}</Badge>
          </div>
          {addCandidates.length ? (
            <div className="opportunity-strip">
              {addCandidates.map((item) => (
                <button key={`${item.id}-${item.symbol}`} onClick={() => setSelectedDecision(item)}>
                  <Badge tone="live">{item.decision}</Badge>
                  <strong>{item.symbol}</strong>
                  <span>{item.plain_action}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="group-description">Signal PM is not promoting outside adds until they beat the current portfolio after risk, data freshness, and turnover.</p>
          )}
        </SignalPanel>

        <DetailDrawer
          open={Boolean(selectedDecision)}
          onOpenChange={(open) => !open && setSelectedDecision(null)}
          title={selectedDecision ? `${selectedDecision.symbol}: ${selectedDecision.decision}` : "Decision detail"}
          eyebrow="Portfolio decision"
        >
          {selectedDecision && (
            <div className="action-detail">
              <div className="detail-score-row">
                <div>
                  <span>Target</span>
                  <strong>{pct(selectedDecision.target_weight)}</strong>
                </div>
                <div>
                  <span>Current</span>
                  <strong>{pct(selectedDecision.current_weight)}</strong>
                </div>
                <div>
                  <span>Confidence</span>
                  <strong>{selectedDecision.confidence_label}</strong>
                </div>
              </div>
              {selectedDecision.detail_payload?.trimPlan && (
                <section className="decision-receipt-card">
                  <h3>Decision receipt</h3>
                  <p>Advisory-only. No order has been placed.</p>
                  <div className="detail-score-row">
                    <div>
                      <span>Current value</span>
                      <strong>{money(selectedDecision.detail_payload.trimPlan.currentValue)}</strong>
                    </div>
                    <div>
                      <span>Target value</span>
                      <strong>{money(selectedDecision.detail_payload.trimPlan.targetValue)}</strong>
                    </div>
                    <div>
                      <span>Estimated trim</span>
                      <strong>{money(selectedDecision.detail_payload.trimPlan.estimatedSellValue)}</strong>
                    </div>
                    <div>
                      <span>Exact shares</span>
                      <strong>{selectedDecision.detail_payload.trimPlan.sharesToSellExact}</strong>
                    </div>
                    <div>
                      <span>Whole shares</span>
                      <strong>{selectedDecision.detail_payload.trimPlan.sharesToSellWhole}</strong>
                    </div>
                    <div>
                      <span>Post weight</span>
                      <strong>{pct(selectedDecision.detail_payload.trimPlan.estimatedPostWeight)}</strong>
                    </div>
                  </div>
                  <p>
                    Price used: {money(selectedDecision.detail_payload.trimPlan.priceUsed)}
                    {selectedDecision.detail_payload.trimPlan.priceTimestamp ? ` · ${selectedDecision.detail_payload.trimPlan.priceTimestamp}` : ""}
                  </p>
                  {selectedDecision.detail_payload.trimPlan.taxWarning && <p>{selectedDecision.detail_payload.trimPlan.taxWarning}</p>}
                </section>
              )}
              {selectedDecision.detail_payload?.addPlan && (
                <section className="decision-receipt-card">
                  <h3>Stagger plan</h3>
                  <p>Advisory-only. No order has been placed.</p>
                  <div className="risk-note-stack">
                    {selectedDecision.detail_payload.addPlan.trancheSchedule.slice(0, 4).map((tranche) => (
                      <div key={`${tranche.trancheNumber}`}>
                        Tranche {tranche.trancheNumber}: {pct(Number(tranche.estimatedWeight))} · {money(Number(tranche.estimatedDollarAmount))}
                      </div>
                    ))}
                  </div>
                </section>
              )}
              <section>
                <h3>Why</h3>
                <p>{selectedDecision.reason}</p>
                {selectedDecision.reason_code && <p>Reason code: {selectedDecision.reason_code}</p>}
              </section>
              <section>
                <h3>Quant evidence</h3>
                <div className="risk-note-stack">
                  {selectedDecision.quant_evidence.map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              </section>
              <section>
                <h3>Risk and execution</h3>
                <p>{selectedDecision.risk_check}</p>
                <p>{selectedDecision.ai_commentary || advisorDecision.staggering_guidance[0] || "No extra AI commentary attached."}</p>
              </section>
              <section>
                <h3>What would change this</h3>
                <div className="risk-note-stack">
                  {(advisorDecision.what_would_change_my_mind.length ? advisorDecision.what_would_change_my_mind : advisorDecision.entry_conditions).slice(0, 3).map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              </section>
              <div className="drawer-actions">
                <CommandButton icon={selectedDecision.decision === "Avoid" ? ShieldAlert : CheckCircle2} variant={selectedDecision.decision === "Avoid" ? "danger" : "primary"}>
                  Decision reviewed
                </CommandButton>
                <CommandButton icon={MessageCircle} variant="ghost" onClick={() => onAsk(`Explain the ${selectedDecision.symbol} ${selectedDecision.decision} decision.`)}>
                  Ask Signal
                </CommandButton>
              </div>
            </div>
          )}
        </DetailDrawer>
      </section>
    );
  }

  return (
    <section className="actions-view screen-enter">
      <SignalPanel className="actions-command">
        <span>Advisor queue</span>
        <h1>Insight cards, not tickers</h1>
        <p>Every action starts with deterministic quant gates. AI explains and challenges the result, but cannot approve blocked ideas.</p>
        <div className="inline-actions">
          <CommandButton icon={MessageCircle} variant="primary" onClick={() => onAsk("Which action matters most and why?")}>
            Ask about actions
          </CommandButton>
        </div>
        <div className="next-action-strip compact">
          {dashboard.action_items.slice(0, 2).map((item, index) => (
            <div className={`next-action ${actionPriorityTone(item)}`} key={`${item.type}-${item.symbol ?? index}`}>
              <strong>{index + 1}</strong>
              <div>
                <span>{item.priority}</span>
                <p>{item.title}</p>
              </div>
            </div>
          ))}
        </div>
      </SignalPanel>

      <section className="insight-action-board" data-testid="action-queue">
        {lanes.map((lane) => (
          <SignalPanel className={`insight-lane ${laneTone(lane.lane)}`} key={lane.lane}>
            <div className="panel-label-row">
              <span>{lane.lane}</span>
              <Badge tone={laneTone(lane.lane)}>{lane.items.length}</Badge>
            </div>
            <p className="group-description">{lane.body}</p>
            <div className="insight-card-stack">
              {lane.items.length ? (
                lane.items.slice(0, 8).map((item) => (
                  <button className="insight-action-card" key={`${lane.lane}-${item.id}-${item.symbol}`} onClick={() => setSelected(item)}>
                    <div className="insight-action-top">
                      <Badge tone={laneTone(lane.lane)}>{item.action}</Badge>
                      <strong>{item.symbol}</strong>
                      <span>{item.name ?? item.symbol}</span>
                    </div>
                    <p>{item.reason}</p>
                    <div className="confidence-explain">
                      <strong>{confidenceLabel(item)}</strong>
                      <span>{pct(item.confidence)} confidence · target {pct(item.target_weight)}</span>
                    </div>
                    <div className="factor-strip">
                      {confidenceFactors(item).map((factor) => (
                        <i key={factor}>{factor}</i>
                      ))}
                    </div>
                    <dl>
                      <div>
                        <dt>Risk gate</dt>
                        <dd>{item.status === "fail" ? "Blocked" : titleCase(item.status)}</dd>
                      </div>
                      <div>
                        <dt>Freshness</dt>
                        <dd>{item.source_data_age_days}d</dd>
                      </div>
                      <div>
                        <dt>AI critique</dt>
                        <dd>{item.ai_review?.reason ? "Attached" : "Pending"}</dd>
                      </div>
                    </dl>
                  </button>
                ))
              ) : (
                <EmptyState title={`No ${lane.lane.toLowerCase()} items`} body="The robo flow will place ideas here when quant gates produce them." />
              )}
            </div>
          </SignalPanel>
        ))}
      </section>

      <DetailDrawer
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
        title={selected ? `${selected.symbol}: ${selected.action}` : "Action detail"}
        eyebrow={selected?.name ?? "Advisor action"}
      >
        {selected && (
          <div className="action-detail">
            <div className="detail-score-row">
              <div>
                <span>Expected</span>
                <strong>{pct(selected.expected_return)}</strong>
              </div>
              <div>
                <span>Risk</span>
                <strong>{pct(selected.risk_score)}</strong>
              </div>
              <div>
                <span>Source age</span>
                <strong>{selected.source_data_age_days}d</strong>
              </div>
            </div>
            <section>
              <h3>Why this is here</h3>
              <p>{selected.reason}</p>
            </section>
            <ActionImpactPreview recommendation={selected} />
            <section>
              <h3>Risk gate</h3>
              {selected.risk_flags.length ? (
                <div className="risk-note-stack">
                  {selected.risk_flags.map((flag) => (
                    <div key={flag}>{flag}</div>
                  ))}
                </div>
              ) : (
                <p>Passed deterministic risk gates. AI can explain, but cannot override hard rules.</p>
              )}
            </section>
            <section>
              <h3>AI critique</h3>
              <p>{selected.ai_review?.reason ?? "No live AI critique attached to this item yet."}</p>
            </section>
            <div className="drawer-actions">
              <CommandButton icon={selected.status === "fail" ? ShieldAlert : CheckCircle2} variant={selected.status === "fail" ? "danger" : "primary"}>
                {selected.status === "fail" ? "Keep blocked" : "Mark reviewed"}
              </CommandButton>
              <CommandButton icon={BrainCircuit} variant="secondary">
                Open memo
              </CommandButton>
              <CommandButton icon={MessageCircle} variant="ghost" onClick={() => onAsk(`Explain the ${selected.symbol} ${selected.action} recommendation.`)}>
                Ask Signal
              </CommandButton>
            </div>
          </div>
        )}
      </DetailDrawer>
    </section>
  );
}
