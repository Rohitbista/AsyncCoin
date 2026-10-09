"""Service layer for the personal watchlist.

Business rules live here (limits, validation against synced coins, alert logic,
performance maths). It talks to the DB only through watchlist_repo and knows
nothing about HTTP; the API layer translates the exceptions below into status codes.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.app.schemas.crypto_schemas import CoinSnapshotOut
from asynccoin.app.schemas.personal_crypto_schemas import (
    CoinPerformance,
    WatchlistAddResponse,
    WatchlistAlertsResponse,
    WatchlistItemOut,
    WatchlistResponse,
    WatchlistSummaryResponse,
)
from asynccoin.database import watchlist_repo
from asynccoin.database.models import CryptoSnapshot, WatchlistItem

MAX_WATCHLIST_SIZE = 100


# ----------------------------- errors -----------------------------


class WatchlistError(Exception):
    """Base class for expected, user-facing watchlist errors."""


class WatchlistLimitError(WatchlistError):
    pass


class CoinNotTrackedError(WatchlistError):
    pass


class InvalidAlertError(WatchlistError):
    pass


# ----------------------------- helpers -----------------------------


def _alert_status(item: WatchlistItem, snap: CryptoSnapshot | None) -> Literal["above", "below"] | None:
    if snap is None or snap.current_price is None:
        return None
    price = snap.current_price
    if item.alert_above is not None and price >= item.alert_above:
        return "above"
    if item.alert_below is not None and price <= item.alert_below:
        return "below"
    return None


def _to_item_out(item: WatchlistItem, snap: CryptoSnapshot | None) -> WatchlistItemOut:
    return WatchlistItemOut(
        coin_id=item.coin_id,
        added_at=item.created_at,
        note=item.note,
        alert_above=item.alert_above,
        alert_below=item.alert_below,
        alert_status=_alert_status(item, snap),
        coin=CoinSnapshotOut.model_validate(snap) if snap else None,
    )


def _last_synced(snaps: dict[str, CryptoSnapshot]) -> datetime | None:
    return max((s.fetched_at for s in snaps.values()), default=None)


def _pct_change(now: float | None, then: float | None) -> float | None:
    if now is None or then is None or then == 0:
        return None
    return (now - then) / then * 100


# ----------------------------- operations -----------------------------


async def get_watchlist(db: AsyncSession, user_id: uuid.UUID) -> WatchlistResponse:
    items = await watchlist_repo.list_items(db, user_id)
    snaps = await watchlist_repo.get_latest_snapshots(db, [i.coin_id for i in items])
    return WatchlistResponse(
        last_synced=_last_synced(snaps),
        count=len(items),
        data=[_to_item_out(i, snaps.get(i.coin_id)) for i in items],
    )


async def add_coins(db: AsyncSession, user_id: uuid.UUID, coin_ids: list[str]) -> WatchlistAddResponse:
    # 1. Only accept coins we actually have data for.
    known = await watchlist_repo.get_latest_snapshots(db, coin_ids)
    not_found = [c for c in coin_ids if c not in known]
    valid = [c for c in coin_ids if c in known]

    # 2. Split off the ones already tracked.
    already = await watchlist_repo.existing_coin_ids(db, user_id, valid)
    to_add = [c for c in valid if c not in already]

    # 3. Enforce the per-user cap.
    current = await watchlist_repo.count_items(db, user_id)
    if current + len(to_add) > MAX_WATCHLIST_SIZE:
        raise WatchlistLimitError(
            f"Watchlist limit is {MAX_WATCHLIST_SIZE} coins "
            f"(you track {current}, tried to add {len(to_add)})."
        )

    inserted = await watchlist_repo.add_items(db, user_id, to_add)
    # `inserted` can be smaller than `to_add` if a concurrent request added one first.
    already_tracked = [c for c in valid if c not in inserted]

    return WatchlistAddResponse(
        added=inserted,
        already_tracked=already_tracked,
        not_found=not_found,
        tracked_count=current + len(inserted),
    )


async def remove_coin(db: AsyncSession, user_id: uuid.UUID, coin_id: str) -> None:
    if not await watchlist_repo.remove_item(db, user_id, coin_id):
        raise CoinNotTrackedError(f"'{coin_id}' is not in your watchlist")


async def update_coin(
    db: AsyncSession, user_id: uuid.UUID, coin_id: str, fields: dict[str, Any]
) -> WatchlistItemOut:
    """`fields` contains only the keys the client actually sent (so null can clear a value)."""
    item = await watchlist_repo.get_item(db, user_id, coin_id)
    if item is None:
        raise CoinNotTrackedError(f"'{coin_id}' is not in your watchlist")

    # Validate the final combination, not just the incoming fields.
    above = fields.get("alert_above", item.alert_above)
    below = fields.get("alert_below", item.alert_below)
    if above is not None and below is not None and below >= above:
        raise InvalidAlertError("alert_below must be lower than alert_above")

    if "note" in fields and fields["note"] is not None:
        fields["note"] = fields["note"].strip() or None

    if fields:
        item = await watchlist_repo.update_item(db, item, fields)

    snaps = await watchlist_repo.get_latest_snapshots(db, [coin_id])
    return _to_item_out(item, snaps.get(coin_id))


async def get_triggered_alerts(db: AsyncSession, user_id: uuid.UUID) -> WatchlistAlertsResponse:
    items = await watchlist_repo.list_items(db, user_id)
    with_alerts = [i for i in items if i.alert_above is not None or i.alert_below is not None]
    snaps = await watchlist_repo.get_latest_snapshots(db, [i.coin_id for i in with_alerts])

    triggered = [
        _to_item_out(i, snaps.get(i.coin_id))
        for i in with_alerts
        if _alert_status(i, snaps.get(i.coin_id)) is not None
    ]
    return WatchlistAlertsResponse(last_synced=_last_synced(snaps), count=len(triggered), data=triggered)


async def get_summary(db: AsyncSession, user_id: uuid.UUID) -> WatchlistSummaryResponse:
    items = await watchlist_repo.list_items(db, user_id)
    coin_ids = [i.coin_id for i in items]

    latest = await watchlist_repo.get_latest_snapshots(db, coin_ids)
    now = datetime.now(timezone.utc)
    week_ago = await watchlist_repo.get_snapshots_at(db, coin_ids, now - timedelta(days=7))
    month_ago = await watchlist_repo.get_snapshots_at(db, coin_ids, now - timedelta(days=30))

    performance: list[CoinPerformance] = []
    for cid in coin_ids:
        snap = latest.get(cid)
        if snap is None:
            continue
        performance.append(
            CoinPerformance(
                coin_id=cid,
                name=snap.name,
                symbol=snap.symbol,
                current_price=snap.current_price,
                change_24h_pct=snap.price_change_percentage_24h,
                change_7d_pct=_pct_change(snap.current_price, getattr(week_ago.get(cid), "current_price", None)),
                change_30d_pct=_pct_change(snap.current_price, getattr(month_ago.get(cid), "current_price", None)),
            )
        )

    ranked = [p for p in performance if p.change_24h_pct is not None]
    caps = [s.market_cap for s in latest.values() if s.market_cap is not None]

    return WatchlistSummaryResponse(
        last_synced=_last_synced(latest),
        tracked_count=len(items),
        total_market_cap=sum(caps) if caps else None,
        best_24h=max(ranked, key=lambda p: p.change_24h_pct, default=None),
        worst_24h=min(ranked, key=lambda p: p.change_24h_pct, default=None),
        performance=performance,
    )