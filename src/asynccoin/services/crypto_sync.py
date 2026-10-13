"""Service layer: pulls market data from CoinGecko and appends it to the DB,
plus the background scheduler. Flow: app -> service (this file) -> db (crypto_repo)."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from asynccoin.config.settings import settings
from asynccoin.database import crypto_repo
from asynccoin.database.session import SessionLocal

logger = logging.getLogger(__name__)

_sync_lock = asyncio.Lock()  # never run two syncs at once in this process


class CryptoSyncError(Exception):
    pass


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_row(coin: dict, fetched_at: datetime) -> dict:
    return {
        "fetched_at": fetched_at,
        "coin_id": coin["id"],
        "symbol": (coin.get("symbol") or "").upper(),
        "name": coin.get("name") or "",
        "image": coin.get("image"),
        "current_price": coin.get("current_price"),
        "market_cap": coin.get("market_cap"),
        "market_cap_rank": coin.get("market_cap_rank"),
        "fully_diluted_valuation": coin.get("fully_diluted_valuation"),
        "total_volume": coin.get("total_volume"),
        "high_24h": coin.get("high_24h"),
        "low_24h": coin.get("low_24h"),
        "price_change_24h": coin.get("price_change_24h"),
        "price_change_percentage_24h": coin.get("price_change_percentage_24h"),
        "market_cap_change_24h": coin.get("market_cap_change_24h"),
        "market_cap_change_percentage_24h": coin.get("market_cap_change_percentage_24h"),
        "circulating_supply": coin.get("circulating_supply"),
        "total_supply": coin.get("total_supply"),
        "max_supply": coin.get("max_supply"),
        "ath": coin.get("ath"),
        "ath_change_percentage": coin.get("ath_change_percentage"),
        "ath_date": _parse_dt(coin.get("ath_date")),
        "atl": coin.get("atl"),
        "atl_change_percentage": coin.get("atl_change_percentage"),
        "atl_date": _parse_dt(coin.get("atl_date")),
        "source_last_updated": _parse_dt(coin.get("last_updated")),
    }


async def _fetch_page(client: httpx.AsyncClient, page: int) -> list[dict]:
    params = {
        "vs_currency": settings.vs_currency,
        "order": "market_cap_desc",
        "per_page": settings.sync_per_page,
        "page": page,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    for attempt in range(settings.sync_rate_limit_retries + 1):
        response = await client.get(settings.coingecko_url, params=params)
        if response.status_code == 429 and attempt < settings.sync_rate_limit_retries:
            logger.warning("CoinGecko rate limit on page %d, waiting before retry", page)
            await asyncio.sleep(settings.sync_rate_limit_wait_seconds)
            continue
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected CoinGecko response shape")
        return data
    raise CryptoSyncError("unreachable")  # pragma: no cover


async def sync_all_crypto(client: httpx.AsyncClient) -> int:
    """Fetch every configured page, then append them all in ONE commit.
    If any page fails nothing is written, so a "latest snapshot" is never half-complete."""
    async with _sync_lock:
        fetched_at = datetime.now(timezone.utc)
        rows: list[dict] = []
        try:
            for page in range(1, settings.sync_max_pages + 1):
                coins = await _fetch_page(client, page)
                rows.extend(_to_row(c, fetched_at) for c in coins)
                if len(coins) < settings.sync_per_page:
                    break  # last page reached
                if page < settings.sync_max_pages:
                    await asyncio.sleep(settings.sync_page_delay_seconds)
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise CryptoSyncError(f"CoinGecko sync failed: {e!r}") from e

        if not rows:
            raise CryptoSyncError("CoinGecko returned no coins")

        async with SessionLocal() as session:
            count = await crypto_repo.insert_snapshots(session, rows)
        logger.info("Crypto sync stored %d snapshot rows", count)
        return count


async def run_sync_scheduler(client: httpx.AsyncClient) -> None:
    """Runs forever: sync once at startup, then every `sync_interval_seconds`.
    Errors are logged and retried at the next tick; they never crash the server."""
    while True:
        try:
            await sync_all_crypto(client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Crypto sync failed; will retry in %ss", settings.sync_interval_seconds)
        await asyncio.sleep(settings.sync_interval_seconds)