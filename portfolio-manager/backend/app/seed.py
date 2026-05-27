from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Iterable

from app.database import get_conn, init_db


INSTRUMENTS = [
    ("SPY", "SPDR S&P 500 ETF", "ETF", "Broad Market", 1, 98),
    ("QQQ", "Invesco Nasdaq 100 ETF", "ETF", "Technology Growth", 1, 97),
    ("VTI", "Vanguard Total Stock Market ETF", "ETF", "Broad Market", 1, 96),
    ("IWM", "iShares Russell 2000 ETF", "ETF", "Small Cap", 1, 92),
    ("TLT", "iShares 20+ Year Treasury Bond ETF", "ETF", "Bonds", 1, 90),
    ("GLD", "SPDR Gold Shares", "ETF", "Commodities", 1, 91),
    ("VNQ", "Vanguard Real Estate ETF", "ETF", "Real Estate", 1, 88),
    ("XLF", "Financial Select Sector SPDR", "ETF", "Financials", 1, 90),
    ("XLK", "Technology Select Sector SPDR", "ETF", "Technology", 1, 93),
    ("XLV", "Health Care Select Sector SPDR", "ETF", "Health Care", 1, 89),
    ("XLE", "Energy Select Sector SPDR", "ETF", "Energy", 1, 88),
    ("BITO", "ProShares Bitcoin Strategy ETF", "ETF", "Crypto Proxy", 1, 70),
    ("AAPL", "Apple Inc.", "Stock", "Technology", 0, 97),
    ("MSFT", "Microsoft Corp.", "Stock", "Technology", 0, 97),
    ("NVDA", "NVIDIA Corp.", "Stock", "Technology", 0, 95),
    ("AMZN", "Amazon.com Inc.", "Stock", "Consumer Discretionary", 0, 95),
    ("GOOGL", "Alphabet Inc.", "Stock", "Communication Services", 0, 94),
    ("META", "Meta Platforms Inc.", "Stock", "Communication Services", 0, 94),
    ("BRK.B", "Berkshire Hathaway Inc.", "Stock", "Financials", 0, 92),
    ("JPM", "JPMorgan Chase & Co.", "Stock", "Financials", 0, 91),
    ("LLY", "Eli Lilly and Co.", "Stock", "Health Care", 0, 89),
    ("COST", "Costco Wholesale Corp.", "Stock", "Consumer Staples", 0, 88),
    ("DIA", "SPDR Dow Jones Industrial Average ETF", "ETF", "Large Cap Value", 1, 94),
    ("RSP", "Invesco S&P 500 Equal Weight ETF", "ETF", "Equal Weight", 1, 92),
    ("MTUM", "iShares MSCI USA Momentum Factor ETF", "ETF", "Momentum Factor", 1, 86),
    ("QUAL", "iShares MSCI USA Quality Factor ETF", "ETF", "Quality Factor", 1, 86),
    ("VLUE", "iShares MSCI USA Value Factor ETF", "ETF", "Value Factor", 1, 84),
    ("USMV", "iShares MSCI USA Min Vol Factor ETF", "ETF", "Defensive Equity", 1, 85),
    ("SCHD", "Schwab US Dividend Equity ETF", "ETF", "Dividend Quality", 1, 89),
    ("EFA", "iShares MSCI EAFE ETF", "ETF", "International Developed", 1, 91),
    ("EEM", "iShares MSCI Emerging Markets ETF", "ETF", "Emerging Markets", 1, 89),
    ("VEA", "Vanguard FTSE Developed Markets ETF", "ETF", "International Developed", 1, 90),
    ("VWO", "Vanguard FTSE Emerging Markets ETF", "ETF", "Emerging Markets", 1, 89),
    ("BND", "Vanguard Total Bond Market ETF", "ETF", "Core Bonds", 1, 90),
    ("IEF", "iShares 7-10 Year Treasury Bond ETF", "ETF", "Treasury Bonds", 1, 89),
    ("SHY", "iShares 1-3 Year Treasury Bond ETF", "ETF", "Cash Equivalents", 1, 88),
    ("TIP", "iShares TIPS Bond ETF", "ETF", "Inflation Protected Bonds", 1, 86),
    ("LQD", "iShares Investment Grade Corporate Bond ETF", "ETF", "Credit", 1, 87),
    ("HYG", "iShares High Yield Corporate Bond ETF", "ETF", "High Yield Credit", 1, 87),
    ("DBC", "Invesco DB Commodity Index Tracking Fund", "ETF", "Broad Commodities", 1, 80),
    ("SLV", "iShares Silver Trust", "ETF", "Commodities", 1, 84),
    ("USO", "United States Oil Fund", "ETF", "Energy Commodities", 1, 78),
    ("DBA", "Invesco DB Agriculture Fund", "ETF", "Agriculture Commodities", 1, 74),
    ("UUP", "Invesco DB US Dollar Index Bullish Fund", "ETF", "Currency", 1, 75),
    ("FXE", "Invesco CurrencyShares Euro Trust", "ETF", "Currency", 1, 70),
    ("ARKK", "ARK Innovation ETF", "ETF", "Disruptive Growth", 1, 76),
    ("IBIT", "iShares Bitcoin Trust", "ETF", "Crypto Proxy", 1, 74),
    ("SOXX", "iShares Semiconductor ETF", "ETF", "Semiconductors", 1, 88),
    ("XLY", "Consumer Discretionary Select Sector SPDR", "ETF", "Consumer Discretionary", 1, 87),
    ("XLP", "Consumer Staples Select Sector SPDR", "ETF", "Consumer Staples", 1, 86),
    ("XLU", "Utilities Select Sector SPDR", "ETF", "Utilities", 1, 84),
    ("XLI", "Industrial Select Sector SPDR", "ETF", "Industrials", 1, 87),
    ("XLB", "Materials Select Sector SPDR", "ETF", "Materials", 1, 84),
    ("XLRE", "Real Estate Select Sector SPDR", "ETF", "Real Estate", 1, 84),
    ("KWEB", "KraneShares CSI China Internet ETF", "ETF", "China Growth", 1, 72),
    ("INDA", "iShares MSCI India ETF", "ETF", "India Equity", 1, 78),
    ("EWJ", "iShares MSCI Japan ETF", "ETF", "Japan Equity", 1, 83),
    ("EWZ", "iShares MSCI Brazil ETF", "ETF", "Brazil Equity", 1, 76),
]


PROFILE = {
    "SPY": (475, 0.00042, 0.009, 0.10),
    "QQQ": (395, 0.00055, 0.012, 0.15),
    "VTI": (235, 0.00040, 0.009, 0.08),
    "IWM": (190, 0.00024, 0.014, 0.05),
    "TLT": (92, -0.00003, 0.010, -0.06),
    "GLD": (190, 0.00028, 0.008, 0.04),
    "VNQ": (84, 0.00012, 0.012, 0.03),
    "XLF": (41, 0.00031, 0.012, 0.06),
    "XLK": (210, 0.00058, 0.012, 0.16),
    "XLV": (145, 0.00023, 0.008, 0.03),
    "XLE": (93, 0.00018, 0.015, 0.02),
    "BITO": (27, 0.00066, 0.031, 0.18),
    "AAPL": (185, 0.00038, 0.014, 0.08),
    "MSFT": (410, 0.00053, 0.013, 0.13),
    "NVDA": (880, 0.00095, 0.026, 0.30),
    "AMZN": (175, 0.00049, 0.016, 0.12),
    "GOOGL": (145, 0.00042, 0.015, 0.09),
    "META": (470, 0.00058, 0.019, 0.18),
    "BRK.B": (410, 0.00028, 0.009, 0.02),
    "JPM": (195, 0.00034, 0.013, 0.05),
    "LLY": (760, 0.00070, 0.017, 0.20),
    "COST": (720, 0.00042, 0.011, 0.08),
    "DIA": (385, 0.00032, 0.008, 0.05),
    "RSP": (160, 0.00031, 0.010, 0.06),
    "MTUM": (185, 0.00047, 0.012, 0.12),
    "QUAL": (165, 0.00039, 0.009, 0.08),
    "VLUE": (105, 0.00025, 0.011, 0.02),
    "USMV": (82, 0.00022, 0.006, 0.01),
    "SCHD": (78, 0.00029, 0.007, 0.03),
    "EFA": (76, 0.00018, 0.010, 0.01),
    "EEM": (41, 0.00016, 0.014, 0.02),
    "VEA": (49, 0.00019, 0.010, 0.01),
    "VWO": (43, 0.00017, 0.014, 0.02),
    "BND": (72, 0.00003, 0.004, -0.02),
    "IEF": (95, 0.00002, 0.006, -0.03),
    "SHY": (82, 0.00008, 0.0015, 0.00),
    "TIP": (106, 0.00005, 0.004, 0.00),
    "LQD": (108, 0.00008, 0.006, -0.01),
    "HYG": (77, 0.00017, 0.007, 0.01),
    "DBC": (23, 0.00013, 0.013, 0.02),
    "SLV": (23, 0.00024, 0.018, 0.04),
    "USO": (76, 0.00016, 0.024, 0.02),
    "DBA": (24, 0.00011, 0.010, 0.01),
    "UUP": (29, 0.00005, 0.005, 0.00),
    "FXE": (100, -0.00002, 0.005, -0.01),
    "ARKK": (47, 0.00039, 0.026, 0.12),
    "IBIT": (38, 0.00070, 0.033, 0.18),
    "SOXX": (220, 0.00072, 0.020, 0.22),
    "XLY": (178, 0.00036, 0.012, 0.08),
    "XLP": (75, 0.00018, 0.006, 0.01),
    "XLU": (68, 0.00015, 0.007, 0.00),
    "XLI": (120, 0.00030, 0.010, 0.05),
    "XLB": (87, 0.00022, 0.012, 0.03),
    "XLRE": (39, 0.00012, 0.012, 0.02),
    "KWEB": (28, 0.00018, 0.030, 0.05),
    "INDA": (52, 0.00038, 0.014, 0.09),
    "EWJ": (68, 0.00023, 0.010, 0.03),
    "EWZ": (31, 0.00019, 0.021, 0.04),
}


FUNDAMENTALS = {
    "AAPL": {"revenue_growth": 0.055, "gross_margin": 0.46, "free_cash_flow_yield": 0.032, "debt_to_equity": 1.35},
    "MSFT": {"revenue_growth": 0.135, "gross_margin": 0.70, "free_cash_flow_yield": 0.026, "debt_to_equity": 0.42},
    "NVDA": {"revenue_growth": 0.780, "gross_margin": 0.73, "free_cash_flow_yield": 0.021, "debt_to_equity": 0.24},
    "AMZN": {"revenue_growth": 0.115, "gross_margin": 0.48, "free_cash_flow_yield": 0.020, "debt_to_equity": 0.58},
    "GOOGL": {"revenue_growth": 0.110, "gross_margin": 0.57, "free_cash_flow_yield": 0.040, "debt_to_equity": 0.10},
    "META": {"revenue_growth": 0.175, "gross_margin": 0.81, "free_cash_flow_yield": 0.038, "debt_to_equity": 0.25},
    "BRK.B": {"revenue_growth": 0.070, "gross_margin": 0.34, "free_cash_flow_yield": 0.045, "debt_to_equity": 0.30},
    "JPM": {"revenue_growth": 0.083, "gross_margin": 0.40, "free_cash_flow_yield": 0.050, "debt_to_equity": 1.10},
    "LLY": {"revenue_growth": 0.290, "gross_margin": 0.80, "free_cash_flow_yield": 0.015, "debt_to_equity": 1.55},
    "COST": {"revenue_growth": 0.075, "gross_margin": 0.13, "free_cash_flow_yield": 0.018, "debt_to_equity": 0.42},
}


def business_days(days: int = 520) -> list[date]:
    current = date.today() - timedelta(days=days * 1.45)
    items: list[date] = []
    while len(items) < days:
        if current.weekday() < 5:
            items.append(current)
        current += timedelta(days=1)
    return items


def generated_prices(symbol: str, dates: Iterable[date]) -> list[tuple]:
    base, drift, vol, alpha = PROFILE[symbol]
    rows = []
    price = base
    seed = sum(ord(ch) for ch in symbol)
    for idx, day in enumerate(dates):
        cycle = math.sin((idx + seed) / 17) * vol * 0.55
        shock = math.sin((idx + seed) / 5.3) * vol * 0.28
        regime = alpha * 0.0009 if idx > 330 else 0
        daily_return = drift + cycle + shock + regime
        price = max(2, price * (1 + daily_return))
        spread = max(0.005, abs(daily_return) * 0.65)
        open_price = price / (1 + daily_return * 0.45)
        high = max(open_price, price) * (1 + spread)
        low = min(open_price, price) * (1 - spread)
        volume = 1_000_000 + ((idx * 7919 + seed * 3571) % 25_000_000)
        rows.append(
            (
                symbol,
                day.isoformat(),
                round(open_price, 2),
                round(high, 2),
                round(low, 2),
                round(price, 2),
                float(volume),
                "sample",
            )
        )
    return rows


def seed_sample_data(force: bool = False) -> dict[str, int]:
    init_db()
    dates = business_days()
    with get_conn() as conn:
        for instrument in INSTRUMENTS:
            conn.execute(
                """
                INSERT INTO instruments (symbol, name, asset_class, sector, is_multi_asset, liquidity_score)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    asset_class = excluded.asset_class,
                    sector = excluded.sector,
                    is_multi_asset = excluded.is_multi_asset,
                    liquidity_score = excluded.liquidity_score
                """,
                instrument,
            )

        existing = conn.execute("SELECT COUNT(*) AS count FROM price_bars WHERE source = 'sample'").fetchone()["count"]
        existing_symbols = {
            row["symbol"]
            for row in conn.execute("SELECT DISTINCT symbol FROM price_bars WHERE source = 'sample'").fetchall()
        }
        missing_symbols = [symbol for symbol, *_ in INSTRUMENTS if symbol not in existing_symbols]
        if force or existing == 0 or missing_symbols:
            if force:
                conn.execute("DELETE FROM price_bars WHERE source = 'sample'")
                symbols_to_generate = [symbol for symbol, *_ in INSTRUMENTS]
            elif existing == 0:
                symbols_to_generate = [symbol for symbol, *_ in INSTRUMENTS]
            else:
                symbols_to_generate = missing_symbols
            for symbol in symbols_to_generate:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO price_bars
                    (symbol, date, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    generated_prices(symbol, dates),
                )

        periods = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
        for symbol, metrics in FUNDAMENTALS.items():
            for period_idx, period in enumerate(periods):
                for metric, value in metrics.items():
                    drifted = value * (1 + (period_idx - 2) * 0.015)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO fundamental_facts
                        (symbol, metric, period, value, source)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (symbol, metric, period, round(drifted, 5), "sample"),
                    )

        macro_dates = dates[-260:]
        for idx, day in enumerate(macro_dates):
            values = {
                "FEDFUNDS": 4.75 + math.sin(idx / 37) * 0.35 - idx * 0.0009,
                "CPI_YOY": 3.25 + math.sin(idx / 27) * 0.42 - idx * 0.0015,
                "UNRATE": 4.05 + math.sin(idx / 41) * 0.20 + idx * 0.0007,
                "DGS10": 4.20 + math.sin(idx / 31) * 0.38 - idx * 0.0006,
            }
            for series_id, value in values.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO macro_series (series_id, date, value, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (series_id, day.isoformat(), round(value, 4), "sample"),
                )

        return {
            "instruments": conn.execute("SELECT COUNT(*) AS count FROM instruments").fetchone()["count"],
            "price_bars": conn.execute("SELECT COUNT(*) AS count FROM price_bars").fetchone()["count"],
            "fundamental_facts": conn.execute("SELECT COUNT(*) AS count FROM fundamental_facts").fetchone()["count"],
            "macro_points": conn.execute("SELECT COUNT(*) AS count FROM macro_series").fetchone()["count"],
        }
