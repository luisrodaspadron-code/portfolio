import type { ActionItem, ConnectionProvider, Dashboard, Opportunity, Position, Recommendation } from "../types";
import { money, pct, textValue, titleCase } from "./format";

export type AppTab = "now" | "portfolio" | "risks" | "actions" | "connections";

export type TelemetryItem = {
  label: string;
  value: string;
  tone: "live" | "good" | "attention" | "danger" | "neutral";
  detail: string;
  actionLabel?: string;
  onAction?: () => void;
};

export type PrimaryDecision = {
  eyebrow: string;
  title: string;
  body: string;
  primaryLabel: string;
  primaryTab: AppTab;
  secondaryLabel: string;
  secondaryTab: AppTab;
  tone: "live" | "good" | "attention" | "danger";
  confidence: string;
};

export type ConstellationNode = {
  id: string;
  label: string;
  name: string;
  kind: "holding" | "idea";
  weight: number;
  risk: number;
  returnSignal: number;
  confidence: number;
  tone: "live" | "good" | "attention" | "danger" | "neutral";
  detail: string;
};

export type RadarMetric = {
  label: string;
  value: number;
  tone: "good" | "attention" | "danger" | "neutral";
  detail: string;
};

export type PipelineStep = {
  label: string;
  status: "complete" | "active" | "blocked" | "waiting";
  detail: string;
};

function screenCopy(value: string) {
  return value
    .replace("Open Risk to see sector and concentration details.", "Open Risks to review sector and concentration details.")
    .replace("Open Actions, then expand the audit trail to review sector and concentration details.", "Open Risks to review sector and concentration details.")
    .replace("Open Quant Lab and inspect the warning checks.", "Open Now and expand the audit trail to inspect the warning checks.")
    .replace("Open Quant Lab to compare strategy sleeves before making any brokerage decision.", "Open Now to review the market-universe trace before making any brokerage decision.");
}

export function getSetupStatus(dashboard: Dashboard) {
  const real = dashboard.real_portfolio;
  const portfolioConnected = Boolean(real && real.positions.length > 0);
  const cashOnly = Boolean(real && real.positions.length === 0 && real.cash > 0);
  const openai = dashboard.connections.providers.find((provider) => provider.provider === "openai");
  const aiConnected = Boolean(openai?.configured || dashboard.ai_status.configured);
  const aiReady = aiConnected && !["rate_limited", "disabled"].includes(dashboard.ai_status.state);
  const aiWorkflowIssue = dashboard.ai_status.state === "error";
  const aiRateLimited = dashboard.ai_status.state === "rate_limited";
  const marketKeyConnected = dashboard.connections.providers.some((provider) => provider.provider !== "openai" && provider.configured);
  const dataLive = dashboard.data_freshness.provider_mode === "live" && dashboard.data_freshness.preferred_price_source !== "sample";
  const latestProviderFailed = dashboard.data_freshness.latest_provider_refresh?.status === "failed";
  const missing = [
    portfolioConnected ? null : "Import holdings",
    aiConnected ? null : "Connect OpenAI",
    dataLive ? null : "Connect market data"
  ].filter(Boolean) as string[];

  return {
    portfolioConnected,
    cashOnly,
    aiConnected,
    aiReady,
    aiWorkflowIssue,
    aiRateLimited,
    dataLive,
    marketKeyConnected,
    latestProviderFailed,
    ready: portfolioConnected && aiConnected && dataLive,
    missing
  };
}

export function telemetryState(dashboard: Dashboard): TelemetryItem[] {
  const setup = getSetupStatus(dashboard);
  const riskBreaches = dashboard.decision_packet_status.risk_breaches;
  const portfolioValue = dashboard.real_portfolio?.total_value ?? 0;
  const latestProvider = dashboard.data_freshness.latest_provider_refresh;
  const latestPriceProviderFailed = latestProvider?.status === "failed" && latestProvider.provider === dashboard.data_freshness.preferred_price_source;
  const auxiliaryProviderWarning = latestProvider?.status === "failed" && !latestPriceProviderFailed;
  const dataMode = dashboard.data_freshness.provider_mode;
  const hasConfiguredPriceSource = dashboard.data_freshness.preferred_price_source !== "sample";
  const dataValue = setup.dataLive
    ? latestPriceProviderFailed
      ? "Stale"
      : dataMode === "partial"
        ? "Partial"
        : "Recent"
    : hasConfiguredPriceSource && ["recent", "stale", "partial"].includes(dataMode)
      ? titleCase(dataMode)
      : dashboard.data_freshness.price_bars
        ? "Sample"
        : "Needs data";
  const dataTone = setup.dataLive
    ? latestPriceProviderFailed || dataMode === "partial"
      ? "attention"
      : "good"
    : dashboard.data_freshness.price_bars || hasConfiguredPriceSource
      ? "attention"
      : "neutral";
  const largestPosition = dashboard.real_portfolio?.positions.reduce(
    (top, position) => (position.weight > (top?.weight ?? 0) ? position : top),
    dashboard.real_portfolio?.positions[0],
  );
  return [
    {
      label: "Portfolio",
      value: setup.portfolioConnected ? money(portfolioValue) : setup.cashOnly ? "Cash only" : "Missing",
      tone: setup.portfolioConnected ? "good" : "attention",
      detail: setup.portfolioConnected
        ? `${dashboard.real_portfolio?.positions.length ?? 0} holdings${largestPosition ? ` · largest ${largestPosition.symbol} ${pct(largestPosition.weight)}` : ""}`
        : setup.cashOnly
          ? "Only cash is loaded. Import positions for useful risk checks."
          : "No real holdings imported yet.",
      actionLabel: "Open portfolio",
    },
    {
      label: "Data",
      value: dataValue,
      tone: dataTone,
      detail: setup.dataLive || hasConfiguredPriceSource
        ? `${dashboard.data_freshness.live_price_symbols || dashboard.data_freshness.sample_price_symbols} priced symbols from ${titleCase(dashboard.data_freshness.preferred_price_source)}${auxiliaryProviderWarning ? `. ${titleCase(latestProvider?.provider)} needs attention.` : ""}`
        : "Using deterministic local sample data until a market provider is connected.",
      actionLabel: "Open source matrix",
    },
    {
      label: "Risk",
      value: setup.portfolioConnected ? (riskBreaches ? "Extreme" : "Clear") : "Needs holdings",
      tone: setup.portfolioConnected ? (riskBreaches ? "danger" : "good") : "attention",
      detail: setup.portfolioConnected
        ? riskBreaches
          ? `${riskBreaches} threshold${riskBreaches === 1 ? "" : "s"} breached · review before adding exposure.`
          : "No hard breach in current holdings."
        : "Risk checks need imported positions.",
      actionLabel: "Open risk brief",
    }
  ];
}

export function primaryDecision(dashboard: Dashboard): PrimaryDecision {
  const setup = getSetupStatus(dashboard);
  const packet = dashboard.advisor_packet;
  const firstAction = packet?.recommendedPriority?.firstAction;
  const receipt = packet?.decisionReceipt;
  const advisorDecision = dashboard.advisor_decision;
  const reviewAction = dashboard.advisor_review?.highest_priority_action ?? {};
  const fallbackAction = dashboard.action_items[0];

  if (firstAction && receipt) {
    const tone = firstAction.action === "TRIM" || firstAction.action === "BLOCKED_BY_RISK" ? "danger" : firstAction.action === "WAIT_FOR_DATA" ? "attention" : "live";
    return {
      eyebrow: "Portfolio decision",
      title: `${titleCase(firstAction.action.replace(/_/g, " "))} ${firstAction.symbol}`,
      body: packet.recommendedPriority.headline || receipt.summary || firstAction.explanation || "Review the decision receipt for sizing and gate details.",
      primaryLabel: dashboard.decision_packet_status.risk_breaches ? "Review risks" : "Review advisor actions",
      primaryTab: dashboard.decision_packet_status.risk_breaches ? "risks" : "actions",
      secondaryLabel: dashboard.decision_packet_status.risk_breaches ? "Review actions" : "Review connections",
      secondaryTab: dashboard.decision_packet_status.risk_breaches ? "actions" : "connections",
      tone,
      confidence: "Decision receipt"
    };
  }

  const decisionItem = advisorDecision?.holding_decisions.find((item) => item.decision === "Trim") ??
    advisorDecision?.opportunity_decisions.find((item) => item.decision === "Add" || item.decision === "Stagger Entry") ??
    advisorDecision?.holding_decisions.find((item) => item.decision === "Wait For Data") ??
    advisorDecision?.holding_decisions[0] ??
    advisorDecision?.opportunity_decisions[0];

  if (!setup.portfolioConnected) {
    return {
      eyebrow: "Signal required",
      title: "Import real holdings to activate the advisor",
      body: "Signal Prime needs your real positions, cash, and concentration before it can produce useful real-money actions.",
      primaryLabel: "Import real holdings",
      primaryTab: "portfolio",
      secondaryLabel: "Connect AI & data",
      secondaryTab: "connections",
      tone: "attention",
      confidence: "Portfolio missing"
    };
  }

  if (setup.aiRateLimited) {
    return {
      eyebrow: "AI rate limited",
      title: "Use quant-only actions while OpenAI cools down",
      body: "The OpenAI key is saved, but the provider is rate-limiting requests. Signal Prime will keep using deterministic quant gates and rules-based explanations until the model is available.",
      primaryLabel: "Use quant-only actions",
      primaryTab: "actions",
      secondaryLabel: "Review connection",
      secondaryTab: "connections",
      tone: "attention",
      confidence: "Quant-only"
    };
  }

  if (!setup.aiConnected || !setup.dataLive) {
    return {
      eyebrow: "Command setup",
      title: !setup.aiConnected ? "Connect AI for senior portfolio review" : "Connect live market data",
      body: !setup.aiConnected
        ? "Quant gates are working, but the model review is unavailable until OpenAI is connected and tested."
        : "Your holdings are loaded. Live data improves freshness, confidence, and source-aware recommendations.",
      primaryLabel: !setup.aiConnected ? "Connect AI & data" : "Connect market data",
      primaryTab: "connections",
      secondaryLabel: "Review actions",
      secondaryTab: "actions",
      tone: "attention",
      confidence: !setup.aiConnected ? "AI missing" : "Data limited"
    };
  }

  if (setup.aiWorkflowIssue) {
    const aiError = dashboard.ai_status.state === "error";
    return {
      eyebrow: "Quant fallback",
      title: aiError ? "AI review failed, but quant decisions are still available" : "Use quant-only decisions",
      body: dashboard.ai_status.user_message || "The OpenAI key is saved, but the latest model output could not be used. Signal Prime is falling back to deterministic risk-gated decisions.",
      primaryLabel: "Review quant actions",
      primaryTab: "actions",
      secondaryLabel: "See AI details",
      secondaryTab: "connections",
      tone: "attention",
      confidence: "Fallback active"
    };
  }

  return {
    eyebrow: advisorDecision ? "Portfolio decision" : dashboard.advisor_review ? "Advisor brief" : "Quant command",
    title: advisorDecision
      ? textValue(decisionItem?.plain_action, "Keep monitoring the portfolio")
      : dashboard.advisor_review
        ? textValue(reviewAction.title, textValue(reviewAction.action, fallbackAction?.title ?? "Advisor is monitoring"))
        : fallbackAction?.title ?? "Advisor is monitoring",
    body: screenCopy(
      advisorDecision
        ? `${advisorDecision.portfolio_verdict} ${decisionItem?.reason ?? ""}`.trim()
        : dashboard.advisor_review
          ? textValue(reviewAction.next_step, textValue(reviewAction.reason, dashboard.advisor_review.brief))
          : fallbackAction?.plain_action ?? "No urgent action right now. Signal Prime is monitoring risk, data freshness, and opportunity rank."
    ),
    primaryLabel: dashboard.decision_packet_status.risk_breaches ? "Review risks" : "Review advisor actions",
    primaryTab: dashboard.decision_packet_status.risk_breaches ? "risks" : "actions",
    secondaryLabel: dashboard.decision_packet_status.risk_breaches ? "Review actions" : "Review connections",
    secondaryTab: dashboard.decision_packet_status.risk_breaches ? "actions" : "connections",
    tone: fallbackAction?.priority === "high" ? "danger" : "live",
    confidence: advisorDecision?.status === "success" ? "Decision receipt" : advisorDecision ? "Quant receipt" : dashboard.advisor_review?.status === "success" ? "Quant receipt" : "Quant-gated"
  };
}

function nodeTone(status?: string, risk = 0): ConstellationNode["tone"] {
  if (status === "fail" || risk > 0.72) return "danger";
  if (status === "watch" || risk > 0.48) return "attention";
  if (status === "pass") return "live";
  return "good";
}

export function portfolioConstellationNodes(dashboard: Dashboard): ConstellationNode[] {
  const real = dashboard.real_portfolio;
  const holdings: ConstellationNode[] =
    real?.positions.slice(0, 18).map((position: Position) => ({
      id: `holding-${position.symbol}`,
      label: position.symbol,
      name: position.name,
      kind: "holding",
      weight: Math.max(0.01, position.weight),
      risk: Math.min(1, Math.abs(position.gain_loss_pct) + position.weight),
      returnSignal: position.gain_loss_pct,
      confidence: 0.78,
      tone: nodeTone(undefined, Math.abs(position.gain_loss_pct) + position.weight),
      detail: `${pct(position.weight)} weight · ${position.sector} · ${money(position.market_value)}`
    })) ?? [];

  const ideas = dashboard.recent_recommendations.slice(0, holdings.length ? 8 : 18).map((item: Recommendation) => ({
    id: `idea-${item.symbol}-${item.id}`,
    label: item.symbol,
    name: item.name ?? item.symbol,
    kind: "idea" as const,
    weight: Math.max(0.012, item.target_weight || 0.025),
    risk: Math.max(0.02, Math.min(1, item.risk_score)),
    returnSignal: item.expected_return,
    confidence: item.confidence,
    tone: nodeTone(item.status, item.risk_score),
    detail: `${item.action} · target ${pct(item.target_weight)} · source ${item.source_data_age_days}d`
  }));

  return [...holdings, ...ideas];
}

export function riskRadarMetrics(dashboard: Dashboard): RadarMetric[] {
  const real = dashboard.real_portfolio;
  const concentration = Math.min(1, real?.stress.concentration ?? 0);
  const sectorMax = Math.min(1, Math.max(0, ...Object.values(real?.stress.sector_weights ?? {})));
  const avgLiquidity =
    dashboard.opportunities.length > 0
      ? dashboard.opportunities.slice(0, 20).reduce((sum: number, item: Opportunity) => sum + item.liquidity_score / 100, 0) /
        Math.min(20, dashboard.opportunities.length)
      : 0.45;
  const freshnessRisk = dashboard.data_freshness.provider_mode === "live" ? 0.18 : dashboard.decision_packet_status.sample_only ? 0.82 : 0.48;
  const macroRisk = Math.max(0.05, Math.min(1, 0.55 - dashboard.macro_regime.score / 2));
  const breachRisk = Math.min(1, dashboard.decision_packet_status.risk_breaches / 4);

  return [
    {
      label: "Concentration",
      value: concentration,
      tone: concentration > 0.3 ? "danger" : concentration > 0.18 ? "attention" : "good",
      detail: real ? `Largest concentration score ${concentration.toFixed(2)}` : "Needs holdings"
    },
    {
      label: "Theme load",
      value: sectorMax,
      tone: sectorMax > 0.3 ? "danger" : sectorMax > 0.2 ? "attention" : "good",
      detail: sectorMax ? `Largest sector ${pct(sectorMax)}` : "No sector exposure"
    },
    {
      label: "Liquidity",
      value: 1 - avgLiquidity,
      tone: avgLiquidity < 0.45 ? "danger" : avgLiquidity < 0.65 ? "attention" : "good",
      detail: `Top universe liquidity ${(avgLiquidity * 100).toFixed(0)} / 100`
    },
    {
      label: "Freshness",
      value: freshnessRisk,
      tone: freshnessRisk > 0.65 ? "danger" : freshnessRisk > 0.35 ? "attention" : "good",
      detail: dashboard.data_freshness.provider_mode === "live" ? "Live source preferred" : "Data needs upgrade"
    },
    {
      label: "Macro drag",
      value: macroRisk,
      tone: macroRisk > 0.65 ? "danger" : macroRisk > 0.35 ? "attention" : "good",
      detail: titleCase(dashboard.macro_regime.label)
    },
    {
      label: "Rule breach",
      value: breachRisk,
      tone: breachRisk > 0.35 ? "danger" : breachRisk > 0 ? "attention" : "good",
      detail: breachRisk ? `${dashboard.decision_packet_status.risk_breaches} active breaches` : "No hard breach"
    }
  ];
}

export function advisorPipelineSteps(dashboard: Dashboard): PipelineStep[] {
  const setup = getSetupStatus(dashboard);
  const aiFailed = dashboard.ai_status.state === "error";
  const aiRateLimited = dashboard.ai_status.state === "rate_limited";
  return [
    {
      label: "Data refresh",
      status: dashboard.data_freshness.latest_price_date ? "complete" : "waiting",
      detail: `${dashboard.data_freshness.price_bars.toLocaleString()} price bars`
    },
    {
      label: "Feature engine",
      status: dashboard.quant_diagnostics.coverage.scored_instruments ? "complete" : "waiting",
      detail: `${dashboard.quant_diagnostics.coverage.scored_instruments} instruments scored`
    },
    {
      label: "Risk gates",
      status: dashboard.decision_packet_status.risk_breaches ? "active" : "complete",
      detail: dashboard.decision_packet_status.risk_breaches ? "Breaches require review" : "Hard gates clear"
    },
    {
      label: "Backtest evidence",
      status: dashboard.recent_backtests.length ? "complete" : "waiting",
      detail: dashboard.recent_backtests[0] ? `Latest run #${dashboard.recent_backtests[0].id}` : "No recent run"
    },
    {
      label: "AI review",
      status: aiFailed ? "blocked" : aiRateLimited ? "active" : setup.aiReady ? "complete" : "waiting",
      detail: aiFailed
        ? "Connection failed"
        : aiRateLimited
          ? "Rate limited; quant fallback active"
          : setup.aiReady
            ? dashboard.ai_status.profile_summary
            : "Needs OpenAI key"
    },
    {
      label: "Action queue",
      status: dashboard.action_items.length ? "active" : "waiting",
      detail: `${dashboard.action_items.length} next actions`
    }
  ];
}

export function getConnectionGroups(providers: ConnectionProvider[]) {
  return [
    {
      label: "Required",
      description: "Core AI review.",
      providers: providers.filter((provider) => provider.provider === "openai")
    },
    {
      label: "Recommended",
      description: "Prices, macro, and fundamentals.",
      providers: providers.filter((provider) => ["alpaca", "fred", "sec_edgar"].includes(provider.provider))
    },
    {
      label: "Optional",
      description: "Broader paid coverage.",
      providers: providers.filter((provider) => provider.provider === "alpha_vantage")
    }
  ].filter((group) => group.providers.length > 0);
}

export function recommendationLane(item: Recommendation) {
  const action = item.action.toLowerCase();
  if (item.status === "fail" || action.includes("avoid") || action.includes("trim")) return "Blocked";
  if (item.status === "watch" || action.includes("watch")) return "Watch";
  return "Do";
}

export function actionPriorityTone(item: ActionItem) {
  if (item.priority === "high") return "danger";
  if (item.priority === "medium") return "attention";
  return "neutral";
}
