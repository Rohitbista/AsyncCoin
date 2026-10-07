from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings. Override any of them with env vars or a .env file,
    e.g. ASYNCCOIN_CACHE_TTL_SECONDS=30."""

    model_config = SettingsConfigDict(env_prefix="ASYNCCOIN_", env_file=".env", extra="ignore")

    coingecko_url: str

    cache_ttl_seconds: int = 60
    request_timeout_seconds: float = 10.0
    vs_currency: str = "usd"
    coin_ids: str = "bitcoin,ethereum,tether,binancecoin,solana"


settings = Settings()