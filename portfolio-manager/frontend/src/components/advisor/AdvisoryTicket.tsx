import { useState } from "react";
import type { ReactNode } from "react";
import {
  Calendar,
  ClipboardCheck,
  ClipboardCopy,
  CheckCircle2,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type { AddPlan, AdvisorPacketAction, SelectedPolicy, TrimPlan } from "../../types";
import { money, number, pct, shortDateTime, titleCase } from "../../lib/format";
import { Badge, CommandButton } from "../ui/Primitives";
import { PolicyThresholdBar } from "../policy/PolicyThresholdBar";
import { DataQualityPill } from "../data/DataQualityPill";
import { SourceReceiptBadge } from "../data/SourceReceiptBadge";
import { Glossary } from "../ui/ExplainableTerm";

type Props = {
  action: AdvisorPacketAction;
  policy: SelectedPolicy | null;
  /** Hand the parent a request to open the screen-specific Ask Signal panel. */
  onAsk?: (prompt: string) => void;
  /** Optional callback when the user marks the ticket as reviewed locally. */
  onMarkReviewed?: () => void;
  /** Force a compact, embedded layout (used inside drawers / mobile). */
  compact?: boolean;
  reviewed?: boolean;
};

function complianceLabel(mode?: string): string {
  if (mode === "reduce_only") return "Reduce-only — rounds down. May stay above the threshold.";
  if (mode === "tax_aware_review") return "Tax-aware review — leave the final call to a human.";
  return "Strict — rounds up to cross the policy threshold in a single trade.";
}

function asTrimPlan(action: AdvisorPacketAction): TrimPlan | null {
  return action.trimPlan ?? null;
}

function asAddPlan(action: AdvisorPacketAction): AddPlan | null {
  return action.addPlan ?? null;
}

function buildTicketSummary(action: AdvisorPacketAction): string {
  const trim = asTrimPlan(action);
  const add = asAddPlan(action);
  const head = `ADVISORY TICKET — NO ORDER PLACED\n${action.symbol} · ${titleCase(action.action)}\n`;
  const provenance = `Source: ${action.dataQuality?.provider ?? "n/a"} · ${action.dataQuality?.freshness ?? "n/a"}\n`;
  if (trim) {
    const guidance = trim.executionGuidance;
    const guidanceText = guidance
      ? `Broker checklist: ${titleCase(guidance.recommendedStyle.replace(/_/g, " "))} · ${titleCase(guidance.preferredOrderType.replace(/_/g, " "))}\n` +
        `Suggested limit floor: ${money(guidance.suggestedLimitPrice)} · stop/review below ${money(guidance.stopReviewBelow)}\n` +
        `Slices: ${guidance.slices.map((slice) => `${slice.shares} sh @ ${money(slice.suggestedLimitPrice)}`).join("; ")}\n`
      : "";
    return (
      head +
      provenance +
      `Current: ${pct(action.currentWeight ?? 0)} (${money(trim.currentValue)})\n` +
      `Estimated trim: ${money(trim.estimatedSellValue)}\n` +
      `Exact shares: ${number(trim.sharesToSellExact)}\n` +
      `Whole-share compliant: ${number(trim.sharesToSellWholeCompliant ?? trim.sharesToSellWhole)}\n` +
      `Reduce-only: ${number(trim.sharesToSellWholeReduceOnly ?? trim.sharesToSellWhole)}\n` +
      `Post-weight (compliant): ${pct(trim.estimatedPostWeightCompliant ?? trim.estimatedPostWeight)}\n` +
      `Policy threshold: ${pct(trim.policyThreshold ?? 0)}\n` +
      `Price used: ${money(trim.priceUsed)} · ${shortDateTime(trim.priceTimestamp)}\n` +
      guidanceText +
      `Advisory-only. No order has been placed.`
    );
  }
  if (add) {
    return (
      head +
      provenance +
      `Initial: ${pct(add.initialWeight)} → Target: ${pct(add.targetWeight)}\n` +
      `Tranches: ${add.trancheCount}\n` +
      `Advisory-only. No order has been placed.`
    );
  }
  return head + provenance + `Reason: ${action.explanation}\nAdvisory-only. No order has been placed.`;
}

function ActionRow({ label, value, hint }: { label: ReactNode; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="advisory-ticket-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

/**
 * Premium "advisory ticket" card. Replaces the previous trim summary block
 * and is shared across Home / Actions / drawer / mobile. Renders the math the
 * deterministic engine already produced; never tries to recompute it.
 *
 * Important constraints (V8/V9):
 *  - No "Execute" button while real_money_trading_enabled is false.
 *  - Visible advisory-only / no-order-placed copy.
 *  - Numbers are pulled straight from trimPlan / addPlan / sizingMath; this
 *    component performs no financial math of its own.
 */
export function AdvisoryTicket({
  action,
  policy,
  onAsk,
  onMarkReviewed,
  compact = false,
  reviewed = false,
}: Props) {
  const [copied, setCopied] = useState(false);
  const trim = asTrimPlan(action);
  const add = asAddPlan(action);
  const isTrim = action.action === "TRIM" && !!trim;
  const isAdd = (action.action === "ADD" || action.action === "STAGGER_ENTRY") && !!add;
  const currentWeight = action.currentWeight ?? 0;
  const targetWeight =
    trim?.estimatedPostWeightCompliant ??
    trim?.estimatedPostWeight ??
    action.targetWeight ??
    0;
  const wholeCompliant = trim?.sharesToSellWholeCompliant ?? trim?.sharesToSellWhole ?? 0;
  const wholeReduceOnly = trim?.sharesToSellWholeReduceOnly ?? trim?.sharesToSellWhole ?? 0;
  const wholeMatches = wholeCompliant === wholeReduceOnly;
  const trimGuidance = trim?.executionGuidance;

  const handleCopy = async () => {
    try {
      await navigator.clipboard?.writeText(buildTicketSummary(action));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore — clipboard may be unavailable in some browser contexts
    }
  };

  if (compact) {
    return (
      <article
        className="advisory-ticket compact"
        data-action={action.action.toLowerCase()}
        aria-label={`Advisory ticket summary for ${action.symbol}`}
      >
        <header className="advisory-ticket-head">
          <div className="advisory-ticket-eyebrow">
            <span>Action ticket</span>
            <Badge tone={isTrim ? "watch" : isAdd ? "live" : "neutral"}>{titleCase(action.action)}</Badge>
          </div>
          <div className="advisory-ticket-title">
            <strong>{action.symbol}</strong>
            <em>{action.reasonCode ? titleCase(action.reasonCode) : "deterministic review"}</em>
          </div>
          <p className="advisory-ticket-reason">{action.explanation}</p>
        </header>

        {isTrim && trim ? (
          <section className="advisory-ticket-grid compact-summary">
            <ActionRow label="Current" value={`${pct(currentWeight)} · ${money(trim.currentValue)}`} />
            <ActionRow label="Target" value={pct(action.targetWeight ?? trim.policyThreshold ?? targetWeight)} />
            <ActionRow label="Estimated trim" value={money(trim.estimatedSellValue)} />
            <ActionRow
              label="Whole-share compliant"
              value={`${number(wholeCompliant)} sh`}
              hint={`Exact ${number(trim.sharesToSellExact)} sh`}
            />
            <ActionRow
              label="Post-weight"
              value={pct(trim.estimatedPostWeightCompliant ?? trim.estimatedPostWeight)}
            />
            {trim.priceUsed > 0 && (
              <ActionRow
                label="Price"
                value={money(trim.priceUsed)}
                hint={trim.priceTimestamp ? shortDateTime(trim.priceTimestamp) : undefined}
              />
            )}
            {trimGuidance && (
              <ActionRow
                label="Broker checklist"
                value={titleCase(trimGuidance.recommendedStyle.replace(/_/g, " "))}
                hint={`${titleCase(trimGuidance.preferredOrderType.replace(/_/g, " "))} · ${money(trimGuidance.suggestedLimitPrice)} limit floor`}
              />
            )}
          </section>
        ) : isAdd && add ? (
          <section className="advisory-ticket-grid compact-summary">
            <ActionRow label="Initial" value={pct(add.initialWeight)} />
            <ActionRow label="Target" value={pct(add.targetWeight)} />
            <ActionRow label="Tranches" value={`${add.trancheCount}`} />
            <ActionRow label="Risk budget" value={pct(add.riskBudgetImpact)} />
          </section>
        ) : (
          <section className="advisory-ticket-grid compact-summary">
            <ActionRow label="Action" value={titleCase(action.action)} />
            <ActionRow label="Current weight" value={pct(currentWeight)} />
          </section>
        )}

        <div className="advisory-ticket-compact-foot">
          {action.dataQuality && (
            <DataQualityPill freshness={action.dataQuality.freshness} compact />
          )}
          <span>No order placed</span>
        </div>
      </article>
    );
  }

  return (
    <article
      className={`advisory-ticket ${compact ? "compact" : ""}`.trim()}
      data-action={action.action.toLowerCase()}
      aria-label={`Advisory ticket for ${action.symbol}`}
    >
      <header className="advisory-ticket-head">
        <div className="advisory-ticket-eyebrow">
          <span>Advisory ticket</span>
          <Badge tone="watch">No order placed</Badge>
        </div>
        <div className="advisory-ticket-title">
          <strong>{action.symbol}</strong>
          <em>{titleCase(action.action)} · {action.reasonCode ? titleCase(action.reasonCode) : "deterministic"}</em>
        </div>
        <p className="advisory-ticket-reason">{action.explanation}</p>
      </header>

      {policy && isTrim && (
        <section className="advisory-ticket-section">
          <header>
            <ShieldAlert size={14} />
            <strong>Policy ladder</strong>
          </header>
          <PolicyThresholdBar
            policy={policy.singleStock}
            currentWeight={currentWeight}
            afterWeight={targetWeight}
            symbol={action.symbol}
          />
        </section>
      )}

      {isTrim && trim && (
        <section className="advisory-ticket-grid">
          <ActionRow label="Current" value={`${pct(currentWeight)} · ${money(trim.currentValue)}`} />
          <ActionRow
            label={<Glossary k="compliance_mode">Compliance mode</Glossary>}
            value={titleCase(trim.complianceMode?.replace(/_/g, " ") ?? "strict")}
            hint={complianceLabel(trim.complianceMode)}
          />
          <ActionRow
            label="Estimated trim"
            value={money(trim.estimatedSellValue)}
            hint={`Exact: ${number(trim.sharesToSellExact)} sh`}
          />
          <ActionRow
            label="Whole-share compliant"
            value={`${number(wholeCompliant)} sh`}
            hint={wholeMatches ? "Matches reduce-only floor" : `Reduce-only floor ${number(wholeReduceOnly)} sh`}
          />
          <ActionRow
            label="Post-weight (compliant)"
            value={pct(trim.estimatedPostWeightCompliant ?? trim.estimatedPostWeight)}
            hint={trim.policyThreshold ? `Policy threshold ${pct(trim.policyThreshold)}` : undefined}
          />
          {trim.wouldRemainAboveThresholdIfRoundedDown && (
            <ActionRow
              label="Reduce-only post-weight"
              value={pct(trim.estimatedPostWeightReduceOnly ?? trim.estimatedPostWeight)}
              hint="Reduce-only stays above policy — use compliant trim to clear in one round."
            />
          )}
          {trim.taxWarning && <ActionRow label="Tax" value={trim.taxWarning} />}
        </section>
      )}

      {isTrim && trimGuidance && (
        <section className="advisory-ticket-section trim-execution-guidance">
          <header>
            <ClipboardCheck size={14} />
            <strong>Broker checklist</strong>
            <Badge tone="neutral">{titleCase(trimGuidance.recommendedStyle.replace(/_/g, " "))}</Badge>
          </header>
          <div className="advisory-ticket-grid">
            <ActionRow
              label="Preferred order"
              value={titleCase(trimGuidance.preferredOrderType.replace(/_/g, " "))}
              hint={`${trimGuidance.timeInForce.toUpperCase()} · ${titleCase(trimGuidance.session.replace(/_/g, " "))}`}
            />
            <ActionRow
              label="Suggested limit floor"
              value={money(trimGuidance.suggestedLimitPrice)}
              hint={`Reference ${money(trimGuidance.limitPriceReference)}`}
            />
            <ActionRow
              label="Stop / rerun below"
              value={money(trimGuidance.stopReviewBelow)}
              hint="If the live quote is below this, refresh data and rerun."
            />
            <ActionRow
              label="Slices"
              value={`${trimGuidance.sliceCount}`}
              hint={trimGuidance.slices.map((slice) => `${number(slice.shares)} sh`).join(" · ")}
            />
            {trimGuidance.primaryQuantityBasis === "fractional" && trimGuidance.wholeShareSlices?.length ? (
              <ActionRow
                label="Whole-share fallback"
                value={trimGuidance.wholeShareSlices.map((slice) => `${number(slice.shares)} sh`).join(" · ")}
                hint="Use this if the broker account does not accept fractional share sells."
              />
            ) : null}
            {trimGuidance.singleOrderAlternative ? (
              <ActionRow
                label="All-at-once alternative"
                value={`${number(trimGuidance.singleOrderAlternative.shares)} sh`}
                hint={
                  trimGuidance.allAtOnceAcceptable
                    ? "Reasonable after refreshing the quote."
                    : "Available as a checklist, but staging is preferred for this trim size."
                }
              />
            ) : null}
          </div>
          {trimGuidance.stagingRationale && <p className="advisory-ticket-guidance-note">{trimGuidance.stagingRationale}</p>}
          <ol className="advisory-ticket-guidance-list">
            {trimGuidance.instructions.slice(0, 3).map((instruction) => (
              <li key={instruction}>{instruction}</li>
            ))}
          </ol>
        </section>
      )}

      {isAdd && add && (
        <section className="advisory-ticket-grid">
          <ActionRow label="Initial weight" value={pct(add.initialWeight)} />
          <ActionRow label="Target weight" value={pct(add.targetWeight)} />
          <ActionRow label="Tranches" value={`${add.trancheCount}`} hint="Stagger to manage entry risk." />
          <ActionRow label="Sector impact" value={pct(add.sectorImpact)} />
          <ActionRow label="Risk budget impact" value={pct(add.riskBudgetImpact)} />
          {add.blockers.length > 0 && (
            <ActionRow label="Blockers" value={`${add.blockers.length}`} hint={add.blockers.join(" · ")} />
          )}
        </section>
      )}

      <section className="advisory-ticket-meta">
        {action.dataQuality && (
          <DataQualityPill
            freshness={action.dataQuality.freshness}
            detail={`${action.dataQuality.coverage} · age ${Math.round(action.dataQuality.ageSeconds / 60)} min`}
          />
        )}
        {action.dataQuality && (
          <SourceReceiptBadge
            source={action.dataQuality.provider || "internal"}
            freshness={action.dataQuality.freshness}
            timestamp={action.dataQuality.sourceTimestamp}
            compact
          />
        )}
        {trim?.priceUsed && trim.priceUsed > 0 && (
          <Badge tone="neutral">
            Price {money(trim.priceUsed)}
            {trim.priceTimestamp ? ` · ${shortDateTime(trim.priceTimestamp)}` : ""}
          </Badge>
        )}
      </section>

      <footer className="advisory-ticket-footer">
        <p>
          Advisory-only. No order has been placed. Review taxes, confirm a live price, and acknowledge the policy
          gates before acting in your broker.
        </p>
        <div className="advisory-ticket-actions">
          <CommandButton icon={copied ? CheckCircle2 : ClipboardCopy} variant="secondary" onClick={handleCopy}>
            {copied ? "Copied" : "Copy ticket"}
          </CommandButton>
          {onMarkReviewed && (
            <CommandButton
              icon={ClipboardCheck}
              variant={reviewed ? "primary" : "secondary"}
              onClick={onMarkReviewed}
              disabled={reviewed}
            >
              {reviewed ? "Reviewed" : "Mark reviewed"}
            </CommandButton>
          )}
          {onAsk && (
            <CommandButton
              icon={Sparkles}
              variant="quiet"
              onClick={() => onAsk(`Explain the ${action.symbol} ${action.action.toLowerCase()} advisory ticket: why now, what data, and what would change it.`)}
            >
              Ask Signal
            </CommandButton>
          )}
          {action.dataQuality?.sourceTimestamp && (
            <span className="advisory-ticket-stamp">
              <Calendar size={12} aria-hidden="true" />
              Source {shortDateTime(action.dataQuality.sourceTimestamp)}
            </span>
          )}
        </div>
      </footer>
    </article>
  );
}
