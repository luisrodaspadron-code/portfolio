from __future__ import annotations

from typing import Any


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _unique_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for recommendation in recommendations:
        symbol = recommendation["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        unique.append(recommendation)
    return unique


def _action_item(
    *,
    priority: str,
    action_type: str,
    title: str,
    plain_action: str,
    why: str,
    evidence: list[str],
    risk_check: str,
    next_step: str,
    symbol: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "type": action_type,
        "symbol": symbol,
        "title": title,
        "plain_action": plain_action,
        "why": why,
        "evidence": evidence,
        "risk_check": risk_check,
        "next_step": next_step,
        "confidence": confidence,
    }


def portfolio_action_items(
    *,
    real_portfolio: dict[str, Any] | None,
    recommendations: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    macro: dict[str, Any],
    strategies: list[dict[str, Any]] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    real_loaded = bool(real_portfolio and (real_portfolio["positions"] or real_portfolio["cash"] > 0))
    unique_recs = _unique_recommendations(recommendations)
    strategies = strategies or []

    if not real_loaded:
        items.append(
            _action_item(
                priority="high",
                action_type="setup",
                title="Import your real holdings",
                plain_action="Upload or paste a holdings CSV from your brokerage.",
                why="The advisor cannot judge your actual concentration, cash, risk, or gaps until it knows what you own.",
                evidence=[
                    "No real-money positions are currently loaded.",
                    f"Quant engine status: {diagnostics['status']}.",
                ],
                risk_check="No trades are placed. Import only creates a local analysis copy.",
                next_step="Go to Portfolio and use Import Real Holdings.",
            )
        )

    if diagnostics["status"] != "healthy":
        weak_checks = [check["name"] for check in diagnostics["checks"] if check["status"] != "pass"]
        items.append(
            _action_item(
                priority="high",
                action_type="data",
                title="Fix quant engine warnings",
                plain_action="Review the audit trail before trusting new recommendations.",
                why="The advisor depends on clean price history, macro inputs, feature generation, and risk-gate logging.",
                evidence=weak_checks[:3] or ["One or more quant checks needs attention."],
                risk_check="Weak data can create false confidence, so this is prioritized above allocation ideas.",
                next_step="Open Now and expand the audit trail to inspect the warning checks.",
            )
        )

    if real_loaded and real_portfolio:
        warnings = real_portfolio["stress"].get("warnings", [])
        for warning in warnings[:3]:
            items.append(
                _action_item(
                    priority="high",
                    action_type="risk",
                    title="Review a portfolio risk breach",
                    plain_action="Check whether this exposure is intentional or should be reduced over time.",
                    why=warning,
                    evidence=[
                        f"Portfolio risk level: {real_portfolio['stress']['level']}.",
                        f"Concentration score: {real_portfolio['stress']['concentration']}.",
                    ],
                    risk_check="This is a guardrail warning, not an automatic sell instruction.",
                    next_step="Open Risks to review sector and concentration details.",
                )
            )

        cash_weight = (real_portfolio["cash"] / real_portfolio["total_value"]) if real_portfolio["total_value"] else 0
        if cash_weight > 0.15:
            items.append(
                _action_item(
                    priority="medium",
                    action_type="cash",
                    title="Decide what your cash is supposed to do",
                    plain_action="Choose whether this cash is defensive reserve, dry powder, or capital to deploy gradually.",
                    why="High cash can protect you in drawdowns, but it can also drag long-term compounding if it is accidental.",
                    evidence=[
                        f"Tracked cash is {_pct(cash_weight)} of the real portfolio.",
                        f"Macro regime: {macro['label']}.",
                    ],
                    risk_check="If cash is intentional, keep it. If not, use recommendations as a review list, not an automatic order.",
                    next_step="Compare top BUY ideas against your cash plan.",
                )
            )

    for strategy in strategies[:2]:
        if strategy["stance"] not in {"lean in", "selective"}:
            continue
        candidates = ", ".join(candidate["symbol"] for candidate in strategy["candidates"])
        items.append(
            _action_item(
                priority="medium" if real_loaded else "low",
                action_type="strategy",
                title=f"Review the {strategy['name']} strategy sleeve",
                plain_action=f"Consider whether this sleeve should be represented in your portfolio using candidates like {candidates}.",
                why=f"The robo flow reviewed a broad strategy map and rated this sleeve '{strategy['stance']}' for the current data.",
                evidence=[
                    f"Strategy score: {_pct(strategy['score'])}.",
                    f"Confidence: {_pct(strategy['confidence'])}.",
                    f"Average risk score: {_pct(strategy['risk_score'])}.",
                    strategy["goal"],
                ],
                risk_check="A sleeve can look attractive while still duplicating exposures you already own; compare it against current allocation.",
                next_step="Open Now to review the market-universe trace before making any brokerage decision.",
                confidence=strategy["confidence"],
            )
        )

    buy_recs = [item for item in unique_recs if item["action"] == "BUY" and item["status"] == "pass"]
    for rec in buy_recs[:3]:
        impact = rec.get("portfolio_impact", {})
        target_weight = float(impact.get("target_weight", rec.get("target_weight", 0)))
        risk_score = float(impact.get("risk_score", rec.get("risk_score", 0)))
        items.append(
            _action_item(
                priority="medium" if real_loaded else "low",
                action_type="opportunity",
                symbol=rec["symbol"],
                title=f"Review {rec['symbol']} as a candidate add",
                plain_action=f"Consider whether {rec['symbol']} deserves a place in your portfolio near a {_pct(target_weight)} target weight.",
                why="The model ranked it as a passed BUY candidate after momentum, trend, liquidity, quality, and risk checks.",
                evidence=[
                    f"Confidence: {_pct(rec['confidence'])}.",
                    f"Expected-return score: {_pct(rec['expected_return'])}.",
                    f"Standalone risk score: {_pct(risk_score)}.",
                    rec["reason"],
                ],
                risk_check="Passed current risk gates. Still review valuation, tax impact, and whether it duplicates what you already own.",
                next_step=f"Read the memo for {rec['symbol']} before making any real brokerage decision.",
                confidence=rec["confidence"],
            )
        )

    watch_recs = [item for item in unique_recs if item["action"] == "WATCH"]
    for rec in watch_recs[:2]:
        flags = rec.get("risk_flags", [])
        items.append(
            _action_item(
                priority="low",
                action_type="watch",
                symbol=rec["symbol"],
                title=f"Keep {rec['symbol']} on watch",
                plain_action="Do not rush this idea; let the advisor keep tracking it.",
                why="It has some attractive signals, but the model did not clear it as a clean add.",
                evidence=[
                    f"Confidence: {_pct(rec['confidence'])}.",
                    rec["reason"],
                    *(flags[:1] if flags else []),
                ],
                risk_check="Watch items are intentionally below actionable BUY items.",
                next_step="Revisit after the next automatic advisor cycle.",
                confidence=rec["confidence"],
            )
        )

    if not items and unique_recs:
        top = unique_recs[0]
        items.append(
            _action_item(
                priority="medium",
                action_type="review",
                symbol=top["symbol"],
                title="Review the top model output",
                plain_action=f"Start with {top['symbol']} and read why the model ranked it highly.",
                why="There are no urgent setup or risk items, so the next best use of time is reviewing the highest-ranked idea.",
                evidence=[top["reason"], f"Confidence: {_pct(top['confidence'])}."],
                risk_check="This is a review prompt, not an automatic trade.",
                next_step="Open Memos and read the latest thesis and counterargument.",
                confidence=top["confidence"],
            )
        )

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda item: priority_rank.get(item["priority"], 9))[:limit]
