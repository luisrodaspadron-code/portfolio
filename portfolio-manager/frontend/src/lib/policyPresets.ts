import type { SelectedPolicy } from "../types";

export type PolicyPresetId = "conservative" | "balanced" | "aggressive" | "competition";

export type PolicyPresetPreview = {
  id: PolicyPresetId;
  label: string;
  description: string;
  warning: string;
  singleStock: SelectedPolicy["singleStock"];
  sectorCap: number;
  cryptoEnabled: boolean;
};

export const POLICY_PRESET_PREVIEWS: PolicyPresetPreview[] = [
  {
    id: "conservative",
    label: "Conservative",
    description: "Tight single-name caps, defensive sector caps, crypto effectively off.",
    warning: "Lower risk budget. Smaller adds and earlier warnings.",
    singleStock: {
      target: 0.03,
      warning: 0.05,
      hardBuyBlock: 0.06,
      urgentReview: 0.1,
      extreme: 0.18,
    },
    sectorCap: 0.22,
    cryptoEnabled: false,
  },
  {
    id: "balanced",
    label: "Balanced",
    description: "Default ladder: 5% target, 8% warning, 10% hard buy-block, 15% urgent, 25% extreme.",
    warning: "Balanced risk budget for most portfolios.",
    singleStock: {
      target: 0.05,
      warning: 0.08,
      hardBuyBlock: 0.1,
      urgentReview: 0.15,
      extreme: 0.25,
    },
    sectorCap: 0.3,
    cryptoEnabled: false,
  },
  {
    id: "aggressive",
    label: "Aggressive",
    description: "Larger conviction sizing with relaxed but still enforced caps.",
    warning: "Higher single-name budget. Drawdown controls remain active.",
    singleStock: {
      target: 0.08,
      warning: 0.12,
      hardBuyBlock: 0.15,
      urgentReview: 0.2,
      extreme: 0.3,
    },
    sectorCap: 0.4,
    cryptoEnabled: true,
  },
  {
    id: "competition",
    label: "Competition",
    description: "Highest conviction sizing for competition-grade portfolios.",
    warning: "Higher risk budget. Manual deep review recommended. Drawdown controls remain active.",
    singleStock: {
      target: 0.1,
      warning: 0.15,
      hardBuyBlock: 0.18,
      urgentReview: 0.25,
      extreme: 0.35,
    },
    sectorCap: 0.45,
    cryptoEnabled: true,
  },
];

export const PRESET_TO_SETTINGS: Record<
  PolicyPresetId,
  { objective: string; risk: string; diversification: string }
> = {
  conservative: {
    objective: "capital_preservation",
    risk: "defensive",
    diversification: "highly_diversified",
  },
  balanced: {
    objective: "balanced_growth",
    risk: "moderate",
    diversification: "broad_opportunistic",
  },
  aggressive: {
    objective: "balanced_growth",
    risk: "aggressive_managed",
    diversification: "focused_best_ideas",
  },
  competition: {
    objective: "competition_growth",
    risk: "aggressive_managed",
    diversification: "focused_best_ideas",
  },
};
