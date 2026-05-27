from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    database_path: str = "./data/portfolio.sqlite"
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    fred_api_key: str = ""
    alpha_vantage_api_key: str = ""
    sec_user_agent: str = "Local Robo Portfolio Manager contact@example.com"
    alpha_vantage_refresh_limit: int = 12
    sec_edgar_refresh_limit: int = 8
    alpaca_asset_refresh_limit: int = 0
    alpaca_latest_bar_limit: int = 250
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_reasoning_effort: str = "medium"
    openai_memo_style: str = "competition_pm"
    openai_custom_instructions: str = ""
    openai_max_output_tokens: int = 800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def resolved_database_path(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
