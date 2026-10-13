from typing import Literal

from pydantic import BaseModel


class Coin(BaseModel):
    id: str
    name: str
    symbol: str
    current_price: float | None = None
    price_change_percentage_24h: float | None = None
    image: str | None = None


class CryptoResponse(BaseModel):
    # "live_api" = freshly fetched, "cache" = served from cache,
    # "stale_cache" = API failed so we returned the last known data.
    source: Literal["live_api", "cache", "stale_cache"]
    last_updated: float | None = None  # unix timestamp of the data
    data: list[Coin]