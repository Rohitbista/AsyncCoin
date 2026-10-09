from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .crypto_schemas import CoinSnapshotOut


# ----------------------------- requests -----------------------------


class WatchlistAddRequest(BaseModel):
    coin_ids: list[str] = Field(min_length=1, max_length=50, description='CoinGecko ids, e.g. ["bitcoin", "ethereum"]')

    @field_validator("coin_ids")
    @classmethod
    def normalize(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip().lower() for c in v if c and c.strip()]
        if not cleaned:
            raise ValueError("coin_ids must contain at least one non-empty id")
        if any(len(c) > 128 for c in cleaned):
            raise ValueError("coin id too long")
        return list(dict.fromkeys(cleaned))  # de-duplicate, keep order


class WatchlistUpdateRequest(BaseModel):
    """Partial update. Send only the fields you want to change; send null to clear one."""

    note: str | None = Field(None, max_length=500)
    alert_above: float | None = Field(None, gt=0)
    alert_below: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def check_alert_range(self):
        if self.alert_above is not None and self.alert_below is not None and self.alert_below >= self.alert_above:
            raise ValueError("alert_below must be lower than alert_above")
        return self


# ----------------------------- responses -----------------------------


class WatchlistAddResponse(BaseModel):
    added: list[str]
    already_tracked: list[str]
    not_found: list[str]
    tracked_count: int


class WatchlistItemOut(BaseModel):
    coin_id: str
    added_at: datetime
    note: str | None = None
    alert_above: float | None = None
    alert_below: float | None = None
    # Which alert (if any) the latest price currently satisfies.
    alert_status: Literal["above", "below"] | None = None
    # Latest market data; None if the coin is no longer present in the synced data.
    coin: CoinSnapshotOut | None = None


class WatchlistResponse(BaseModel):
    last_synced: datetime | None
    count: int
    data: list[WatchlistItemOut]


class CoinPerformance(BaseModel):
    coin_id: str
    name: str
    symbol: str
    current_price: float | None = None
    change_24h_pct: float | None = None
    # Computed from our own saved snapshots; None until enough history exists.
    change_7d_pct: float | None = None
    change_30d_pct: float | None = None


class WatchlistSummaryResponse(BaseModel):
    last_synced: datetime | None
    tracked_count: int
    total_market_cap: float | None
    best_24h: CoinPerformance | None
    worst_24h: CoinPerformance | None
    performance: list[CoinPerformance]


class WatchlistAlertsResponse(BaseModel):
    last_synced: datetime | None
    count: int
    data: list[WatchlistItemOut]