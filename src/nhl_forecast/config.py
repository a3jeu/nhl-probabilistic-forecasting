"""Paramètres du projet, lus depuis les variables d'environnement ou le fichier .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "predistat"
    mysql_user: str = "root"
    mysql_password: SecretStr = SecretStr("")

    # API NHL
    nhl_api_web_base_url: str = "https://api-web.nhle.com/v1"
    nhl_api_stats_base_url: str = "https://api.nhle.com/stats/rest/en"
    http_request_delay: float = 1.0
    http_timeout: float = 30.0
    http_user_agent: str = "nhl-probabilistic-forecasting (academic research, UQTR)"

    # Périmètre d'étude (saisons au format NHL, ex. 20052006)
    season_start: int = 20052006
    season_end: int = 20252026

    # Chemins
    data_dir: Path = PROJECT_ROOT / "data"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
