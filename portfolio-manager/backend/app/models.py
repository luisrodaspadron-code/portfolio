from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Instrument(BaseModel):
    symbol: str
    name: str
    asset_class: str
    sector: str
    is_multi_asset: bool = False
    liquidity_score: float = 75


class PriceBar(BaseModel):
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "sample"


class FundamentalFact(BaseModel):
    symbol: str
    metric: str
    period: str
    value: float
    source: str


class MacroPoint(BaseModel):
    series_id: str
    date: str
    value: float
    source: str


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    source: str = "manual"


class PortfolioSummary(BaseModel):
    id: int
    name: str
    mode: str
    base_currency: str
    cash: float
    market_value: float
    total_value: float
    positions: list[dict[str, Any]]


class PaperOrderRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    notes: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class BacktestRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "TLT", "GLD"])
    benchmark_symbol: str = Field(default="SPY", min_length=1, max_length=12)
    start_cash: float = Field(default=100000, gt=0)
    lookback_days: int = Field(default=90, ge=20, le=260)
    rebalance_frequency: Literal["weekly", "monthly"] = "weekly"
    transaction_cost_bps: float = Field(default=5, ge=0, le=100)
    slippage_bps: float = Field(default=3, ge=0, le=100)
    max_positions: int = Field(default=8, ge=1, le=25)
    ablations: list[str] = Field(default_factory=list)
    regimes: list[dict[str, str]] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().upper() for item in value if item.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("benchmark_symbol")
    @classmethod
    def normalize_benchmark_symbol(cls, value: str) -> str:
        return value.strip().upper()


class RecommendationRunRequest(BaseModel):
    portfolio_id: int | None = None
    universe: list[str] | None = None
    max_ideas: int = Field(default=12, ge=1, le=40)
    generate_ai_memos: bool = True


class RiskRulesUpdate(BaseModel):
    max_single_stock_weight: float | None = Field(default=None, ge=0.01, le=1)
    max_etf_weight: float | None = Field(default=None, ge=0.01, le=1)
    max_sector_weight: float | None = Field(default=None, ge=0.01, le=1)
    max_crypto_weight: float | None = Field(default=None, ge=0, le=1)
    drawdown_warning: float | None = Field(default=None, ge=0.01, le=1)
    emergency_risk_off: float | None = Field(default=None, ge=0.01, le=1)
    min_liquidity_score: float | None = Field(default=None, ge=0, le=100)
    max_positions: int | None = Field(default=None, ge=1, le=100)
    decision_cadence: str | None = None

    def compact(self) -> dict[str, Any]:
        return {key: value for key, value in self.model_dump().items() if value is not None}


class PolicyUpdate(BaseModel):
    objective: Literal["competition_growth", "balanced_growth", "capital_preservation"] = "competition_growth"
    risk: Literal["aggressive_managed", "moderate", "defensive"] = "aggressive_managed"
    diversification: Literal["broad_opportunistic", "focused_best_ideas", "highly_diversified"] = "broad_opportunistic"


class AiSettingsUpdate(BaseModel):
    model: Literal["gpt-5-mini", "gpt-5", "gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-mini"] = "gpt-5-mini"
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "medium"
    memo_style: Literal["competition_pm", "decisive", "skeptical", "balanced"] = "competition_pm"
    max_output_tokens: int = Field(default=800, ge=300, le=4000)
    custom_instructions: str = Field(default="", max_length=1200)

    @field_validator("custom_instructions")
    @classmethod
    def clean_custom_instructions(cls, value: str) -> str:
        return value.strip()


class AiRouteConfigUpdate(BaseModel):
    model: str = Field(min_length=2, max_length=80)
    reasoningEffort: Literal["none", "low", "medium", "high", "xhigh"] = "medium"
    maxOutputTokens: int = Field(default=1500, ge=200, le=8000)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value: str) -> str:
        return value.strip()


class AiModelConfigUpdate(BaseModel):
    mode: Literal["balanced", "economy", "deep_competition"] = "balanced"
    fast: AiRouteConfigUpdate | None = None
    specialist: AiRouteConfigUpdate | None = None
    leadPM: AiRouteConfigUpdate | None = None
    deepCompetition: AiRouteConfigUpdate | None = None

    def compact(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        return data


class OpenAiKeyUpdate(BaseModel):
    api_key: str = Field(min_length=20, max_length=400)

    @field_validator("api_key")
    @classmethod
    def clean_api_key(cls, value: str) -> str:
        key = value.strip()
        if not key.startswith("sk-"):
            raise ValueError("OpenAI keys should start with sk-")
        return key


class SecretUpdate(BaseModel):
    provider: Literal["openai", "alpaca", "fred", "alpha_vantage", "sec_edgar"]
    values: dict[str, str] = Field(default_factory=dict)


class ConnectionTestRequest(BaseModel):
    provider: Literal["openai", "alpaca", "fred", "alpha_vantage", "sec_edgar"]


class CopilotRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    conversation_id: str | None = Field(default=None, max_length=80)
    screen_context: str | None = Field(default=None, max_length=80)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("conversation_id", "screen_context")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None
