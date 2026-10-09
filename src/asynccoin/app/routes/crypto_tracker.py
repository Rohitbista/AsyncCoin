from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.app.crypto_schemas import (
    CoinHistoryResponse,
    CoinListResponse,
    CoinListShortResponse,
    CoinSnapshotOut,
)
from asynccoin.app.deps import get_current_user
from asynccoin.database import crypto_repo
from asynccoin.database.session import get_db

# Router-level dependency: EVERY route on this router requires a valid login,
# including any you add later. (Public routes live on `app` in server.py.)
router = APIRouter(prefix="/api/crypto", tags=["general_crypto"], dependencies=[Depends(get_current_user)])

_CTX = "asynccoin/app/routes/crypto_tracker"

# ---------------------------------------------------------------------------
# DB-backed endpoints: served from the crypto_snapshots table, filled by the
# background sync. These never call CoinGecko, so all users share one source.
# ---------------------------------------------------------------------------


@router.get("/coins", response_model=CoinListResponse)
async def list_coins(
    limit: int = Query(50, ge=1, le=250),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, min_length=1, max_length=64, description="Match name, symbol or id"),
    sort_by: Literal[
        "market_cap_rank", "market_cap", "current_price", "total_volume", "price_change_percentage_24h", "name"
    ] = "market_cap_rank",
    order: Literal["asc", "desc"] | None = Query(None, description="Default: asc for rank/name, desc otherwise"),
    db: AsyncSession = Depends(get_db),
) -> CoinListResponse:
    descending = (order == "desc") if order else sort_by not in ("market_cap_rank", "name")
    rows, total, last_synced = await crypto_repo.list_latest(
        db, limit=limit, offset=offset, search=search, sort_by=sort_by, descending=descending
    )
    return CoinListResponse(
        last_synced=last_synced,
        total=total,
        limit=limit,
        offset=offset,
        data=[CoinSnapshotOut.model_validate(r) for r in rows],
    )


@router.get("/top", response_model=CoinListShortResponse)
async def top_coins(
    limit: int = Query(10, ge=1, le=100), db: AsyncSession = Depends(get_db)
) -> CoinListShortResponse:
    """Top N by market cap, from the saved data (DB version of /top5)."""
    rows, _, last_synced = await crypto_repo.list_latest(
        db, limit=limit, offset=0, search=None, sort_by="market_cap_rank", descending=False
    )
    return CoinListShortResponse(last_synced=last_synced, data=[CoinSnapshotOut.model_validate(r) for r in rows])


@router.get("/movers", response_model=CoinListShortResponse)
async def movers(
    direction: Literal["gainers", "losers"] = "gainers",
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> CoinListShortResponse:
    """Biggest 24h gainers or losers."""
    rows, last_synced = await crypto_repo.get_movers(db, gainers=direction == "gainers", limit=limit)
    return CoinListShortResponse(last_synced=last_synced, data=[CoinSnapshotOut.model_validate(r) for r in rows])


@router.get("/coins/{coin_id}", response_model=CoinSnapshotOut)
async def get_coin(coin_id: str, db: AsyncSession = Depends(get_db)) -> CoinSnapshotOut:
    row = await crypto_repo.get_latest_for_coin(db, coin_id.lower())
    if row is None:
        raise HTTPException(status_code=404, detail="Coin not found")
    return CoinSnapshotOut.model_validate(row)


@router.get("/coins/{coin_id}/history", response_model=CoinHistoryResponse)
async def coin_history(
    coin_id: str,
    since: datetime | None = Query(None, description="ISO timestamp, e.g. 2026-10-01T00:00:00Z"),
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> CoinHistoryResponse:
    """Price/market history, one point per sync (newest first)."""
    rows = await crypto_repo.get_history_for_coin(db, coin_id.lower(), since=since, until=until, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail="No history for this coin")
    return CoinHistoryResponse(coin_id=coin_id.lower(), count=len(rows), data=rows)