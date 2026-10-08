"""DB layer for crypto data. Only this module talks SQL for the crypto_snapshots table.
Services call it; routes never touch it directly."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.database.models import CryptoSnapshot

_INSERT_CHUNK = 500  # keeps each INSERT well under asyncpg's 32,767 parameter limit

# Whitelisted sort columns for the list endpoint (never trust a raw column name).
SORT_COLUMNS = {
    "market_cap_rank": CryptoSnapshot.market_cap_rank,
    "market_cap": CryptoSnapshot.market_cap,
    "current_price": CryptoSnapshot.current_price,
    "total_volume": CryptoSnapshot.total_volume,
    "price_change_percentage_24h": CryptoSnapshot.price_change_percentage_24h,
    "name": CryptoSnapshot.name,
}


async def insert_snapshots(session: AsyncSession, rows: Sequence[dict]) -> int:
    """Append a batch of rows (never updates/deletes existing ones)."""
    for i in range(0, len(rows), _INSERT_CHUNK):
        await session.execute(insert(CryptoSnapshot), list(rows[i : i + _INSERT_CHUNK]))
    await session.commit()
    return len(rows)


async def get_latest_fetched_at(session: AsyncSession) -> datetime | None:
    return await session.scalar(select(func.max(CryptoSnapshot.fetched_at)))


async def list_latest(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    search: str | None,
    sort_by: str,
    descending: bool,
) -> tuple[list[CryptoSnapshot], int, datetime | None]:
    """Latest snapshot of each coin. Returns (rows, total_matching, fetched_at)."""
    latest = await get_latest_fetched_at(session)
    if latest is None:
        return [], 0, None

    conditions = [CryptoSnapshot.fetched_at == latest]
    if search:
        like = f"%{search.strip().lower()}%"
        conditions.append(
            or_(func.lower(CryptoSnapshot.name).like(like), func.lower(CryptoSnapshot.symbol).like(like),
                CryptoSnapshot.coin_id.like(like))
        )

    total = await session.scalar(select(func.count()).select_from(CryptoSnapshot).where(*conditions))

    col = SORT_COLUMNS[sort_by]
    order = col.desc().nulls_last() if descending else col.asc().nulls_last()
    result = await session.scalars(
        select(CryptoSnapshot)
        .where(*conditions)
        .order_by(order, CryptoSnapshot.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result), total or 0, latest


async def get_latest_for_coin(session: AsyncSession, coin_id: str) -> CryptoSnapshot | None:
    return await session.scalar(
        select(CryptoSnapshot)
        .where(CryptoSnapshot.coin_id == coin_id)
        .order_by(CryptoSnapshot.fetched_at.desc())
        .limit(1)
    )


async def get_history_for_coin(
    session: AsyncSession,
    coin_id: str,
    *,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> list[CryptoSnapshot]:
    """Newest first."""
    stmt = select(CryptoSnapshot).where(CryptoSnapshot.coin_id == coin_id)
    if since:
        stmt = stmt.where(CryptoSnapshot.fetched_at >= since)
    if until:
        stmt = stmt.where(CryptoSnapshot.fetched_at <= until)
    result = await session.scalars(stmt.order_by(CryptoSnapshot.fetched_at.desc()).limit(limit))
    return list(result)


async def get_movers(
    session: AsyncSession, *, gainers: bool, limit: int
) -> tuple[list[CryptoSnapshot], datetime | None]:
    """Biggest 24h gainers/losers among the latest snapshot."""
    latest = await get_latest_fetched_at(session)
    if latest is None:
        return [], None
    col = CryptoSnapshot.price_change_percentage_24h
    result = await session.scalars(
        select(CryptoSnapshot)
        .where(CryptoSnapshot.fetched_at == latest, col.is_not(None))
        .order_by(col.desc() if gainers else col.asc())
        .limit(limit)
    )
    return list(result), latest