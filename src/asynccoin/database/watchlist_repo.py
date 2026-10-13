"""Database layer for the personal watchlist.

Only SQL lives here: no business rules, no HTTP concerns.
Write functions commit; if your get_db dependency already commits for you,
swap `commit()` for `flush()`.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.database.models import CryptoSnapshot, WatchlistItem

# ----------------------------- watchlist rows -----------------------------


async def list_items(db: AsyncSession, user_id: uuid.UUID) -> list[WatchlistItem]:
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.created_at.asc(), WatchlistItem.id.asc())
    )
    return list(result.scalars().all())


async def count_items(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == user_id)
    )
    return result.scalar_one()


async def get_item(db: AsyncSession, user_id: uuid.UUID, coin_id: str) -> WatchlistItem | None:
    result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == user_id, WatchlistItem.coin_id == coin_id)
    )
    return result.scalar_one_or_none()


async def existing_coin_ids(db: AsyncSession, user_id: uuid.UUID, coin_ids: Sequence[str]) -> set[str]:
    """Which of `coin_ids` this user already tracks."""
    result = await db.execute(
        select(WatchlistItem.coin_id).where(
            WatchlistItem.user_id == user_id, WatchlistItem.coin_id.in_(coin_ids)
        )
    )
    return set(result.scalars().all())


async def add_items(db: AsyncSession, user_id: uuid.UUID, coin_ids: Sequence[str]) -> list[str]:
    """Insert rows, silently skipping ones that already exist (safe under races).
    Returns the coin_ids that were actually inserted."""
    if not coin_ids:
        return []
    stmt = (
        pg_insert(WatchlistItem)
        .values([{"user_id": user_id, "coin_id": c} for c in coin_ids])
        .on_conflict_do_nothing(constraint="uq_user_watchlist_user_id_coin_id")
        .returning(WatchlistItem.coin_id)
    )
    result = await db.execute(stmt)
    inserted = list(result.scalars().all())
    await db.commit()
    return inserted


async def remove_item(db: AsyncSession, user_id: uuid.UUID, coin_id: str) -> bool:
    result = await db.execute(
        delete(WatchlistItem)
        .where(WatchlistItem.user_id == user_id, WatchlistItem.coin_id == coin_id)
        .returning(WatchlistItem.id)
    )
    deleted = result.first() is not None
    await db.commit()
    return deleted


async def update_item(db: AsyncSession, item: WatchlistItem, fields: dict[str, Any]) -> WatchlistItem:
    """Apply a partial update (keys must be note / alert_above / alert_below)."""
    for key, value in fields.items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


# ----------------------------- reading crypto_snapshots -----------------------------


async def get_latest_snapshots(db: AsyncSession, coin_ids: Sequence[str]) -> dict[str, CryptoSnapshot]:
    """Newest snapshot per coin. Uses DISTINCT ON per coin (rather than 'newest fetched_at
    overall') so a coin that missed one sync still shows its last known data."""
    if not coin_ids:
        return {}
    result = await db.execute(
        select(CryptoSnapshot)
        .where(CryptoSnapshot.coin_id.in_(coin_ids))
        .distinct(CryptoSnapshot.coin_id)
        .order_by(CryptoSnapshot.coin_id, CryptoSnapshot.fetched_at.desc())
    )
    return {row.coin_id: row for row in result.scalars().all()}


async def get_snapshots_at(
    db: AsyncSession,
    coin_ids: Sequence[str],
    target: datetime,
    tolerance: timedelta = timedelta(days=1),
) -> dict[str, CryptoSnapshot]:
    """Per coin, the latest snapshot taken at or before `target` but no older than
    `target - tolerance`. Used as the baseline for 7d/30d change. Coins without such a
    snapshot (not enough history yet) are simply absent from the result."""
    if not coin_ids:
        return {}
    result = await db.execute(
        select(CryptoSnapshot)
        .where(
            CryptoSnapshot.coin_id.in_(coin_ids),
            CryptoSnapshot.fetched_at <= target,
            CryptoSnapshot.fetched_at >= target - tolerance,
        )
        .distinct(CryptoSnapshot.coin_id)
        .order_by(CryptoSnapshot.coin_id, CryptoSnapshot.fetched_at.desc())
    )
    return {row.coin_id: row for row in result.scalars().all()}