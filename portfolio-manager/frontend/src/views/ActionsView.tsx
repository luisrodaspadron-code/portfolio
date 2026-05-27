import { useMemo, useState } from "react";
import { BrainCircuit, CheckCircle2, MessageCircle, ShieldAlert } from "lucide-react";
import type { AdvisorDecisionItem, Dashboard, Recommendation } from "../types";
import { actionPriorityTone, recommendationLane } from "../lib/viewModels";
import { money, pct, shortDateTime, titleCase } from "../lib/format";
import { ActionImpactPreview } from "../components/visuals/ActionImpactPreview";
import { DecisionReceiptCard } from "../components/advisor/DecisionReceiptCard";
import { StaggerTimeline } from "../components/advisor/StaggerTimeline";
import { Badge, CommandButton, DetailDrawer, EmptyState, SignalPanel } from "../components/ui/Primitives";
import { OpportunityLab } from "../components/opportunities/OpportunityLab";

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
  const packet = dashboard.advisor_packet;
  const canonicalFirst = packet.recommendedPriority.firstAction;
  const receipt = packet.decisionReceipt;
  const packetPositions = packet.positions;
  const packetCandidates = packet.candidates;

  if (advisorDecision || packetPositions.length) {
    const allDecisions = advisorDecision
      ? [...advisorDecision.holding_decisions, ...advisorDecision.opportunity_decisions].sort((a, b) => decisionRank(a) - decisionRank(b))
      : [];
    const topAction = allDecisions[0];
    const topTrimPlan = topAction?.detail_payload?.trimPlan;
    const canonicalTrimPlan = canonicalFirst?.trimPlan as NonNullable<AdvisorDecisionItem["detail_payload"]>["trimPlan"] | undefined;
    const displayTrimPlan = canonicalTrimPlan ?? topTrimPlan;
    const addCandidates = packetCandidates.filter((item) => item.action === "ADD" || item.action === "STAGGER_ENTRY").slice(0, 4);
    const trims = packetPositions.filter((item) => item.action === "TRIM");
    const holds = packetPositions.filter((item) => item.action === "HOLD");
    const waits = [...packetPositions, ...packetCandidates].filter((item) => item.action === "WAIT_FOR_DATA" || item.action === "BLOCKED_BY_RISK");
    return (
      <section className="actions-view actions-redesign screen-enter">
        <SignalPanel className="actions-hero-v2">
          <div>
            <span>Action Brief</span>
            <h1>{canonicalFirst ? `${titleCase(canonicalFirst.action)} ${canonicalFirst.symbol}` : topAction ? `${topAction.decision} ${topAction.symbol}` : "No portfolio action needed yet"}</h1>
            <p>{packet.recommendedPriority.headline || advisorDecision?.portfolio_verdict || "Run the advisor to build an action brief."}</p>
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
                  ? `${displayTrimPlan.sharesToSellExact} exact · ${displayTrimPlan.sharesToSellWholeCompliant ?? displayTrimPlan.sharesToSellWhole} compliant whole shares · ${displayTrimPlan.sharesToSellWholeReduceOnly ?? displayTrimPlan.sharesToSellWhole} reduce-only`
                  : topAction.plain_action}
              </p>
            </div>
          )}
        </SignalPanel>

        <details className="decision-receipt-drawer" open>
          <summary>
            <span>Decision receipt</span>
            <Badge tone={(receipt.hardGatesTripped?.length ?? 0) ? "watch" : "live"}>
              {(receipt.hardGatesTripped?.length ?? 0) ? `${receipt.hardGatesTripped?.length} gates` : "Clear"}
            </Badge>
          </summary>
          <DecisionReceiptCard dashboard={dashboard} compact />
        </details>

        <SignalPanel className="actions-summary-strip">
          <div>
            <span>Reviewed</span>
            <strong>{advisorDecision?.holding_decisions.length ?? packetPositions.length} holdings</strong>
            <p>{packetCandidates.length} outside candidates compared against the portfolio.</p>
          </div>
          <div>
            <span>Change pressure</span>
            <strong>{trims.length ? `${trims.length} trim/rotate` : "No forced trim"}</strong>
            <p>{trims[0]?.explanation ?? "Signal is not forcing a reduction unless risk or evidence changes."}</p>
          </div>
          <div>
            <span>Potential adds</span>
            <strong>{addCandidates.length ? `${addCandidates.length} staged/add` : "No adds now"}</strong>
            <p>{addCandidates[0]?.explanation ?? "Outside ideas must beat current holdings after risk, freshness, and turnover."}</p>
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
              <Badge tone={advisorDecision?.status === "success" ? "live" : "watch"}>{titleCase(advisorDecision?.status ?? "ready")}</Badge>
            </div>
            <div className="execution-steps">
              {(packet.recommendedPriority.doNext.length ? packet.recommendedPriority.doNext : advisorDecision?.execution_plan ?? []).slice(0, 2).map((item, index) => (
                <div key={item}>
                  <strong>{index + 1}</strong>
                  <p>{item}</p>
                </div>
              ))}
            </div>
            {advisorDecision && advisorDecision.execution_plan.length > 2 && (
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
              <Badge tone="live">{packetPositions.length}</Badge>
            </div>
            <div className="execution-list">
              {packetPositions.map((item) => (
                <button
                  className={`execution-row ${decisionTone(item.action === "TRIM" ? "Trim" : item.action === "HOLD" ? "Hold" : item.action === "WAIT_FOR_DATA" ? "Wait For Data" : "Add")}`}
                  key={`packet-${item.symbol}`}
                  onClick={() => {
                    const existing = advisorDecision?.holding_decisions.find((row) => row.symbol === item.symbol);
                    if (existing) {
                      setSelectedDecision(existing);
                      return;
                    }
                    setSelectedDecision({
                      id: 0,
                      decision_run_id: 0,
                      symbol: item.symbol,
                      item_type: "holding",
                      decision: item.action === "TRIM" ? "Trim" : item.action === "HOLD" ? "Hold" : item.action === "WAIT_FOR_DATA" ? "Wait For Data" : "Add",
                      plain_action: `${item.action} ${item.symbol}`,
                      reason: item.explanation,
                      target_weight: item.targetWeight ?? 0,
                      current_weight: item.currentWeight ?? 0,
                      confidence_label: item.reasonCode,
                      confidence_score: item.confidence ?? 0,
                      eligibility: "eligible",
                      risk_check: item.blockers.join("; "),
                      quant_evidence: item.confidenceDrivers,
                      source_freshness: item.dataQuality?.freshness ?? "",
                      reason_code: item.reasonCode,
                      ai_commentary: "",
                      created_at: "",
                      detail_payload: {
                        trimPlan: item.trimPlan as NonNullable<AdvisorDecisionItem["detail_payload"]>["trimPlan"],
                        addPlan: item.addPlan as NonNullable<AdvisorDecisionItem["detail_payload"]>["addPlan"]
                      }
                    });
                  }}
                >
                  <div className="execution-symbol">
                    <Badge tone={decisionTone(item.action === "TRIM" ? "Trim" : "Hold")}>{titleCase(item.action.replace(/_/g, " "))}</Badge>
                    <strong>{item.symbol}</strong>
                    <span>{item.reasonCode}</span>
                  </div>
                  <p>{item.explanation}</p>
                  <div className="execution-weight">
                    <span>
                      {pct(item.currentWeight ?? 0)} → {pct(item.targetWeight ?? 0)}
                    </span>
                    {item.trimPlan && typeof item.trimPlan === "object" && "estimatedSellValue" in item.trimPlan ? (
                      <em>{money(Number((item.trimPlan as { estimatedSellValue?: number }).estimatedSellValue ?? 0))} trim estimate</em>
                    ) : null}
                    <i>
                      <b style={{ width: `${Math.min(100, Math.max(4, (item.currentWeight ?? 0) * 100))}%` }} />
                    </i>
                  </div>
                </button>
              ))}
            </div>
          </SignalPanel>
        </section>

        <OpportunityLab
          candidates={packetCandidates}
          onAsk={onAsk}
          onSelect={(item) => {
            const existing = advisorDecision?.opportunity_decisions.find((row) => row.symbol === item.symbol);
            if (existing) {
              setSelectedDecision(existing);
              return;
            }
            setSelectedDecision({
              id: 0,
              decision_run_id: 0,
              symbol: item.symbol,
              item_type: "opportunity",
              decision: item.action === "STAGGER_ENTRY" ? "Stagger Entry" : "Add",
              plain_action: `${item.action} ${item.symbol}`,
              reason: item.explanation,
              target_weight: item.targetWeight ?? 0,
              current_weight: item.currentWeight ?? 0,
              confidence_label: item.reasonCode,
              confidence_score: item.confidence ?? 0,
              eligibility: "pass",
              risk_check: item.blockers.join("; "),
              quant_evidence: item.confidenceDrivers,
              source_freshness: item.dataQuality?.freshness ?? "",
              reason_code: item.reasonCode,
              ai_commentary: "",
              created_at: "",
              detail_payload: { addPlan: item.addPlan ?? undefined },
            });
          }}
        />

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
                      <span>Whole shares (compliant)</span>
                      <strong>{selectedDecision.detail_payload.trimPlan.sharesToSellWholeCompliant ?? selectedDecision.detail_payload.trimPlan.sharesToSellWhole}</strong>
                      <small>
                        Reduce-only: {selectedDecision.detail_payload.trimPlan.sharesToSellWholeReduceOnly ?? selectedDecision.detail_payload.trimPlan.sharesToSellWhole}
                      </small>
                    </div>
                    <div>
                      <span>Post weight (compliant)</span>
                      <strong>{pct(selectedDecision.detail_payload.trimPlan.estimatedPostWeightCompliant ?? selectedDecision.detail_payload.trimPlan.estimatedPostWeight)}</strong>
                      {selectedDecision.detail_payload.trimPlan.policyThreshold ? (
                        <small>Threshold: {pct(selectedDecision.detail_payload.trimPlan.policyThreshold)}</small>
                      ) : null}
                    </div>
                  </div>
                  <p className="trim-compliance-mode">
                    Compliance mode: {titleCase((selectedDecision.detail_payload.trimPlan.complianceMode ?? "strict_below_threshold").replace(/_/g, " "))}
                    {selectedDecision.detail_payload.trimPlan.wouldRemainAboveThresholdIfRoundedDown
                      ? " · Reduce-only floor would still stay above the policy threshold."
                      : ""}
                  </p>
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
                  <StaggerTimeline schedule={selectedDecision.detail_payload.addPlan.trancheSchedule} symbol={selectedDecision.symbol} />
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
                <h3>Risk and remediation</h3>
                <p>{selectedDecision.risk_check}</p>
                <p>{selectedDecision.ai_commentary || advisorDecision?.staggering_guidance?.[0] || "No extra AI commentary attached."}</p>
                <p className="risk-note-footer">Advisory-only. No order has been placed.</p>
              </section>
              <section>
                <h3>What would change this</h3>
                <div className="risk-note-stack">
                  {((advisorDecision?.what_would_change_my_mind.length ? advisorDecision.what_would_change_my_mind : advisorDecision?.entry_conditions) ?? []).slice(0, 3).map((item) => (
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
