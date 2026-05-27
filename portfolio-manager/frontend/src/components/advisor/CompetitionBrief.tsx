import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "motion/react";
import { Trophy, X } from "lucide-react";
import type { Dashboard } from "../../types";
import { money, pct, shortDateTime } from "../../lib/format";
import { pickSelectedPolicy } from "../policy/SelectedPolicyCard";
import { ActionTimeline } from "./ActionTimeline";
import { Badge, IconSlot } from "../ui/Primitives";

export function CompetitionBrief({
  open,
  onOpenChange,
  dashboard,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dashboard: Dashboard;
}) {
  const packet = dashboard.advisor_packet;
  const first = packet.recommendedPriority.firstAction;
  const receipt = packet.decisionReceipt;
  const policy = pickSelectedPolicy(dashboard);
  const topCandidate = packet.candidates.find((item) => item.action === "ADD" || item.action === "STAGGER_ENTRY");
  const real = dashboard.real_portfolio;
  const largestPosition = real?.positions.reduce(
    (largest, position) => (!largest || position.weight > largest.weight ? position : largest),
    real.positions[0],
  );
  const topRisk = packet.portfolioRisk.singleNameBreaches[0]?.message
    ?? (largestPosition ? `${largestPosition.symbol} at ${pct(largestPosition.weight)}` : "Import holdings to assess risk.");

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div className="palette-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.section
                className="competition-brief"
                data-testid="competition-brief"
                initial={{ opacity: 0, y: 16, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 16, scale: 0.98 }}
              >
                <header>
                  <div>
                    <span>Competition brief</span>
                    <h2>Judge-ready portfolio summary</h2>
                    <p>
                      Competition mode increases risk budget but keeps drawdown, liquidity, and data-quality controls active.
                    </p>
                  </div>
                  <Dialog.Close asChild>
                    <button type="button" className="icon-button" aria-label="Close competition brief">
                      <IconSlot icon={X} />
                    </button>
                  </Dialog.Close>
                </header>

                <div className="competition-brief-grid">
                  <article>
                    <Trophy size={16} />
                    <span>Current objective</span>
                    <strong>Win with controlled drawdown</strong>
                    <p>{packet.recommendedPriority.headline ?? receipt?.summary ?? "Run the advisor to generate a competition brief."}</p>
                  </article>
                  <article>
                    <span>Portfolio edge</span>
                    <strong>{real ? money(real.total_value) : "Needs import"}</strong>
                    <p>
                      {real?.positions.length
                        ? `${real.positions.length} holdings across ${Object.keys(real.stress.sector_weights).length} sectors.`
                        : "Import holdings to describe the portfolio edge."}
                    </p>
                  </article>
                  <article className="danger">
                    <span>Top risk</span>
                    <strong>{topRisk}</strong>
                    <p>{packet.portfolioRisk.issueCount ? `${packet.portfolioRisk.issueCount} active risk issues.` : "No hard breach forcing action."}</p>
                  </article>
                  <article>
                    <span>Best opportunity</span>
                    <strong>{topCandidate ? topCandidate.symbol : "None eligible"}</strong>
                    <p>{topCandidate?.explanation ?? "No staged add is eligible until gates clear."}</p>
                  </article>
                </div>

                <section className="competition-brief-section">
                  <div className="panel-label-row">
                    <span>What changed</span>
                    <Badge tone="watch">{shortDateTime(receipt?.timestamp ?? packet.generatedAt)}</Badge>
                  </div>
                  <p>{receipt?.summary ?? "No sealed receipt yet."}</p>
                </section>

                <section className="competition-brief-section">
                  <div className="panel-label-row">
                    <span>Action timeline</span>
                    <Badge tone={policy?.preset === "competition" ? "fail" : "live"}>{policy?.name ?? "Balanced"}</Badge>
                  </div>
                  <ActionTimeline dashboard={dashboard} />
                </section>

                <footer className="competition-brief-judge">
                  <span>Judge summary</span>
                  <p>
                    {first
                      ? `Deterministic first action: ${first.action} ${first.symbol}. ${first.explanation}`
                      : "No deterministic first action yet. Connect data and run the advisor."}
                  </p>
                </footer>
              </motion.section>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
