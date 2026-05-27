export type ProviderStatus = {
  name: string;
  configured: boolean;
  capabilities: string[];
  note: string;
  priority: number;
  state: string;
  last_refresh: string | null;
  records: number;
  error: string;
};

export type Position = {
  symbol: string;
  name: string;
  asset_class: string;
  sector: string;
  theme?: string;
  metadata_source?: string;
  metadata_confidence?: number;
  quantity: number;
  avg_cost: number;
  valuation_status: "priced" | "proxy" | "missing_price" | string;
  valuation_note: string;
  latest_price: number;
  market_value: number;
  gain_loss: number;
  gain_loss_pct: number;
  weight: number;
};

export type HoldingsImportResult = {
  status: "success" | "partial" | string;
  imported: Array<{ symbol: string; quantity: number; avg_cost: number }>;
  portfolio: Portfolio;
  detected_columns: Record<string, string>;
  warnings: string[];
  rejected_rows: Array<{ row: number; symbol?: string; reason: string }>;
};

export type Portfolio = {
  id: number;
  name: string;
  mode: string;
  base_currency: string;
  cash: number;
  market_value: number;
  total_value: number;
  positions: Position[];
  stress: {
    level: string;
    warnings: string[];
    concentration: number;
    sector_weights: Record<string, number>;
    unknown_sector_weight?: number;
  };
};

export type Opportunity = {
  symbol: string;
  name: string;
  asset_class: string;
  sector: string;
  latest_price: number;
  one_year_return: number;
  momentum_63d: number;
  momentum_126d: number;
  volatility: number;
  max_drawdown: number;
  trend_persistence: number;
  quality_score: number;
  score: number;
  expected_return: number;
  confidence: number;
  risk_score: number;
  liquidity_score: number;
};

export type Recommendation = {
  id: number;
  symbol: string;
  name?: string;
  action: string;
  target_weight: number;
  confidence: number;
  expected_return: number;
  risk_score: number;
  status: string;
  reason: string;
  source_data_age_days: number;
  portfolio_impact: Record<string, unknown>;
  risk_flags: string[];
  data_confidence: "fresh" | "stale" | "sample_only" | string;
  ai_review: null | {
    symbol: string;
    action: string;
    status: string;
    quant_status: string;
    reason: string;
    source: string;
  };
  created_at: string;
};

export type ResearchMemo = {
  id: number;
  recommendation_id: number | null;
  symbol: string;
  name: string;
  title: string;
  thesis: string;
  evidence: string;
  risks: string;
  counterargument: string;
  change_mind: string;
  created_at: string;
  generation_method: string;
  ai_provider: string;
  ai_model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type BacktestRun = {
  id: number;
  params: Record<string, unknown>;
  metrics: Record<string, number>;
  equity_curve: Array<{ date: string; value: number }>;
  created_at?: string;
};

export type QuantDiagnostics = {
  status: string;
  freshness: {
    latest_price_date: string;
    price_bars: number;
    latest_macro_date: string;
    macro_points: number;
  };
  coverage: {
    enabled_instruments: number;
    price_history_ready: number;
    fundamental_symbols: number;
    macro_series: number;
    scored_instruments: number;
    sectors: number;
    asset_classes: number;
  };
  recommendations: {
    total: number;
    pass: number;
    watch: number;
    fail: number;
  };
  top_score: number;
  checks: Array<{
    name: string;
    status: string;
    detail: string;
  }>;
};

export type AdvisorStatus = {
  enabled: boolean;
  cadence: string;
  last_run: null | {
    id: number;
    trigger: string;
    status: string;
    started_at: string;
    finished_at: string;
    error: string;
  };
  summary: {
    steps?: string[];
    step_receipts?: AdvisorRunStep[];
    recommendations?: number;
    buy_ideas?: number;
    watch_ideas?: number;
    memos?: number;
    diagnostics_status?: string;
    real_portfolio_loaded?: boolean;
    real_portfolio_value?: number;
    real_positions?: number;
    strategies_reviewed?: number;
    top_strategy?: string | null;
    backtest?: null | {
      id: number;
      total_return: number;
      max_drawdown: number;
      sharpe: number;
    };
  };
  message: string;
};

export type AdvisorRunResult = {
  id: number;
  run_id?: number;
  status: "success" | "failed" | string;
  started_at: string;
  finished_at: string;
  summary: AdvisorStatus["summary"] & {
    advisor_decision_status?: string;
    advisor_verdict?: string;
    fallback_reason?: string;
    ai_tokens?: number;
  };
  error?: string;
};

export type AdvisorRunStart = {
  run_id: number;
  status: "running" | string;
  started_at: string;
};

export type AdvisorRunStatus = {
  run_id: number;
  status: "running" | "success" | "failed" | string;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  current_step: AdvisorRunStep | null;
  completed_steps: AdvisorRunStep[];
  steps: AdvisorRunStep[];
  events: AdvisorRunEvent[];
  records_processed: number;
  fallback_reason: string;
  model: string;
  reasoning: string;
  token_usage: number;
  universe_size: number;
  priced_symbols: number;
  sec_used: boolean;
  fred_used: boolean;
  decision_hash: string;
  summary: AdvisorStatus["summary"] & {
    advisor_decision_status?: string;
    advisor_verdict?: string;
    fallback_reason?: string;
    ai_tokens?: number;
    ai_model?: string;
    ai_reasoning?: string;
    decision_hash?: string;
  };
  error: string;
};

export type AdvisorRunEvent = {
  runId: string;
  eventId?: number;
  type?: "step" | "run" | string;
  timestamp: string;
  phase:
    | "universe"
    | "prices"
    | "holdings"
    | "fundamentals"
    | "macro"
    | "factors"
    | "risk"
    | "sizing"
    | "candidates"
    | "llm"
    | "receipt"
    | "complete"
    | "lifecycle"
    | "error"
    | string;
  status: "queued" | "running" | "success" | "warning" | "error" | "failed" | "cancelled" | string;
  title: string;
  detail: string;
  metrics?: Record<string, string | number>;
  source?: string;
};

export type AdvisorRunStep = {
  step: string;
  status: "updated" | "reused" | "skipped" | "warning" | "failed" | string;
  records: number;
  started_at: string;
  finished_at: string;
  message: string;
  technical_detail: string;
};

export type ActionItem = {
  priority: "high" | "medium" | "low" | string;
  type: string;
  symbol: string | null;
  title: string;
  plain_action: string;
  why: string;
  evidence: string[];
  risk_check: string;
  next_step: string;
  confidence: number | null;
};

export type MarketScope = {
  enabled_instruments: number;
  asset_classes: Record<string, number>;
  sectors: Record<string, number>;
  strategy_count: number;
  strategy_names: string[];
};

export type AdvisorTrace = {
  packet_hash: string;
  created_at: string;
  ai_activity: "not_connected" | "ready" | "reviewed" | "rate_limited" | "error" | "idle" | string;
  ai: {
    model: string;
    model_route?: {
      advisor_decision: string;
      copilot: string;
      connection_test: string;
      reasoning_effort: string;
      review_token_cap: number;
      decision_token_cap: number;
    };
    review_status: string;
    latest_decision?: null | {
      id: number;
      packet_hash: string;
      status: string;
      model: string;
      total_tokens: number;
      created_at: string;
    };
    latest_eval?: null | {
      id: number;
      status: string;
      model: string;
      total_tokens: number;
      created_at: string;
    };
    decision_boundary: string;
    last_run: null | {
      purpose: string;
      status: string;
      finished_at: string;
      total_tokens: number;
      error: string;
    };
  };
  holdings_analyzed: {
    count: number;
    total_value: number;
    top_holding: Position | null;
    symbols: string[];
  };
  top_risks: Array<{ title: string; severity: string; what_to_do: string }>;
  risk_bounds: Record<string, number | string | boolean>;
  quant_tools: Array<{ name: string; label: string; description: string; status: string }>;
  market_universe: MarketScope & {
    coverage?: UniverseStatus;
    allowed_categories: string[];
    blocked_or_limited_categories: string[];
    top_opportunities: Array<{
      symbol: string;
      name: string;
      asset_class: string;
      sector: string;
      score: number;
      confidence: number;
      risk_score: number;
    }>;
  };
  provider_freshness: {
    mode: string;
    preferred_source: string;
    price_bars: number;
    live_price_symbols: number;
    latest_provider_refresh: null | Record<string, string | number>;
    providers: Array<{
      provider: string;
      label: string;
      state: string;
      configured: boolean;
      used_in_review: boolean;
      records: number;
      last_refresh: string | null;
      last_test: ConnectionTestStatus | null;
    }>;
  };
  sec_edgar: {
    configured: boolean;
    state: string;
    purpose: string;
    covered_symbols: string[];
    facts_count: number;
    latest_refresh: string;
    last_test: ConnectionTestStatus | null;
    message: string;
  };
};

export type UniverseStatus = {
  total_assets: number;
  included_assets: number;
  tradable_assets: number;
  priced_symbols: number;
  sec_mapped_symbols: number;
  ipo_assets: number;
  low_liquidity_or_unconfirmed: number;
  asset_classes: Record<string, number>;
  sources: Record<string, number>;
  rate_limits: Record<string, Record<string, string | number>>;
  last_refresh: string | null;
  scope_label: string;
};

export type SourceMatrixEntry = {
  provider?: string;
  fallback?: string;
  recordCount?: number;
  symbolCount?: number;
  latestTimestamp?: string | null;
  freshness?: string;
  coverage?: string;
  confidence?: number;
  configured?: boolean;
  usedInRun?: boolean;
  usedInLatestRun?: boolean;
  warnings?: string[];
  [key: string]: unknown;
};

export type SourceMatrix = {
  generatedAt: string;
  policyVersion: string;
  selectedPreset: string;
  matrix: Record<string, SourceMatrixEntry>;
  summary: Record<string, number | string | boolean | Record<string, boolean>>;
};

export type TrimPlan = {
  mode: string;
  complianceMode?: "strict_below_threshold" | "reduce_only" | "tax_aware_review" | string;
  currentValue: number;
  targetValue: number;
  estimatedSellValue: number;
  estimatedExecutedSellValue: number;
  sharesToSellExact: number;
  sharesToSell: number;
  sharesToSellWhole: number;
  sharesToSellWholeCompliant?: number;
  sharesToSellWholeReduceOnly?: number;
  sharesToSellFractionalCompliant?: number;
  estimatedPostWeight: number;
  estimatedPostWeightCompliant?: number;
  estimatedPostWeightReduceOnly?: number;
  wouldRemainAboveThresholdIfRoundedDown?: boolean;
  policyThreshold?: number;
  priceUsed: number;
  priceTimestamp: string;
  executionGuidance?: {
    advisoryOnly: boolean;
    brokerActionLabel: string;
    preferredOrderType: string;
    timeInForce: string;
    session: string;
    recommendedStyle: string;
    sliceCount: number;
    limitPriceReference: number;
    suggestedLimitPrice: number;
    stopReviewBelow: number;
    priceRefreshRequired: boolean;
    primaryQuantityBasis?: "fractional" | "whole_share_compliant";
    slices: Array<{
      sliceNumber: number;
      shares: number;
      estimatedValue: number;
      suggestedLimitPrice: number;
      timeInForce: string;
      condition: string;
    }>;
    wholeShareSlices?: Array<{
      sliceNumber: number;
      shares: number;
      estimatedValue: number;
      suggestedLimitPrice: number;
      timeInForce: string;
      condition: string;
    }>;
    fractionalSlices?: Array<{
      sliceNumber: number;
      shares: number;
      estimatedValue: number;
      suggestedLimitPrice: number;
      timeInForce: string;
      condition: string;
    }>;
    singleOrderAlternative?: {
      shares: number;
      estimatedValue: number;
      suggestedLimitPrice: number;
      timeInForce: string;
    };
    allAtOnceAcceptable?: boolean;
    stagingRationale?: string;
    instructions: string[];
    invalidation: string[];
  };
  advisoryOnly: boolean;
  taxWarning?: string;
};

export type AddPlan = {
  targetWeight: number;
  initialWeight: number;
  trancheCount: number;
  trancheSchedule: Array<Record<string, string | number>>;
  sectorImpact: number;
  riskBudgetImpact: number;
  blockers: string[];
  advisoryOnly: boolean;
};

export type AdvisorDecisionItem = {
  id: number;
  decision_run_id: number;
  symbol: string;
  item_type: "holding" | "opportunity" | string;
  decision: "Hold" | "Add" | "Trim" | "Rotate" | "Stagger Entry" | "Avoid" | "Wait For Data" | string;
  plain_action: string;
  reason: string;
  target_weight: number;
  current_weight: number;
  confidence_label: string;
  confidence_score: number;
  eligibility: string;
  risk_check: string;
  quant_evidence: string[];
  ai_commentary: string;
  source_freshness: string;
  reason_code?: string;
  detail_payload?: {
    advisoryOnly?: boolean;
    reasonCode?: string;
    capDistance?: {
      current_weight: number;
      limit: number;
      over_by: number;
      breached: boolean;
    };
    dataQuality?: {
      provider: string;
      sourceTimestamp: string;
      receivedAt: string;
      ageSeconds: number;
      freshness: string;
      coverage: string;
      confidence: number;
      warnings: string[];
    };
    trimPlan?: TrimPlan | null;
    addPlan?: AddPlan | null;
    blockers?: string[];
  };
  created_at: string;
};

export type AdvisorDecision = {
  id: number;
  packet_hash: string;
  model: string;
  status: string;
  portfolio_verdict: string;
  holding_decisions: AdvisorDecisionItem[];
  opportunity_decisions: AdvisorDecisionItem[];
  execution_plan: string[];
  staggering_guidance: string[];
  entry_conditions: string[];
  risks: string[];
  data_used: string[];
  missing_data: string[];
  what_would_change_my_mind: string[];
  fallback_reason: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  response_id: string;
  created_at: string;
};

export type AdvisorEval = {
  id: number;
  status: string;
  model: string;
  decision_run_id: number | null;
  rubric: Record<string, boolean>;
  questions: Array<Record<string, unknown>>;
  total_tokens: number;
  error: string;
  created_at: string;
};

export type PortfolioTrend = {
  granularity: string;
  intraday_available: boolean;
  points: Array<{ date: string; value: number }>;
  day_change: number;
  day_change_pct: number;
  week_change: number;
  week_change_pct: number;
  month_change: number;
  month_change_pct: number;
  latest_change_label: string;
  comparison_date: string | null;
  as_of_date: string | null;
  source_note: string;
  position_changes: Array<{
    symbol: string;
    day_change: number;
    day_change_pct: number;
    latest_price: number;
    source: string;
  }>;
};

export type SchedulerStatus = {
  enabled: boolean;
  cadence: string;
  last_run_at: string | null;
  next_run_at: string | null;
  interval_seconds: number;
  last_result: null | {
    status?: string;
    summary?: Record<string, unknown>;
    error?: string;
  };
};

export type StrategyReview = {
  name: string;
  category: string;
  goal: string;
  stance: string;
  score: number;
  confidence: number;
  risk_score: number;
  momentum: number;
  candidates: Array<{
    symbol: string;
    name: string;
    score: number;
    confidence: number;
    risk_score: number;
  }>;
};

export type PolicyChoice = {
  label: string;
  description: string;
};

export type PolicyStatus = {
  objective: string;
  risk: string;
  diversification: string;
  summary: {
    objective: PolicyChoice;
    risk: PolicyChoice;
    diversification: PolicyChoice;
  };
  options: {
    objectives: Record<string, PolicyChoice>;
    risks: Record<string, PolicyChoice>;
    diversification: Record<string, PolicyChoice>;
  };
  guardrails: Record<string, number>;
  selectedPolicy?: SelectedPolicy;
  policyVersion?: string;
  autopilotEnabled?: boolean;
  realMoneyTradingEnabled?: boolean;
};

export type AiStatus = {
  provider: string;
  configured: boolean;
  state: string;
  model: string;
  max_output_tokens: number;
  settings: {
    model: string;
    reasoning_effort: string;
    memo_style: string;
    custom_instructions: string;
    max_output_tokens: number;
    review_max_output_tokens?: number;
    model_route?: string;
  };
  model_router: {
    mode: string;
    fast: AiModelRoute;
    specialist: AiModelRoute;
    leadPM: AiModelRoute;
    deepCompetition: AiModelRoute;
  };
  profile_summary: string;
  message: string;
  user_message?: string;
  technical_error?: string;
  last_run: null | {
    provider: string;
    model: string;
    purpose: string;
    status: string;
    finished_at: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    error: string;
  };
  usage_totals: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
};

export type AiModelRoute = {
  role: string;
  provider: string;
  model: string;
  reasoningEffort: "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | string;
  maxOutputTokens: number;
  timeoutMs?: number;
  stream?: boolean;
  purpose?: string;
  requiresManualRun?: boolean;
  promptVersion?: string;
};

export type SelectedSingleStockPolicy = {
  target: number;
  warning: number;
  hardBuyBlock: number;
  urgentReview: number;
  extreme: number;
};

export type SelectedSectorPolicy = {
  warning: number;
  hardCap: number;
  useBenchmarkRelativeCap: boolean;
  maxActiveOverweight: number;
};

export type SelectedBroadEtfPolicy = {
  exemptFromSingleStockCap: boolean;
  useLookThroughWhenAvailable: boolean;
  maxSingleBroadEtf: number;
};

export type SelectedThematicEtfPolicy = {
  maxSingleThematicEtf: number;
  requireLookThroughOrThemeRiskLabel: boolean;
};

export type SelectedNewStockPolicy = {
  initialMax: number;
  targetMax: number;
  blockIfWorsensExistingBreach: boolean;
  allowIfRiskReducingWithNewCash: boolean;
};

export type SelectedCryptoPolicy = {
  enabledByDefault: boolean;
  maxTotal: number;
  maxSingle: number;
  requireExplicitUserEnablement: boolean;
  require24X7Freshness: boolean;
  requireCustodyWarning: boolean;
};

export type SelectedDataQualityPolicy = {
  equityLiveSeconds: number;
  equityRecentSeconds: number;
  cryptoLiveSeconds: number;
  cryptoRecentSeconds: number;
  minHistoryDaysRestricted: number;
  minHistoryDaysFull: number;
  minHistoryDaysWatchOnly: number;
};

export type SelectedLiquidityPolicy = {
  minDollarVolumeDefault: number;
  maxTradePercentOfAdv: number;
};

export type SelectedRemediationPolicy = {
  allowRiskReducingTradesDuringBreach: boolean;
  blockRiskIncreasingTradesDuringBreach: boolean;
  requireTaxWarningForTaxableAccounts: boolean;
  defaultTranches?: number;
  defaultTrancheCadenceDays?: number;
};

export type SelectedPolicy = {
  id: string;
  name: string;
  preset: "conservative" | "balanced" | "aggressive" | "competition" | "custom" | string;
  advisoryOnly: boolean;
  version?: string;
  singleStock: SelectedSingleStockPolicy;
  sector: SelectedSectorPolicy;
  broadEtf: SelectedBroadEtfPolicy;
  thematicEtf: SelectedThematicEtfPolicy;
  singleNewStockAdd: SelectedNewStockPolicy;
  crypto: SelectedCryptoPolicy;
  dataQuality: SelectedDataQualityPolicy;
  liquidity: SelectedLiquidityPolicy;
  remediation: SelectedRemediationPolicy;
};

export type ConnectionField = {
  key: string;
  label: string;
  secret: boolean;
  placeholder: string;
  configured: boolean;
  source: string;
  masked_value: string;
};

export type ConnectionTestStatus = {
  status: string;
  tested_at: string;
  records: number;
  message: string;
  error: string;
};

export type ConnectionProvider = {
  provider: string;
  label: string;
  description: string;
  configured: boolean;
  state: string;
  fields: ConnectionField[];
  capabilities: string[];
  note: string;
  last_refresh: string | null;
  last_test: ConnectionTestStatus | null;
  records: number;
  error: string;
  connection_state?: string;
  latest_use_state?: string;
  user_message?: string;
  last_successful_use?: string | null;
  next_fix?: string;
};

export type ConnectionsStatus = {
  summary: {
    configured: number;
    total: number;
    missing: number;
  };
  providers: ConnectionProvider[];
};

export type AdvisorReview = {
  id: number;
  packet_hash: string;
  model: string;
  status: string;
  brief: string;
  highest_priority_action: Record<string, unknown>;
  approved_actions: Array<Record<string, unknown>>;
  concerns: Array<string | Record<string, unknown>>;
  rejected_or_blocked_ideas: Array<Record<string, unknown>>;
  missing_data: Array<string | Record<string, unknown>>;
  what_would_change_my_mind: Array<string | Record<string, unknown>>;
  fallback_reason: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  response_id: string;
  created_at: string;
};

export type DecisionPacketStatus = {
  packet_hash: string;
  created_at: string;
  tool_count: number;
  data_confidence: string;
  sample_only: boolean;
  max_source_age_days: number;
  recommendations: number;
  risk_breaches: number;
};

export type AdvisorPacketAction = {
  symbol: string;
  name?: string;
  assetClass?: string;
  sector?: string;
  action: "TRIM" | "ADD" | "STAGGER_ENTRY" | "HOLD" | "WAIT_FOR_DATA" | "BLOCKED_BY_RISK" | "REVIEW_MANUALLY" | string;
  reasonCode: string;
  explanation: string;
  currentValue?: number;
  currentWeight?: number;
  targetWeight: number;
  targetValue?: number;
  livePrice?: number | null;
  priceTimestamp?: string | null;
  dataQuality: {
    provider: string;
    sourceTimestamp: string;
    receivedAt: string;
    ageSeconds: number;
    freshness: string;
    coverage: string;
    confidence: number;
    warnings: string[];
  };
  riskBreaches: Array<{
    id: string;
    severity: string;
    rule: string;
    observed: number;
    limit: number;
    message: string;
    blocksAdds: boolean;
  }>;
  trimPlan?: TrimPlan | null;
  addPlan?: AddPlan | null;
  confidence: number;
  confidenceDrivers: string[];
  blockers: string[];
};

export type AdvisorPacket = {
  packetVersion: string;
  runId: string;
  promptVersion: string;
  policyVersion: string;
  deterministicEngineVersion?: string;
  generatedAt: string;
  packetHash: string;
  portfolioValue: number;
  cashValue: number;
  dataSources: Array<Record<string, string | number | boolean>>;
  positions: AdvisorPacketAction[];
  candidates: AdvisorPacketAction[];
  portfolioRisk: {
    severity: string;
    issueCount: number;
    concentrationScore: number;
    sectorBreaches: AdvisorPacketAction["riskBreaches"];
    singleNameBreaches: AdvisorPacketAction["riskBreaches"];
    liquidityWarnings: AdvisorPacketAction["riskBreaches"];
    staleDataWarnings: AdvisorPacketAction["riskBreaches"];
  };
  recommendedPriority: {
    headline: string;
    firstAction: AdvisorPacketAction | null;
    doNext: string[];
    blockedActions: string[];
  };
  workflowAudit?: {
    status: string;
    gapCount: number;
    firstActionReadyForBrokerReview: boolean;
    requiredBeforeBroker: string[];
    gaps: Array<{
      area: string;
      severity: string;
      finding: string;
      action: string;
      clearsWhen: string;
    }>;
  };
  decisionReceipt: {
    title: string;
    runId?: string;
    timestamp?: string;
    advisoryOnly: boolean;
    noOrderPlaced: boolean;
    portfolioValueUsed?: number;
    firstAction?: string;
    sizingMath?: null | Record<string, unknown>;
    hardGatesTripped?: string[];
    alternativesConsidered?: string[];
    dataLimitations?: string[];
    model?: string;
    reasoningEffort?: string;
    promptVersion?: string;
    deterministicEngineVersion?: string;
    confidenceDrivers?: string[];
    nextScheduledReview?: string;
    summary?: string;
    selectedPolicy?: string;
    selectedPolicyPreset?: string;
    policyVersion?: string;
    packetHash?: string;
    modelRoute?: string;
    tokenUsage?: Record<string, number>;
    softWarnings?: string[];
    riskIncreasingActionsBlocked?: string[];
    riskReducingActionsAllowed?: string[];
  };
  selectedPolicy?: SelectedPolicy;
  sourceMatrix?: SourceMatrix;
  audit: {
    deterministicEngineVersion: string;
    llmModel?: string;
    llmReasoningEffort?: string;
    modelRoute?: string;
    toolCalls: Array<Record<string, string | number | boolean>>;
    warnings: string[];
    errors: string[];
  };
};

export type Dashboard = {
  paper_portfolio: Portfolio;
  real_portfolio: Portfolio | null;
  watchlist_portfolio: Portfolio | null;
  portfolio_trend: PortfolioTrend;
  opportunities: Opportunity[];
  macro_regime: {
    label: string;
    risk_bias: string;
    score: number;
    latest: Record<string, number>;
    inflation_trend_60d: number;
  };
  recent_recommendations: Recommendation[];
  research_memos: ResearchMemo[];
  recent_backtests: BacktestRun[];
  correlations: Record<string, Record<string, number>>;
  risk_rules: Record<string, number | string | boolean>;
  data_freshness: {
    latest_price_date: string;
    price_bars: number;
    latest_macro_date: string;
    macro_points: number;
    provider_mode: string;
    preferred_price_source: string;
    live_price_symbols: number;
    sample_price_symbols: number;
    price_source_counts: Record<string, number>;
    macro_source_counts: Record<string, number>;
    latest_provider_refresh: null | {
      provider: string;
      status: string;
      finished_at: string;
      records: number;
      message: string;
      error: string;
    };
  };
  providers: ProviderStatus[];
  scheduler: SchedulerStatus;
  connections: ConnectionsStatus;
  quant_diagnostics: QuantDiagnostics;
  advisor: AdvisorStatus;
  advisor_review: AdvisorReview | null;
  advisor_decision: AdvisorDecision | null;
  advisor_run_status: AdvisorRunStatus | null;
  advisor_eval: AdvisorEval | null;
  advisor_packet: AdvisorPacket;
  advisor_trace: AdvisorTrace;
  ai_activity: string;
  decision_packet_status: DecisionPacketStatus;
  portfolio_pulse: {
    current_value: number;
    positions: number;
    day_change: number;
    day_change_pct: number;
    trend_available: boolean;
    source_note: string;
  };
  what_changed: Record<string, string>;
  primary_execution_plan: string[];
  compact_system_status: Record<string, string>;
  action_items: ActionItem[];
  market_scope: MarketScope;
  universe_status: UniverseStatus;
  strategy_reviews: StrategyReview[];
  policy: PolicyStatus;
  ai_status: AiStatus;
};
