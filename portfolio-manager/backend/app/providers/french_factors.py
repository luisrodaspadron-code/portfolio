from __future__ import annotations

from typing import Any


def factor_library_status() -> dict[str, Any]:
    """Scaffolding for Kenneth French / Fama-French factor attribution."""
    return {
        "loaded": False,
        "provider": "french_factors",
        "message": "Factor library not loaded. Configure a local cache path to enable Fama-French attribution.",
        "available_factors": ["MKT-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
    }


def factor_exposure_summary(_symbols: list[str]) -> dict[str, Any]:
    status = factor_library_status()
    return {
        "status": status["loaded"],
        "message": status["message"],
        "exposures": {},
    }
