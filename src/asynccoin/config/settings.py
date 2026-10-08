from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings. Override any of them with env vars or a .env file,
    e.g. ASYNCCOIN_CACHE_TTL_SECONDS=30."""

    model_config = SettingsConfigDict(env_prefix="ASYNCCOIN_", env_file=".env", extra="ignore")

    coingecko_url: str

    # Must be the asyncpg flavour: postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str

    cache_ttl_seconds: int = 60
    request_timeout_seconds: float = 10.0
    vs_currency: str = "usd"
    coin_ids: str = "bitcoin,ethereum,tether,binancecoin,solana"

    # --- Auth ---
    jwt_secret: str  # generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # --- Email verification (Brevo) ---
    # If brevo_api_key is empty, the verification link is logged instead of emailed (dev mode).
    brevo_api_key: str = ""
    brevo_sender_email: str = ""  # must be a sender/domain verified in Brevo
    brevo_sender_name: str = "Async Coin"
    # Frontend page that receives ?token=... and POSTs it to /api/auth/verify-email
    frontend_verify_url: str = "http://localhost:3000/verify-email"
    verification_token_ttl_hours: int = 24
    verification_resend_cooldown_seconds: int = 600


settings = Settings()