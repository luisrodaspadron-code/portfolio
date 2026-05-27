import { useMemo } from "react";
import { ArrowRight } from "lucide-react";
import type { AdvisorPacket } from "../../types";
import { money, pct, shortDateTime, signedMoney } from "../../lib/format";
import { Badge, DetailDrawer, EmptyState } from "../ui/Primitives";
import {
  computePacketDiff,
  loadPreviousPacketSnapshot,
  packetToSnapshot,
} from "../../lib/packetSnapshot";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  packet: AdvisorPacket | null | undefined;
};

function Row({
  label,
  before,
  after,
  tone,
}: {
  label: string;
  before: React.ReactNode;
  after: React.ReactNode;
  tone?: "good" | "watch" | "fail" | "neutral";
}) {
  return (
    <div className={`compare-row tone-${tone ?? "neutral"}`}>
      <span className="compare-label">{label}</span>
      <div className="compare-values">
        <div>{before}</div>
        <ArrowRight size={14} aria-hidden="true" />
        <strong>{after}</strong>
      </div>
    </div>
  );
}

/**
 * Drawer that diffs the current advisor packet against the previous one
 * snapshotted in localStorage. Purely client-side; no network calls.
 */
export function CompareRunDrawer({ open, onOpenChange, packet }: Props) {
  const previous = useMemo(
    () => (packet ? loadPreviousPacketSnapshot(packet.packetHash) : null),
    [packet?.packetHash, open],
  );

  return (
    <DetailDrawer
      open={open}
      onOpenChange={onOpenChange}
      eyebrow="Compare runs"
      title="Since the last run"
    >
      {!packet ? (
        <EmptyState
          title="No current run"
          body="Run the advisor to generate a packet, then we can diff it against the previous one."
        />
      ) : !previous ? (
        <EmptyState
          title="No previous run captured yet"
          body="Once a second run completes, the drawer will diff the new packet against the previous one — portfolio value, risk, first action, data quality, blockers, and model route."
        />
      ) : (
        (() => {
          const current = packetToSnapshot(packet);
          const diff = computePacketDiff(previous, current);
          const valueTone = diff.portfolioValueChange === 0 ? "neutral" : diff.portfolioValueChange > 0 ? "good" : "watch";
          const riskTone = diff.riskIssueChange === 0 ? "neutral" : diff.riskIssueChange < 0 ? "good" : "fail";
          return (
            <div className="compare-run-drawer-body">
              <header className="compare-summary">
                <div>
                  <span>Previous</span>
                  <strong>{previous.packetHash.slice(0, 10) || "—"}</strong>
                  <em>{previous.generatedAt ? shortDateTime(previous.generatedAt) : "—"}</em>
                </div>
                <ArrowRight size={16} aria-hidden="true" />
                <div>
                  <span>Current</span>
                  <strong>{current.packetHash.slice(0, 10) || "—"}</strong>
                  <em>{current.generatedAt ? shortDateTime(current.generatedAt) : "—"}</em>
                </div>
              </header>

              <Row
                label="Portfolio value"
                before={money(previous.portfolioValue)}
                after={(
                  <>
                    {money(current.portfolioValue)}
                    <Badge tone={valueTone}>{signedMoney(diff.portfolioValueChange)}</Badge>
                  </>
                )}
                tone={valueTone}
              />

              <Row
                label="Risk issues"
                before={`${previous.riskIssueCount}`}
                after={(
                  <>
                    {current.riskIssueCount}
                    <Badge tone={riskTone}>
                      {diff.riskIssueChange === 0 ? "no change" : `${diff.riskIssueChange > 0 ? "+" : ""}${diff.riskIssueChange}`}
                    </Badge>
                  </>
                )}
                tone={riskTone}
              />

              <Row
                label="First action"
                before={previous.firstAction}
                after={(
                  <>
                    {current.firstAction}
                    {diff.firstActionChanged && <Badge tone="watch">Changed</Badge>}
                  </>
                )}
                tone={diff.firstActionChanged ? "watch" : "neutral"}
              />

              <Row
                label="Data quality"
                before={previous.freshness}
                after={(
                  <>
                    {current.freshness}
                    {diff.freshnessChanged && <Badge tone="watch">Changed</Badge>}
                  </>
                )}
                tone={diff.freshnessChanged ? "watch" : "neutral"}
              />

              <Row
                label="Model route"
                before={`${previous.modelRoute} · ${previous.reasoningEffort}`}
                after={(
                  <>
                    {current.modelRoute} · {current.reasoningEffort}
                    {diff.modelRouteChanged && <Badge tone="watch">Updated</Badge>}
                  </>
                )}
                tone={diff.modelRouteChanged ? "watch" : "neutral"}
              />

              <Row
                label="First-action weight"
                before={pct(previous.firstActionWeight)}
                after={<>{pct(current.firstActionWeight)} → {pct(current.firstActionTarget)}</>}
                tone="neutral"
              />

              <section className="compare-block">
                <header>
                  <strong>New blockers</strong>
                  <Badge tone={diff.newlyBlocked.length ? "fail" : "good"}>
                    {diff.newlyBlocked.length ? `${diff.newlyBlocked.length}` : "None"}
                  </Badge>
                </header>
                {diff.newlyBlocked.length ? (
                  <ul>
                    {diff.newlyBlocked.map((message) => (
                      <li key={message}>{message}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No new hard gates tripped versus the previous run.</p>
                )}
              </section>

              <section className="compare-block">
                <header>
                  <strong>Cleared blockers</strong>
                  <Badge tone={diff.clearedBlocked.length ? "good" : "neutral"}>
                    {diff.clearedBlocked.length ? `${diff.clearedBlocked.length}` : "None"}
                  </Badge>
                </header>
                {diff.clearedBlocked.length ? (
                  <ul>
                    {diff.clearedBlocked.map((message) => (
                      <li key={message}>{message}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No previously blocked actions have cleared yet.</p>
                )}
              </section>

              <footer className="compare-footer">
                Diff is client-side, generated from canonical packet snapshots. Advisory-only — no order has been placed.
              </footer>
            </div>
          );
        })()
      )}
    </DetailDrawer>
  );
}
