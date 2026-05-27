import * as Tooltip from "@radix-ui/react-tooltip";
import { HelpCircle } from "lucide-react";
import type { ReactNode } from "react";

type Props = {
  term: ReactNode;
  children: ReactNode;
  hideIcon?: boolean;
};

/**
 * Inline term that reveals a plain-language explanation on hover/focus.
 *
 * Use to demystify Signal-specific vocabulary (cap distance, hard buy-block,
 * source freshness, drawdown, factor, etc.) without dumbing the surface down.
 */
export function ExplainableTerm({ term, children, hideIcon = false }: Props) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button type="button" className="explainable-term" aria-label="What does this mean?">
          <span>{term}</span>
          {!hideIcon && <HelpCircle size={12} aria-hidden="true" />}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="signal-tooltip explainable-tooltip" sideOffset={8} collisionPadding={12}>
          {children}
          <Tooltip.Arrow className="signal-tooltip-arrow" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

/**
 * Pre-baked glossary entries so the same term reads consistently across the
 * app. Add new entries here when you reuse a term in more than one surface.
 */
export const GLOSSARY: Record<string, { title: string; body: string }> = {
  cap_distance: {
    title: "Cap distance",
    body: "How far a position is above or below its single-stock policy cap. The deterministic engine computes this from current weight and the selected policy ladder.",
  },
  hard_buy_block: {
    title: "Hard buy block",
    body: "When a position passes this threshold the app blocks recommendations that would add more exposure. Trims and risk-reducing trades stay eligible.",
  },
  urgent_review: {
    title: "Urgent review",
    body: "An above-policy state that requires a manual review before any new buys. The deterministic engine routes this to a Trim recommendation.",
  },
  extreme: {
    title: "Extreme concentration",
    body: "The position is so far above policy that further exposure is not advisable even if other gates pass. The app surfaces this as a top action.",
  },
  source_freshness: {
    title: "Source freshness",
    body: "How fresh the underlying data is (live / recent / stale / partial / missing). Caps and risk gates only fire when the data is recent enough to trust.",
  },
  drawdown: {
    title: "Drawdown",
    body: "The deepest peak-to-trough loss measured over the backtest window. The advisor uses this to size positions and gate risky candidates.",
  },
  factor_crowding: {
    title: "Factor crowding",
    body: "How concentrated the portfolio is across one factor (e.g. momentum, growth). A high score suggests adding diversified exposure rather than more of the same.",
  },
  cvar: {
    title: "CVaR (expected shortfall)",
    body: "Average loss in the worst 5% of historical days. Useful for sizing risk-reducing capital and stress-testing the portfolio.",
  },
  compliance_mode: {
    title: "Compliance mode",
    body: "Strict rounds up to cross the policy threshold in a single trade. Reduce-only rounds down (may stay over). Tax-aware leaves the call to a human review.",
  },
};

/**
 * Shorthand: <Glossary k="hard_buy_block">Hard buy-block</Glossary>
 */
export function Glossary({ k, children }: { k: keyof typeof GLOSSARY; children: ReactNode }) {
  const entry = GLOSSARY[k];
  if (!entry) return <>{children}</>;
  return (
    <ExplainableTerm term={children}>
      <strong>{entry.title}</strong>
      <p>{entry.body}</p>
    </ExplainableTerm>
  );
}
