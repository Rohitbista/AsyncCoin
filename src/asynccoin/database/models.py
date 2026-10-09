import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from asynccoin.database.base import Base

# Token purposes (one table serves email verification now, password reset later).
PURPOSE_VERIFY_EMAIL = "verify_email"
PURPOSE_PASSWORD_RESET = "password_reset"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # We always store emails lowercased; the DB enforces it.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tokens: Mapped[list["UserToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    watchlist: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserToken(Base):
    """Single-use, expiring tokens. Only the SHA-256 hash is stored, never the raw token."""

    __tablename__ = "user_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'password_reset')", name="purpose_valid"
        ),
        Index("ix_user_tokens_user_id_purpose", "user_id", "purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="tokens")

class WatchlistItem(Base):
    """One row per (user, coin) the user wants to track.
 
    `coin_id` is the CoinGecko id (same value as crypto_snapshots.coin_id). It is
    deliberately NOT a foreign key: crypto_snapshots is append-only with many rows
    per coin, so there is no single row to reference. The service layer validates
    that the coin exists in crypto_snapshots before inserting.
    """
 
    __tablename__ = "user_watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "coin_id", name="uq_user_watchlist_user_id_coin_id"),
        CheckConstraint("coin_id = lower(coin_id)", name="watchlist_coin_id_lowercase"),
        CheckConstraint("alert_above IS NULL OR alert_above > 0", name="watchlist_alert_above_positive"),
        CheckConstraint("alert_below IS NULL OR alert_below > 0", name="watchlist_alert_below_positive"),
        Index("ix_user_watchlist_user_id", "user_id"),
    )
 
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    coin_id: Mapped[str] = mapped_column(String(128), nullable=False)
 
    # Optional personal extras.
    note: Mapped[str | None] = mapped_column(String(500))
    alert_above: Mapped[float | None] = mapped_column(Float)  # flag when price >= this
    alert_below: Mapped[float | None] = mapped_column(Float)  # flag when price <= this
 
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
 
    user: Mapped[User] = relationship(back_populates="watchlist")

class CryptoSnapshot(Base):
    """One row per coin per sync. Append-only: every sync adds a new batch of rows
    (all sharing the same `fetched_at`), nothing is overwritten. This gives price
    history for free. "Latest" data = the rows with the newest `fetched_at`.
    Shared by all users (not tied to any user)."""
 
    __tablename__ = "crypto_snapshots"
    __table_args__ = (
        Index("ix_crypto_snapshots_coin_id_fetched_at", "coin_id", "fetched_at"),
        Index("ix_crypto_snapshots_fetched_at_rank", "fetched_at", "market_cap_rank"),
    )
 
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
 
    # CoinGecko's id, e.g. "bitcoin" (stable identifier; symbols are not unique).
    coin_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    image: Mapped[str | None] = mapped_column(String(512))
 
    current_price: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    market_cap_rank: Mapped[int | None] = mapped_column()
    fully_diluted_valuation: Mapped[float | None] = mapped_column(Float)
    total_volume: Mapped[float | None] = mapped_column(Float)
    high_24h: Mapped[float | None] = mapped_column(Float)
    low_24h: Mapped[float | None] = mapped_column(Float)
    price_change_24h: Mapped[float | None] = mapped_column(Float)
    price_change_percentage_24h: Mapped[float | None] = mapped_column(Float)
    market_cap_change_24h: Mapped[float | None] = mapped_column(Float)
    market_cap_change_percentage_24h: Mapped[float | None] = mapped_column(Float)
    circulating_supply: Mapped[float | None] = mapped_column(Float)
    total_supply: Mapped[float | None] = mapped_column(Float)
    max_supply: Mapped[float | None] = mapped_column(Float)
    ath: Mapped[float | None] = mapped_column(Float)
    ath_change_percentage: Mapped[float | None] = mapped_column(Float)
    ath_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    atl: Mapped[float | None] = mapped_column(Float)
    atl_change_percentage: Mapped[float | None] = mapped_column(Float)
    atl_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))