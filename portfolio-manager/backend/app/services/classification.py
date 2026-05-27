from __future__ import annotations

from typing import Any


SECTOR_BY_SYMBOL: dict[str, tuple[str, str]] = {
    "AAPL": ("Technology", "Mega-cap platform"),
    "MSFT": ("Technology", "Cloud and software"),
    "NVDA": ("Technology", "AI semiconductors"),
    "META": ("Communication Services", "Digital platforms"),
    "GOOGL": ("Communication Services", "Digital platforms"),
    "GOOG": ("Communication Services", "Digital platforms"),
    "AMZN": ("Consumer Discretionary", "E-commerce and cloud"),
    "TSLA": ("Consumer Discretionary", "Electric vehicles"),
    "LLY": ("Health Care", "Pharma"),
    "JPM": ("Financials", "Banking"),
    "BRK.B": ("Financials", "Conglomerate"),
    "COST": ("Consumer Staples", "Retail"),
    "NEE": ("Utilities", "Renewable power"),
    "VST": ("Utilities", "Power generation"),
    "RTX": ("Industrials", "Aerospace and defense"),
    "CCJ": ("Energy", "Uranium and nuclear fuel"),
    "XOM": ("Energy", "Integrated energy"),
    "CVX": ("Energy", "Integrated energy"),
}

ETF_THEME_BY_SYMBOL: dict[str, str] = {
    "SPY": "Broad US equity",
    "VOO": "Broad US equity",
    "VTI": "Broad US equity",
    "QQQ": "Growth and technology",
    "IWM": "US small caps",
    "DIA": "US blue chips",
    "TLT": "Long duration bonds",
    "IEF": "Intermediate Treasury",
    "SHY": "Short Treasury",
    "BIL": "Cash and T-bills",
    "GLD": "Gold",
    "SLV": "Silver",
    "VNQ": "Real estate",
    "XLE": "Energy",
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
}

ETF_NAME_HINTS = {
    "TREASURY": "Fixed income",
    "BOND": "Fixed income",
    "GOLD": "Commodity proxy",
    "SILVER": "Commodity proxy",
    "REAL ESTATE": "Real estate",
    "REIT": "Real estate",
    "ENERGY": "Energy",
    "TECH": "Technology",
    "SEMICONDUCTOR": "Technology",
    "HEALTH": "Health Care",
    "FINANCIAL": "Financials",
    "UTILITY": "Utilities",
    "INDUSTRIAL": "Industrials",
    "CONSUMER": "Consumer",
    "INTERNATIONAL": "International equity",
    "EMERGING": "Emerging markets",
}

UNCLASSIFIED_SECTORS = {"", "Imported", "Imported Universe", "Unknown", "Unclassified"}


def classify_instrument(symbol: str, name: str = "", asset_class: str = "Stock", sector: str = "") -> dict[str, Any]:
    clean_symbol = symbol.strip().upper()
    clean_name = name.strip() or clean_symbol
    clean_asset_class = asset_class or "Stock"
    existing_sector = sector.strip()

    if clean_symbol in ETF_THEME_BY_SYMBOL:
        return {
            "asset_class": "ETF",
            "sector": ETF_THEME_BY_SYMBOL[clean_symbol],
            "theme": ETF_THEME_BY_SYMBOL[clean_symbol],
            "metadata_source": "curated_etf_map",
            "metadata_confidence": 0.92,
        }

    if clean_symbol in SECTOR_BY_SYMBOL:
        mapped_sector, theme = SECTOR_BY_SYMBOL[clean_symbol]
        return {
            "asset_class": clean_asset_class,
            "sector": mapped_sector,
            "theme": theme,
            "metadata_source": "curated_symbol_map",
            "metadata_confidence": 0.9,
        }

    if clean_asset_class == "ETF":
        upper_name = clean_name.upper()
        for hint, mapped_sector in ETF_NAME_HINTS.items():
            if hint in upper_name:
                return {
                    "asset_class": "ETF",
                    "sector": mapped_sector,
                    "theme": mapped_sector,
                    "metadata_source": "etf_name_hint",
                    "metadata_confidence": 0.62,
                }
        return {
            "asset_class": "ETF",
            "sector": "Unclassified ETF",
            "theme": "Unclassified ETF",
            "metadata_source": "asset_class",
            "metadata_confidence": 0.35,
        }

    if existing_sector not in UNCLASSIFIED_SECTORS:
        return {
            "asset_class": clean_asset_class,
            "sector": existing_sector,
            "theme": existing_sector,
            "metadata_source": "instrument",
            "metadata_confidence": 0.7,
        }

    return {
        "asset_class": clean_asset_class,
        "sector": "Unknown",
        "theme": "Unknown",
        "metadata_source": "unclassified",
        "metadata_confidence": 0.15,
    }

