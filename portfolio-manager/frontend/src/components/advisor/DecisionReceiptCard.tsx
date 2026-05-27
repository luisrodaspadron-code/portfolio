import type { AdvisorPacket, Dashboard } from "../../types";
import { money, number, pct, shortDateTime, titleCase } from "../../lib/format";
import { Badge } from "../ui/Primitives";

function trimMathFromPacket(dashboard: Dashboard) {
  const math = dashboard.advisor_packet?.decisionReceipt?.sizingMath;
  const first = dashboard.advisor_packet?.recommendedPriority?.firstAction;
  if (!math || !first) return null;
  const compliantWhole = math.sharesToSellWholeCompliant ?? math.sharesToSellWhole;
  const reduceOnlyWhole = math.sharesToSellWholeReduceOnly ?? math.sharesToSellWhole;
  return {
    symbol: first.symbol,
    currentWeight: first.currentWeight ?? 0,
    targetWeight: first.targetWeight ?? 0,
    sellValue: Number(math.estimatedSellValue ?? 0),
    exactShares: Number(math.sharesToSellExact ?? 0),
    wholeShares: Number(math.sharesToSellWhole ?? 0),
    wholeSharesCompliant: Number(compliantWhole ?? 0),
    wholeSharesReduceOnly: Number(reduceOnlyWhole ?? 0),
    fractionalCompliant: Number(math.sharesToSellFractionalCompliant ?? 0),
    postWeight: Number(math.estimatedPostWeight ?? 0),
    postWeightCompliant: Number(math.estimatedPostWeightCompliant ?? math.estimatedPostWeight ?? 0),
    postWeightReduceOnly: Number(math.estimatedPostWeightReduceOnly ?? math.estimatedPostWeight ?? 0),
    wouldRemainAbove: Boolean(math.wouldRemainAboveThresholdIfRoundedDown ?? false),
    policyThreshold: Number(math.policyThreshold ?? 0),
    complianceMode: typeof math.complianceMode === "string" ? math.complianceMode : "strict_below_threshold",
    priceUsed: Number(math.priceUsed ?? 0),
    priceTimestamp: typeof math.priceTimestamp === "string" ? math.priceTimestamp : ""
  };
}

function complianceLabel(mode: string): string {
  if (mode === "reduce_only") return "Reduce-only (rounds down; may stay over)";
  if (mode === "tax_aware_review") return "Tax-aware review (advisory)";
  return "Compliant (rounds up to cross threshold)";
}

export function DecisionReceiptCard({
  dashboard,
  compact = false
}: {
  dashboard: Dashboard;
  compact?: boolean;
}) {
  const packet = dashboard.advisor_packet;
  const receipt = packet?.decisionReceipt;
  const first = packet?.recommendedPriority?.firstAction;
  const sizing = trimMathFromPacket(dashboard);

  if (!receipt) {
    return (
      <div className="decision-receipt-card empty">
        <p>Run the advisor to generate a decision receipt.</p>
      </div>
    );
  }

  return (
    <div className={`decision-receipt-card ${compact ? "compact" : ""}`}>
      <div className="decision-receipt-head">
        <div>
          <span>Decision receipt</span>
          <strong>{receipt.firstAction ?? (first ? `${titleCase(first.action)} ${first.symbol}` : "No first action")}</strong>
        </div>
        <Badge tone={(receipt.hardGatesTripped?.length ?? 0) ? "watch" : "live"}>
          {(receipt.hardGatesTripped?.length ?? 0) ? `${receipt.hardGatesTripped?.length} gates` : "Clear"}
        </Badge>
      </div>

      {sizing && first?.action === "TRIM" && (
        <div className="receipt-math-grid">
          <div>
            <span>Weight shift</span>
            <strong>
              {pct(sizing.currentWeight)} → {pct(sizing.targetWeight)}
            </strong>
          </div>
          <div>
            <span>Estimated trim</span>
            <strong>{money(sizing.sellValue)}</strong>
          </div>
          <div>
            <span>Compliance mode</span>
            <strong>{titleCase(sizing.complianceMode.replace(/_/g, " "))}</strong>
            <small>{complianceLabel(sizing.complianceMode)}</small>
          </div>
          <div>
            <span>Suggested whole-share trim</span>
            <strong>{number(sizing.wholeSharesCompliant)}</strong>
            <small>
              Reduce-only floor: {number(sizing.wholeSharesReduceOnly)} ·
              Exact: {sizing.exactShares.toFixed(4)}
            </small>
          </div>
          <div>
            <span>Post-action weight (compliant)</span>
            <strong>{pct(sizing.postWeightCompliant)}</strong>
            {sizing.policyThreshold > 0 && (
              <small>Policy threshold: {pct(sizing.policyThreshold)}</small>
            )}
          </div>
          {sizing.wholeSharesReduceOnly !== sizing.wholeSharesCompliant && (
            <div>
              <span>Reduce-only post-weight</span>
              <strong>{pct(sizing.postWeightReduceOnly)}</strong>
              {sizing.wouldRemainAbove && (
                <small className="receipt-warning">
                  Reduce-only stays above the policy threshold — use compliant trim if a single round is required.
                </small>
              )}
            </div>
          )}
          {sizing.priceUsed > 0 && (
            <div>
              <span>Price used</span>
              <strong>
                {money(sizing.priceUsed)}
                {sizing.priceTimestamp ? ` · ${shortDateTime(sizing.priceTimestamp)}` : ""}
              </strong>
            </div>
          )}
        </div>
      )}

      <div className="decision-receipt-strip">
        <div>
          <span>Hard gates</span>
          <strong>{receipt.hardGatesTripped?.length ?? 0}</strong>
          <p>{receipt.hardGatesTripped?.[0] ?? "No hard gate is currently forcing an action."}</p>
        </div>
        <div>
          <span>Model route</span>
          <strong>{receipt.model ?? dashboard.ai_status.model_router.leadPM.model}</strong>
          <p>
            {titleCase(receipt.reasoningEffort ?? dashboard.ai_status.model_router.leadPM.reasoningEffort)} reasoning
            {receipt.promptVersion ? ` · ${receipt.promptVersion}` : ""}
          </p>
        </div>
        <div>
          <span>Engine</span>
          <strong>{receipt.deterministicEngineVersion ?? packet.audit.deterministicEngineVersion}</strong>
          <p>{receipt.nextScheduledReview ? `Next review ${shortDateTime(receipt.nextScheduledReview)}` : "Scheduled review tracked locally."}</p>
        </div>
        <div>
          <span>Packet</span>
          <strong>{packet.packetHash.slice(0, 10)}</strong>
          <p>{receipt.runId ? `Run ${receipt.runId}` : "Latest canonical packet"}</p>
        </div>
      </div>

      {(receipt.dataLimitations?.length ?? 0) > 0 && (
        <div className="decision-receipt-limits">
          <span>Data limitations</span>
          <ul>
            {receipt.dataLimitations?.slice(0, 3).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="decision-receipt-footer">Advisory-only. No order has been placed.</p>
    </div>
  );
}

export { trimMathFromPacket };
