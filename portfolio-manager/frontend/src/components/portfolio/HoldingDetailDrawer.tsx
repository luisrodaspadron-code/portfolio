import { useState } from "react";
import { MessageCircle } from "lucide-react";
import type { AdvisorPacketAction, Position } from "../../types";
import { money, number, pct, titleCase } from "../../lib/format";
import { PolicyThresholdBar } from "../policy/PolicyThresholdBar";
import { pickSelectedPolicy } from "../policy/SelectedPolicyCard";
import type { Dashboard } from "../../types";
import { CommandButton, DetailDrawer } from "../ui/Primitives";
import { SourceReceiptBadge } from "../data/SourceReceiptBadge";

type PacketTrimPlan = {
  targetValue: number;
  estimatedSellValue: number;
  sharesToSellExact: number;
  sharesToSellWhole?: number;
  sharesToSellWholeCompliant?: number;
  sharesToSellWholeReduceOnly?: number;
  estimatedPostWeight: number;
  estimatedPostWeightCompliant?: number;
  estimatedPostWeightReduceOnly?: number;
  priceUsed: number;
  priceTimestamp?: string;
  priceSource?: string;
  taxWarning?: string;
};

type TabId = "overview" | "math" | "risk" | "data" | "history" | "ask";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "math", label: "Math" },
  { id: "risk", label: "Risk" },
  { id: "data", label: "Data" },
  { id: "history", label: "History" },
  { id: "ask", label: "Ask" },
];

function actionLabel(action?: string) {
  return action ? titleCase(action.replace(/_/g, " ")) : "Waiting";
}

function maxBreachOver(decision?: AdvisorPacketAction | null) {
  return Math.max(0, ...(decision?.riskBreaches ?? []).map((breach) => breach.observed - breach.limit));
}

export function HoldingDetailDrawer({
  dashboard,
  position,
  open,
  onOpenChange,
  onAsk,
}: {
  dashboard: Dashboard;
  position: Position | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAsk: (question?: string) => void;
}) {
  const [tab, setTab] = useState<TabId>("overview");
  const decision = position
    ? dashboard.advisor_packet.positions.find((item) => item.symbol === position.symbol) ?? null
    : null;
  const trimPlan = decision?.trimPlan as PacketTrimPlan | null | undefined;
  const policy = pickSelectedPolicy(dashboard);
  const capOver = maxBreachOver(decision);
  const askPrompts = position
    ? [
        `Why is ${position.symbol} ${actionLabel(decision?.action)}?`,
        `What happens if I trim less of ${position.symbol}?`,
        `How does ${position.symbol} affect sector risk?`,
        `What data is missing for ${position.symbol}?`,
        `What would change the decision on ${position.symbol}?`,
      ]
    : [];

  return (
    <DetailDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={position ? `${position.symbol} · ${actionLabel(decision?.action)}` : "Holding detail"}
      eyebrow={decision?.riskBreaches.length ? "Risk remediation" : "Real holding"}
    >
      {position && (
        <div className="holding-detail-drawer" data-testid="holding-detail-drawer">
          {policy && decision && (
            <PolicyThresholdBar
              policy={policy.singleStock}
              currentWeight={position.weight}
              symbol={position.symbol}
              afterWeight={decision.targetWeight}
            />
          )}

          <div className="holding-detail-tabs" role="tablist" aria-label="Holding detail sections">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                className={tab === item.id ? "active" : ""}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <section className="holding-detail-panel">
              <div className="detail-score-row">
                <div><span>Value</span><strong>{money(position.market_value)}</strong></div>
                <div><span>Weight</span><strong>{pct(position.weight)}</strong></div>
                <div><span>Action</span><strong>{actionLabel(decision?.action)}</strong></div>
                <div><span>Target</span><strong>{decision?.targetWeight !== undefined ? pct(decision.targetWeight) : "Pending"}</strong></div>
              </div>
              <p>{decision?.explanation ?? position.valuation_note}</p>
              {decision?.blockers.map((blocker) => (
                <div className="drawer-risk-note" key={blocker}>{blocker}</div>
              ))}
            </section>
          )}

          {tab === "math" && (
            <section className="holding-detail-panel">
              {trimPlan ? (
                <>
                  <div className="detail-score-row">
                    <div><span>Exact shares</span><strong>{number(trimPlan.sharesToSellExact)}</strong></div>
                    <div><span>Whole-share compliant</span><strong>{trimPlan.sharesToSellWholeCompliant ?? trimPlan.sharesToSellWhole ?? "n/a"}</strong></div>
                    <div><span>Reduce-only</span><strong>{trimPlan.sharesToSellWholeReduceOnly ?? trimPlan.sharesToSellWhole ?? "n/a"}</strong></div>
                    <div><span>Estimated trim</span><strong>{money(trimPlan.estimatedSellValue)}</strong></div>
                    <div><span>Post weight</span><strong>{pct(trimPlan.estimatedPostWeightCompliant ?? trimPlan.estimatedPostWeight)}</strong></div>
                    <div><span>Price used</span><strong>{money(trimPlan.priceUsed)}</strong></div>
                  </div>
                  {trimPlan.taxWarning && <p>{trimPlan.taxWarning}</p>}
                </>
              ) : (
                <p>No sizing math is attached to this holding yet. Run the advisor after importing holdings.</p>
              )}
            </section>
          )}

          {tab === "risk" && (
            <section className="holding-detail-panel">
              <div className="detail-score-row">
                <div><span>Cap distance</span><strong>{capOver > 0 ? `${pct(capOver)} over` : "Within rule"}</strong></div>
                <div><span>Sector</span><strong>{position.sector}</strong></div>
              </div>
              {decision?.riskBreaches.length ? (
                decision.riskBreaches.map((breach) => (
                  <div className="drawer-risk-note" key={breach.id}>
                    {breach.message}
                    {breach.blocksAdds ? " New similar exposure is blocked until this clears." : ""}
                  </div>
                ))
              ) : (
                <p>No active breach on this symbol.</p>
              )}
            </section>
          )}

          {tab === "data" && (
            <section className="holding-detail-panel">
              <SourceReceiptBadge
                source={decision?.dataQuality.provider ?? position.valuation_status}
                freshness={decision?.dataQuality.freshness ?? position.valuation_status}
              />
              <div className="detail-score-row">
                <div><span>Coverage</span><strong>{titleCase(decision?.dataQuality.coverage ?? "unknown")}</strong></div>
                <div><span>Confidence</span><strong>{decision?.confidence !== undefined ? pct(decision.confidence) : "—"}</strong></div>
              </div>
              {(decision?.dataQuality.warnings ?? [position.valuation_note]).map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </section>
          )}

          {tab === "history" && (
            <section className="holding-detail-panel">
              <p>
                Latest packet: {actionLabel(decision?.action)} at {pct(position.weight)}
                {decision?.targetWeight !== undefined ? ` toward ${pct(decision.targetWeight)}` : ""}.
              </p>
              <p>Prior run history will appear here after multiple advisor cycles are saved locally.</p>
            </section>
          )}

          {tab === "ask" && (
            <section className="holding-detail-panel">
              <div className="ask-prompt-grid">
                {askPrompts.map((prompt) => (
                  <CommandButton key={prompt} icon={MessageCircle} variant="ghost" onClick={() => onAsk(prompt)}>
                    {prompt}
                  </CommandButton>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </DetailDrawer>
  );
}
