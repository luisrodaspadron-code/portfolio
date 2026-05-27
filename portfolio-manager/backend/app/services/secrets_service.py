from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings


PROVIDER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "description": "Portfolio-level AI reviews and research memos.",
        "fields": [
            {"key": "openai_api_key", "label": "API key", "secret": True, "placeholder": "sk-..."},
        ],
    },
    "alpaca": {
        "label": "Alpaca",
        "description": "Preferred live/recent equity bars and paper-trading context.",
        "fields": [
            {"key": "alpaca_api_key", "label": "API key", "secret": True, "placeholder": "APCA..."},
            {"key": "alpaca_secret_key", "label": "Secret key", "secret": True, "placeholder": "secret..."},
        ],
    },
    "fred": {
        "label": "FRED",
        "description": "Macro regime data for rates, inflation, labor, and liquidity.",
        "fields": [
            {"key": "fred_api_key", "label": "API key", "secret": True, "placeholder": "FRED key"},
        ],
    },
    "alpha_vantage": {
        "label": "Alpha Vantage",
        "description": "Fallback daily prices, fundamentals, technicals, and crypto coverage.",
        "fields": [
            {"key": "alpha_vantage_api_key", "label": "API key", "secret": True, "placeholder": "Alpha Vantage key"},
        ],
    },
    "sec_edgar": {
        "label": "SEC EDGAR",
        "description": "Company facts and filings. SEC requires a real contact identity.",
        "fields": [
            {"key": "sec_user_agent", "label": "Contact identity", "secret": False, "placeholder": "Your Name email@example.com"},
        ],
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _secret_key_path() -> Path:
    return get_settings().resolved_database_path.parent / "local_secret.key"


def _load_or_create_key() -> bytes:
    path = _secret_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes().strip()

    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def _encrypt_secret(value: str) -> str:
    return "fernet:" + _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("fernet:"):
        return value
    token = value.removeprefix("fernet:").encode("utf-8")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def migrate_legacy_secrets(conn) -> None:
    rows = conn.execute("SELECT provider, key, value FROM local_secrets WHERE value NOT LIKE 'fernet:%'").fetchall()
    timestamp = _now()
    for row in rows:
        value = str(row["value"] or "")
        if not value:
            continue
        conn.execute(
            """
            UPDATE local_secrets
            SET value = ?, updated_at = ?
            WHERE provider = ? AND key = ?
            """,
            (_encrypt_secret(value), timestamp, row["provider"], row["key"]),
        )


def _provider_field_keys(provider: str) -> set[str]:
    definition = PROVIDER_DEFINITIONS.get(provider)
    if not definition:
        raise ValueError(f"Unknown provider: {provider}")
    return {field["key"] for field in definition["fields"]}


def _mask(value: str, *, secret: bool = True) -> str:
    if not value:
        return ""
    if not secret:
        return "Configured locally"
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}••••{value[-4:]}"


def local_secret_values(conn) -> dict[str, str]:
    migrate_legacy_secrets(conn)
    rows = conn.execute("SELECT provider, key, value FROM local_secrets").fetchall()
    return {row["key"]: _decrypt_secret(str(row["value"])) for row in rows}


def get_local_secret(conn, provider: str, key: str) -> str:
    migrate_legacy_secrets(conn)
    row = conn.execute("SELECT value FROM local_secrets WHERE provider = ? AND key = ?", (provider, key)).fetchone()
    return _decrypt_secret(str(row["value"])) if row else ""


def get_effective_secret(conn, provider: str, key: str) -> str:
    value = get_local_secret(conn, provider, key)
    if value:
        return value
    return str(getattr(get_settings(), key, "") or "")


def effective_settings(conn) -> Settings:
    overrides = local_secret_values(conn)
    return get_settings().model_copy(update=overrides)


def save_provider_secrets(conn, provider: str, values: dict[str, Any]) -> None:
    allowed = _provider_field_keys(provider)
    cleaned: dict[str, str] = {}
    for key, raw_value in values.items():
        if key not in allowed:
            continue
        value = str(raw_value or "").strip()
        if not value:
            continue
        if key == "openai_api_key" and not value.startswith("sk-"):
            raise ValueError("OpenAI keys should start with sk-")
        if key == "sec_user_agent" and ("@" not in value or "contact@example.com" in value.lower()):
            raise ValueError("SEC identity should include your real contact email.")
        cleaned[key] = value
    if not cleaned:
        raise ValueError("No valid connection values were provided.")

    timestamp = _now()
    for key, value in cleaned.items():
        conn.execute(
            """
            INSERT INTO local_secrets (provider, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (provider, key, _encrypt_secret(value), timestamp),
        )


def delete_provider_secrets(conn, provider: str) -> None:
    if provider not in PROVIDER_DEFINITIONS:
        raise ValueError(f"Unknown provider: {provider}")
    conn.execute("DELETE FROM local_secrets WHERE provider = ?", (provider,))


def secret_field_status(conn, provider: str) -> list[dict[str, Any]]:
    migrate_legacy_secrets(conn)
    definition = PROVIDER_DEFINITIONS[provider]
    settings = get_settings()
    rows = conn.execute("SELECT key, value FROM local_secrets WHERE provider = ?", (provider,)).fetchall()
    local_values = {row["key"]: _decrypt_secret(str(row["value"])) for row in rows}
    fields = []
    for field in definition["fields"]:
        key = field["key"]
        local_value = local_values.get(key, "")
        env_value = str(getattr(settings, key, "") or "")
        if key == "sec_user_agent" and "contact@example.com" in env_value.lower():
            env_value = ""
        value = local_value or env_value
        fields.append(
            {
                "key": key,
                "label": field["label"],
                "secret": bool(field["secret"]),
                "placeholder": field["placeholder"],
                "configured": bool(value),
                "source": "local" if local_value else "env" if env_value else "",
                "masked_value": _mask(value, secret=bool(field["secret"])),
            }
        )
    return fields
