from datetime import date


def test_refresh_prefers_alpaca_latest_bars(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.providers.base import ProviderStatus
    from app.services import data_service

    class FakeAlpacaProvider:
        name = "alpaca"

        def __init__(self, settings):
            self.settings = settings

        def status(self):
            return ProviderStatus(
                name=self.name,
                configured=True,
                capabilities=["latest_minute_equity_bars"],
                note="test provider",
                priority=100,
            )

        async def latest_bars(self, symbols):
            assert "SPY" in symbols
            return {
                "bars": {
                    "SPY": {
                        "t": f"{date.today().isoformat()}T15:59:00Z",
                        "o": 998.0,
                        "h": 1002.0,
                        "l": 997.0,
                        "c": 1000.0,
                        "v": 1234567,
                    }
                }
            }

    monkeypatch.setattr(data_service, "AlpacaProvider", FakeAlpacaProvider)

    result = data_service.refresh_data(force_sample=True)
    alpaca = next(item for item in result["providers"] if item["provider"] == "alpaca")
    assert alpaca["status"] == "success"
    assert alpaca["records"] == 1

    from app.database import get_conn
    from app.providers.registry import provider_statuses

    with get_conn() as conn:
        latest = data_service.load_price_series(conn, ["SPY"])["SPY"][-1]
        freshness = data_service.data_freshness(conn)
        statuses = {item["name"]: item for item in provider_statuses(conn)}

    assert latest["source"] == "alpaca"
    assert latest["close"] == 1000.0
    assert freshness["provider_mode"] == "live"
    assert freshness["preferred_price_source"] == "alpaca"
    assert statuses["alpaca"]["state"] == "live"
