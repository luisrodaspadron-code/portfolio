def test_canonical_packet_includes_selected_policy_and_source_matrix(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.advisor_packet import build_canonical_advisor_packet
    from app.services.portfolio_service import import_holdings_csv

    init_db()
    with get_conn() as conn:
        import_holdings_csv(conn, b"MSFT,2,428.50\nMETA,2,604.25\n")
        packet = build_canonical_advisor_packet(conn)
    assert packet["packetVersion"] == "signal-prime.v2"
    assert packet["selectedPolicy"]["preset"] == "balanced"
    assert "singleStock" in packet["selectedPolicy"]
    assert "matrix" in packet["sourceMatrix"]
    assert packet["audit"]["deterministicEngineVersion"].endswith(".v2")


def test_decision_receipt_includes_v8_governance_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.advisor_packet import build_canonical_advisor_packet
    from app.services.portfolio_service import import_holdings_csv

    init_db()
    with get_conn() as conn:
        import_holdings_csv(conn, b"META,40,604.25\n")  # heavy META concentration triggers Trim
        packet = build_canonical_advisor_packet(conn)
    receipt = packet["decisionReceipt"]
    assert receipt["advisoryOnly"] is True
    assert receipt["noOrderPlaced"] is True
    assert receipt["selectedPolicy"]
    assert receipt["policyVersion"]
    assert receipt["packetHash"]
    assert receipt["deterministicEngineVersion"]
    assert "sourceReceipts" in receipt
    assert "tokenUsage" in receipt


def test_v9_mission_control_contract_fields(tmp_path, monkeypatch):
    """V9 Mission Control surface depends on these packet fields being present.

    If any of these disappear, the Mission Control header, pill strip, or
    Advisory Ticket will lose information silently. This is a contract test.
    """
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.advisor_packet import build_canonical_advisor_packet
    from app.services.portfolio_service import import_holdings_csv

    init_db()
    with get_conn() as conn:
        import_holdings_csv(conn, b"META,40,604.25\n")
        packet = build_canonical_advisor_packet(conn)

    receipt = packet["decisionReceipt"]
    # Mission Control pill strip
    assert "riskIncreasingActionsBlocked" in receipt
    assert "riskReducingActionsAllowed" in receipt
    assert isinstance(receipt["riskIncreasingActionsBlocked"], list)
    assert isinstance(receipt["riskReducingActionsAllowed"], list)
    # Advisory ticket — first action must have a sizing snapshot
    first_action = packet["recommendedPriority"]["firstAction"]
    assert first_action is not None
    assert first_action["symbol"] == "META"
    assert first_action["action"] == "TRIM"
    # Trim plan with V8 compliance fields drives the AdvisoryTicket math rows
    trim = first_action["trimPlan"]
    assert trim is not None
    for required_key in (
        "complianceMode",
        "sharesToSellWholeCompliant",
        "sharesToSellWholeReduceOnly",
        "estimatedPostWeightCompliant",
        "policyThreshold",
    ):
        assert required_key in trim, f"missing {required_key} in trimPlan"
    # Source Matrix powers Connections > Source Matrix panel
    matrix = packet["sourceMatrix"]["matrix"]
    assert isinstance(matrix, dict)
    assert "prices" in matrix
    assert "liquidity" in matrix
    assert "filings" in matrix
    assert "portfolioState" in matrix
    assert "ai" in matrix
    assert "telemetry" in matrix
    assert matrix["portfolioState"]["usedInRun"] is True
    assert 0 <= matrix["prices"]["confidence"] <= 1
    # Compare drawer reads policy + blocked actions from the receipt
    assert receipt["selectedPolicy"]
    assert receipt["packetHash"]


def test_legacy_trim_payload_is_normalized_for_compliant_whole_shares():
    from app.services.advisor_packet import _position_decision

    item = {
        "symbol": "META",
        "decision": "Trim",
        "reason": "Concentration remediation.",
        "reason_code": "SINGLE_NAME_EXTREME",
        "target_weight": 0.08,
        "current_weight": 0.5376,
        "confidence_score": 0.9,
        "quant_evidence": [],
        "eligibility": "eligible",
        "risk_check": "",
        "detail_payload": {
            "capDistance": {
                "state": "extreme",
                "currentWeight": 0.5376,
                "extreme": 0.25,
                "breached": True,
            },
            "dataQuality": {
                "provider": "alpaca",
                "sourceTimestamp": "2026-05-26T20:00:00+00:00",
                "receivedAt": "2026-05-27T00:00:00+00:00",
                "ageSeconds": 14_400,
                "freshness": "recent",
                "coverage": "complete",
                "confidence": 0.82,
                "warnings": [],
            },
            "trimPlan": {
                "mode": "redeploy_or_cash",
                "currentValue": 26_261.39,
                "targetValue": 3_908.23,
                "estimatedSellValue": 22_353.16,
                "sharesToSellExact": 36.600718,
                "sharesToSell": 36.6007,
                "sharesToSellWhole": 36,
                "estimatedPostWeight": 0.08,
                "priceUsed": 610.73,
                "priceTimestamp": "2026-05-26",
                "advisoryOnly": True,
            },
        },
    }
    position = {
        "symbol": "META",
        "name": "Meta Platforms Inc.",
        "asset_class": "Stock",
        "sector": "Communication Services",
        "market_value": 26_261.39,
        "latest_price": 610.73,
        "quantity": 43,
    }

    decision = _position_decision(item, position)
    trim = decision["trimPlan"]

    assert trim["sharesToSellWholeCompliant"] == 37
    assert trim["sharesToSellWholeReduceOnly"] == 36
    assert trim["estimatedPostWeightCompliant"] < trim["estimatedPostWeightReduceOnly"]
    assert trim["complianceMode"] == "strict_below_threshold"


def test_packet_built_without_prior_decision_works(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.advisor_packet import build_canonical_advisor_packet

    init_db()
    with get_conn() as conn:
        # No holdings imported, no decisions run; packet should still build deterministic-first
        packet = build_canonical_advisor_packet(conn)
    assert packet["packetVersion"] == "signal-prime.v2"
    assert "selectedPolicy" in packet
    assert packet["audit"]["errors"]  # advisor run has not completed yet
