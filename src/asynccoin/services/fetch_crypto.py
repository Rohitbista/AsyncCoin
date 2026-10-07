import asyncio
import logging
import time

import httpx

from asynccoin.config.settings import settings
from asynccoin.app.models import Coin, CryptoResponse

_CTX = "asynccoin/services/fetch_crypto"
logger = logging.getLogger(__name__)


class CryptoFetchError(Exception):
    """Raised when data can't be fetched and there is no cache to fall back on."""


# Shared in-memory cache (one per process).
CACHE: dict = {"data": [], "last_updated": 0.0}
_lock = asyncio.Lock()


def _format(raw_data: list[dict]) -> list[Coin]:
    return [
        Coin(
            id=coin["id"],
            name=coin.get("name", ""),
            symbol=(coin.get("symbol") or "").upper(),
            current_price=coin.get("current_price"),
            price_change_percentage_24h=coin.get("price_change_percentage_24h"),
            image=coin.get("image"),
        )
        for coin in raw_data
    ]


async def fetch_top_5_crypto(client: httpx.AsyncClient) -> CryptoResponse:
    # The lock stops many simultaneous requests from all hitting CoinGecko
    # when the cache expires (CoinGecko's free tier rate-limits aggressively).
    async with _lock:
        now = time.time()

        if CACHE["data"] and now - CACHE["last_updated"] < settings.cache_ttl_seconds:
            return CryptoResponse(source="cache", last_updated=CACHE["last_updated"], data=CACHE["data"])

        params = {
            "vs_currency": settings.vs_currency,
            "ids": settings.coin_ids,
            "order": "market_cap_desc",
            "price_change_percentage": "24h",
        }

        try:
            # CoinGecko's public endpoint: no API key needed.
            response = await client.get(settings.coingecko_url, params=params)
            response.raise_for_status()
            data = _format(response.json())
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning("%s: CoinGecko fetch failed: %r", _CTX, e)
            if CACHE["data"]:
                # Better to show slightly old prices than an error.
                return CryptoResponse(
                    source="stale_cache", last_updated=CACHE["last_updated"], data=CACHE["data"]
                )
            raise CryptoFetchError("Could not fetch crypto data from CoinGecko") from e

        CACHE["data"] = data
        CACHE["last_updated"] = now
        return CryptoResponse(source="live_api", last_updated=now, data=data)