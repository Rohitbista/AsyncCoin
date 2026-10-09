from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CoinSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    coin_id: str
    symbol: str
    name: str
    image: str | None = None
    current_price: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    fully_diluted_valuation: float | None = None
    total_volume: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    price_change_24h: float | None = None
    price_change_percentage_24h: float | None = None
    market_cap_change_24h: float | None = None
    market_cap_change_percentage_24h: float | None = None
    circulating_supply: float | None = None
    total_supply: float | None = None
    max_supply: float | None = None
    ath: float | None = None
    ath_change_percentage: float | None = None
    ath_date: datetime | None = None
    atl: float | None = None
    atl_change_percentage: float | None = None
    atl_date: datetime | None = None
    fetched_at: datetime


class CoinListResponse(BaseModel):
    last_synced: datetime | None
    total: int
    limit: int
    offset: int
    data: list[CoinSnapshotOut]


class CoinListShortResponse(BaseModel):
    last_synced: datetime | None
    data: list[CoinSnapshotOut]


class CoinHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fetched_at: datetime
    current_price: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    total_volume: float | None = None
    price_change_percentage_24h: float | None = None


class CoinHistoryResponse(BaseModel):
    coin_id: str
    count: int
    data: list[CoinHistoryPoint]