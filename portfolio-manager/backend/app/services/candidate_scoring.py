"""V8 candidate scoring.

A candidate's eligibility is no longer "score > 0.42 → fail". V8 requires a
multi-component score with explicit blockers/penalties and a limited-history
playbook. The deterministic engine consumes a ``CandidateScore`` to decide
``Add`` / ``Stagger Entry`` / ``Wait For Data`` / ``Avoid``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.policy_engine import RiskPolicy


LimitedHistoryState = Literal["too_new", "speculative_watch", "restricted_signal", "full_signal"]


@dataclass
class LimitedHistoryDecision:
    symbol: str
    history_days: int
    state: LimitedHistoryState
    max_initial_weight: float
    requires_manual_review: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "historyDays": int(self.history_days),
            "state": self.state,
            "maxInitialWeight": round(self.max_initial_weight, 4),
            "requiresManualReview": bool(self.requires_manual_review),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def classify_history(symbol: str, history_days: int, policy: RiskPolicy) -> LimitedHistoryDecision:
    dq = policy.data_quality
    if history_days < dq.min_history_days_watch_only:
        return LimitedHistoryDecision(
            symbol=symbol,
            history_days=history_days,
            state="too_new",
            max_initial_weight=0.0,
            requires_manual_review=True,
            blockers=[f"{symbol} has fewer than {dq.min_history_days_watch_only} trading days; watch-only."],
        )
    if history_days < dq.min_history_days_restricted:
        return LimitedHistoryDecision(
            symbol=symbol,
            history_days=history_days,
            state="speculative_watch",
            max_initial_weight=0.0,
            requires_manual_review=True,
            blockers=[f"{symbol} has limited history; speculative watch only, no normal add."],
        )
    if history_days < dq.min_history_days_full:
        return LimitedHistoryDecision(
            symbol=symbol,
            history_days=history_days,
            state="restricted_signal",
            max_initial_weight=policy.single_new_stock_add.initial_max / 2,
            requires_manual_review=False,
            warnings=[f"{symbol} runs on restricted-signal history (≥ {dq.min_history_days_restricted}d, < {dq.min_history_days_full}d). Use smaller initial size."],
        )
    return LimitedHistoryDecision(
        symbol=symbol,
        history_days=history_days,
        state="full_signal",
        max_initial_weight=policy.single_new_stock_add.target_max,
        requires_manual_review=False,
    )


@dataclass
class CandidateScore:
    symbol: str
    total_score: float
    momentum_score: float = 0.0
    value_proxy_score: float | None = None
    quality_score: float | None = None
    low_vol_score: float = 0.0
    liquidity_score: float = 0.0
    drawdown_score: float = 0.0
    correlation_benefit_score: float = 0.0
    macro_fit_score: float = 0.0
    data_quality_score: float = 0.0
    factor_exposure_penalty: float = 0.0
    sector_concentration_penalty: float = 0.0
    turnover_penalty: float = 0.0
    tax_aware_penalty: float | None = None
    penalties: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    limited_history: LimitedHistoryDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol,
            "totalScore": round(self.total_score, 4),
            "momentumScore": round(self.momentum_score, 4),
            "lowVolScore": round(self.low_vol_score, 4),
            "liquidityScore": round(self.liquidity_score, 4),
            "drawdownScore": round(self.drawdown_score, 4),
            "correlationBenefitScore": round(self.correlation_benefit_score, 4),
            "macroFitScore": round(self.macro_fit_score, 4),
            "dataQualityScore": round(self.data_quality_score, 4),
            "factorExposurePenalty": round(self.factor_exposure_penalty, 4),
            "sectorConcentrationPenalty": round(self.sector_concentration_penalty, 4),
            "turnoverPenalty": round(self.turnover_penalty, 4),
            "penalties": list(self.penalties),
            "blockers": list(self.blockers),
        }
        if self.value_proxy_score is not None:
            payload["valueProxyScore"] = round(float(self.value_proxy_score), 4)
        if self.quality_score is not None:
            payload["qualityScore"] = round(float(self.quality_score), 4)
        if self.tax_aware_penalty is not None:
            payload["taxAwarePenalty"] = round(float(self.tax_aware_penalty), 4)
        if self.limited_history is not None:
            payload["limitedHistory"] = self.limited_history.to_dict()
        return payload


def score_candidate(
    candidate: dict[str, Any],
    policy: RiskPolicy,
    *,
    current_sector_weight: float = 0.0,
    history_days: int | None = None,
) -> CandidateScore:
    symbol = str(candidate.get("symbol") or "").upper()
    asset_class = str(candidate.get("asset_class") or "").lower()
    sector = str(candidate.get("sector") or "Unknown")
    is_thematic = bool(candidate.get("is_thematic_etf"))
    is_broad_etf = bool(candidate.get("is_broad_etf") or candidate.get("asset_class") == "ETF" and not is_thematic)

    momentum = float(candidate.get("score") or 0)
    liquidity_score_raw = float(candidate.get("liquidity_score") or 0)
    risk_score = float(candidate.get("risk_score") or 0)
    confidence = float(candidate.get("confidence") or 0)
    dollar_volume = float(candidate.get("dollar_volume") or 0)
    volatility = float(candidate.get("annualized_vol") or 0)
    drawdown = float(candidate.get("max_drawdown") or 0)
    data_freshness = str(candidate.get("data_freshness") or "missing")

    liquidity_score = max(0.0, min(1.0, liquidity_score_raw / 100.0))
    low_vol_score = max(0.0, 1.0 - volatility) if volatility else 0.5
    drawdown_score = max(0.0, 1.0 + drawdown)
    data_quality_score = {"live": 1.0, "recent": 0.85, "partial": 0.65, "stale": 0.45, "missing": 0.2}.get(
        data_freshness, 0.5
    )

    penalties: list[str] = []
    blockers: list[str] = []
    factor_penalty = 0.0
    sector_penalty = 0.0

    if dollar_volume and dollar_volume < policy.liquidity.min_dollar_volume_default:
        blockers.append(
            f"{symbol} dollar volume ({dollar_volume:,.0f}) is below the configured floor ({policy.liquidity.min_dollar_volume_default:,.0f})."
        )
    if liquidity_score_raw and liquidity_score_raw < 50:
        blockers.append(f"{symbol} liquidity score is too low for normal sizing.")

    if volatility and volatility > 0.60:
        blockers.append(f"{symbol} annualized volatility {volatility:.0%} exceeds the add threshold.")
    elif volatility and volatility > 0.40:
        penalties.append(f"{symbol} runs hot on volatility ({volatility:.0%}); use smaller tranche size.")
        factor_penalty += 0.10

    if drawdown and drawdown < -0.45:
        blockers.append(f"{symbol} drawdown ({drawdown:.0%}) exceeds the add threshold.")
    elif drawdown and drawdown < -0.25:
        penalties.append(f"{symbol} has had a deep drawdown ({drawdown:.0%}); confidence is reduced.")

    if "Crypto" in sector:
        if not policy.crypto.enabled_by_default:
            blockers.append(
                "Crypto is disabled by default; enable crypto in policy settings and confirm custody before adding."
            )
        elif current_sector_weight + 0.01 > policy.crypto.max_total:
            blockers.append(
                f"Adding {symbol} would push crypto exposure above the {policy.crypto.max_total:.0%} total cap."
            )

    if is_thematic and not is_broad_etf:
        penalties.append(f"{symbol} is a thematic ETF; size is capped at {policy.thematic_etf.max_single_thematic_etf:.0%}.")
        factor_penalty += 0.05

    if sector != "Unknown" and current_sector_weight >= policy.sector.hard_cap:
        blockers.append(
            f"New adds in {sector} are blocked; sector exposure is already at {current_sector_weight:.1%} (cap {policy.sector.hard_cap:.0%})."
        )
    elif sector != "Unknown" and current_sector_weight >= policy.sector.warning:
        sector_penalty = round(min(0.25, (current_sector_weight - policy.sector.warning) * 2.0), 4)
        if sector_penalty:
            penalties.append(
                f"{sector} exposure is in the warning zone ({current_sector_weight:.1%}); add tranche size is reduced."
            )

    if data_freshness in {"missing", "stale"}:
        blockers.append(f"{symbol} data is {data_freshness}; sizing is blocked until fresh prices return.")

    if risk_score > 0.68:
        blockers.append(f"{symbol} composite risk score {risk_score:.2f} exceeds the add threshold.")
    elif risk_score > 0.42:
        penalties.append(f"{symbol} composite risk score {risk_score:.2f} is elevated.")
        factor_penalty += 0.05

    limited = None
    if history_days is not None:
        limited = classify_history(symbol, history_days, policy)
        if limited.blockers:
            blockers.extend(limited.blockers)
        if limited.warnings:
            penalties.extend(limited.warnings)

    base = (
        0.45 * momentum
        + 0.10 * liquidity_score
        + 0.10 * low_vol_score
        + 0.10 * drawdown_score
        + 0.10 * data_quality_score
        + 0.15 * confidence
    )
    total = max(-1.0, min(1.0, base - factor_penalty - sector_penalty))

    return CandidateScore(
        symbol=symbol,
        total_score=total,
        momentum_score=momentum,
        low_vol_score=low_vol_score,
        liquidity_score=liquidity_score,
        drawdown_score=drawdown_score,
        data_quality_score=data_quality_score,
        factor_exposure_penalty=factor_penalty,
        sector_concentration_penalty=sector_penalty,
        penalties=penalties,
        blockers=blockers,
        limited_history=limited,
    )
