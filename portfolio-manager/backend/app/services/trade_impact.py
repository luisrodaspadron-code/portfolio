"""V8 trade-impact logic.

The deterministic engine must distinguish between trades that worsen a breached
exposure and trades that reduce portfolio risk. Risk-increasing trades are
blocked; risk-reducing trades remain eligible even when a breach exists elsewhere.

Inputs are simple dicts so this module stays decoupled from SQLAlchemy/SQLite
shapes. ``PortfolioSnapshot`` is::

    {
        "totalValue": 100_000.0,
        "positions": [
            {"symbol": "META", "weight": 0.538, "sector": "Communication Services",
             "assetClass": "stock"},
            ...
        ],
        "sectorWeights": {"Communication Services": 0.538, ...},  # optional
    }

``ProposedTrade`` is::

    {
        "symbol": "META",
        "side": "buy" | "sell",
        "weightDelta": 0.02,
        "sector": "Communication Services",
        "assetClass": "stock",
        "isBroadEtf": False,
        "isThematicEtf": False,
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.policy_engine import (
    RiskPolicy,
    PolicyState,
    build_cap_distance,
    policy_state_for_weight,
)


@dataclass(frozen=True)
class TradeImpact:
    worsens_breach: bool
    reduces_portfolio_risk: bool
    blocked: bool
    reasons: list[str]
    pre_state: PolicyState
    post_state: PolicyState
    pre_weight: float
    post_weight: float
    pre_sector_weight: float
    post_sector_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "worsensBreach": self.worsens_breach,
            "reducesPortfolioRisk": self.reduces_portfolio_risk,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
            "preState": self.pre_state,
            "postState": self.post_state,
            "preWeight": round(self.pre_weight, 4),
            "postWeight": round(self.post_weight, 4),
            "preSectorWeight": round(self.pre_sector_weight, 4),
            "postSectorWeight": round(self.post_sector_weight, 4),
        }


_STATE_ORDER: dict[PolicyState, int] = {
    "ok": 0,
    "warning": 1,
    "hard_buy_block": 2,
    "urgent_review": 3,
    "extreme": 4,
}


def _position_weight(snapshot: dict[str, Any], symbol: str) -> float:
    for position in snapshot.get("positions", []) or []:
        if str(position.get("symbol")).upper() == symbol.upper():
            return float(position.get("weight") or 0)
    return 0.0


def _sector_weight(snapshot: dict[str, Any], sector: str) -> float:
    weights = snapshot.get("sectorWeights") or {}
    if isinstance(weights, dict) and sector in weights:
        return float(weights.get(sector) or 0)
    total = 0.0
    for position in snapshot.get("positions", []) or []:
        if str(position.get("sector") or "Unknown") == sector:
            total += float(position.get("weight") or 0)
    return total


def evaluate_trade_impact(
    snapshot: dict[str, Any],
    trade: dict[str, Any],
    policy: RiskPolicy,
) -> TradeImpact:
    """Return the V8 impact of a proposed trade against the snapshot."""

    symbol = str(trade.get("symbol") or "").upper()
    side = str(trade.get("side") or "buy").lower()
    sector = str(trade.get("sector") or "Unknown")
    is_broad_etf = bool(trade.get("isBroadEtf") or False)
    is_thematic_etf = bool(trade.get("isThematicEtf") or False)
    weight_delta = float(trade.get("weightDelta") or 0)

    pre_weight = _position_weight(snapshot, symbol)
    pre_sector_weight = _sector_weight(snapshot, sector)

    if side == "sell":
        weight_delta = -abs(weight_delta)
    elif side == "buy":
        weight_delta = abs(weight_delta)

    post_weight = max(0.0, pre_weight + weight_delta)
    post_sector_weight = max(0.0, pre_sector_weight + weight_delta)

    pre_state = policy_state_for_weight(pre_weight, policy.single_stock)
    post_state = policy_state_for_weight(post_weight, policy.single_stock)

    reasons: list[str] = []
    worsens = False
    reduces = False

    if side == "buy":
        # broad-ETF carve-out: exempt from single-name cap if policy says so
        if is_broad_etf and policy.broad_etf.exempt_from_single_stock_cap:
            if post_weight > policy.broad_etf.max_single_broad_etf:
                worsens = True
                reasons.append(
                    f"Broad ETF {symbol} would exceed the single broad-ETF cap of {policy.broad_etf.max_single_broad_etf:.0%}."
                )
        else:
            if _STATE_ORDER[post_state] > _STATE_ORDER[pre_state]:
                worsens = True
                reasons.append(
                    f"Buying {symbol} pushes its concentration state from {pre_state} to {post_state}."
                )
            elif pre_state in {"hard_buy_block", "urgent_review", "extreme"} and post_weight >= pre_weight:
                worsens = True
                reasons.append(
                    f"{symbol} is already in {pre_state}; new buys are blocked until weight is reduced below the hard buy-block threshold."
                )

        # sector cap
        if post_sector_weight > policy.sector.hard_cap and post_sector_weight > pre_sector_weight:
            worsens = True
            reasons.append(
                f"Buying {symbol} pushes {sector} to {post_sector_weight:.1%}, above the {policy.sector.hard_cap:.0%} sector cap."
            )

        # thematic ETF cap
        if is_thematic_etf and post_weight > policy.thematic_etf.max_single_thematic_etf:
            worsens = True
            reasons.append(
                f"Thematic ETF {symbol} would exceed the single thematic cap of {policy.thematic_etf.max_single_thematic_etf:.0%}."
            )

        # diversification benefit when buying broad ETFs that lower mega-cap concentration
        if is_broad_etf and policy.remediation.allow_risk_reducing_trades_during_breach:
            top_pos_weight = max(
                (float(pos.get("weight") or 0) for pos in snapshot.get("positions") or []),
                default=0.0,
            )
            current_top_state = policy_state_for_weight(top_pos_weight, policy.single_stock)
            if current_top_state in {"hard_buy_block", "urgent_review", "extreme"}:
                reduces = True
                reasons.append(
                    f"Adding diversified exposure via {symbol} reduces the percentage weight of overweight names."
                )

    elif side == "sell":
        if pre_state in {"hard_buy_block", "urgent_review", "extreme"} and post_weight < pre_weight:
            reduces = True
            reasons.append(
                f"Selling {symbol} reduces concentration from {pre_state} state toward {post_state}."
            )
        if post_sector_weight < pre_sector_weight and pre_sector_weight > policy.sector.warning:
            reduces = True
            reasons.append(
                f"Selling {symbol} lowers {sector} exposure ({pre_sector_weight:.1%} → {post_sector_weight:.1%})."
            )

    blocked = bool(worsens) and not (
        reduces and policy.remediation.allow_risk_reducing_trades_during_breach
    )

    return TradeImpact(
        worsens_breach=worsens,
        reduces_portfolio_risk=reduces,
        blocked=blocked,
        reasons=reasons,
        pre_state=pre_state,
        post_state=post_state,
        pre_weight=pre_weight,
        post_weight=post_weight,
        pre_sector_weight=pre_sector_weight,
        post_sector_weight=post_sector_weight,
    )


def trade_worsens_breach(snapshot: dict[str, Any], trade: dict[str, Any], policy: RiskPolicy) -> bool:
    return evaluate_trade_impact(snapshot, trade, policy).worsens_breach


def trade_reduces_portfolio_risk(snapshot: dict[str, Any], trade: dict[str, Any], policy: RiskPolicy) -> bool:
    return evaluate_trade_impact(snapshot, trade, policy).reduces_portfolio_risk


def position_cap_distance(weight: float, policy: RiskPolicy) -> dict[str, Any]:
    return build_cap_distance(weight, policy.single_stock)
