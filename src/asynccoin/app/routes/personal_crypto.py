"""API layer for the personal crypto watchlist.

HTTP only: parse/validate the request, call the service, map service errors to
status codes. No SQL and no business rules here.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.app.deps import get_current_user
from asynccoin.app.schemas.personal_crypto_schemas import (
    WatchlistAddRequest,
    WatchlistAddResponse,
    WatchlistAlertsResponse,
    WatchlistItemOut,
    WatchlistResponse,
    WatchlistSummaryResponse,
    WatchlistUpdateRequest,
)
from asynccoin.database.session import get_db
from asynccoin.services import personal_crypto_service as service

# Every route here requires a logged-in user.
router = APIRouter(
    prefix="/api/crypto/watchlist",
    tags=["watchlist"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WatchlistResponse:
    """The user's tracked coins with their latest market data."""
    return await service.get_watchlist(db, current_user.id)


@router.post("", response_model=WatchlistAddResponse)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistAddResponse:
    """Track one or more coins by CoinGecko id, e.g. {"coin_ids": ["bitcoin", "solana"]}.
    Unknown ids and already-tracked ids are reported back instead of failing the request."""
    try:
        return await service.add_coins(db, current_user.id, body.coin_ids)
    except service.WatchlistLimitError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# Fixed paths are declared before "/{coin_id}" routes for clarity.
@router.get("/summary", response_model=WatchlistSummaryResponse)
async def watchlist_summary(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WatchlistSummaryResponse:
    """Best/worst 24h performer, total market cap, and 24h / 7d / 30d change per coin."""
    return await service.get_summary(db, current_user.id)


@router.get("/alerts", response_model=WatchlistAlertsResponse)
async def watchlist_alerts(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WatchlistAlertsResponse:
    """Coins whose latest price is currently past the user's alert_above / alert_below."""
    return await service.get_triggered_alerts(db, current_user.id)


@router.patch("/{coin_id}", response_model=WatchlistItemOut)
async def update_watchlist_item(
    coin_id: str,
    body: WatchlistUpdateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemOut:
    """Set or clear a note and price alerts. Only fields present in the body are changed."""
    try:
        return await service.update_coin(
            db, current_user.id, coin_id.strip().lower(), body.model_dump(exclude_unset=True)
        )
    except service.CoinNotTrackedError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except service.InvalidAlertError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{coin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    coin_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await service.remove_coin(db, current_user.id, coin_id.strip().lower())
    except service.CoinNotTrackedError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)