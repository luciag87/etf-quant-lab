"""Validated, explicit identities and immutable decision messages."""

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str
    name: str
    isin: str = Field(alias="ISIN")
    exchange: str
    mic: str = Field(min_length=4, max_length=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    country: str
    listing_timezone: str
    figi: str | None = None
    asset_class: str = "equity"
    sector: str = "broad"
    fund_domicile: str | None = None
    ucits: bool = False
    distribution_policy: str | None = None
    ter: float | None = Field(default=None, ge=0)
    benchmark: str | None = None
    inception_date: date
    listing_date: date
    delisting_date: date | None = None
    known_from: date
    researchable: bool = True
    potentially_tradeable: Literal["unknown", "externally_verified"] = "unknown"
    eligibility_evidence: str | None = None
    leveraged: bool = False
    inverse: bool = False
    aum: float | None = None
    source: str

    @field_validator("isin")
    @classmethod
    def valid_isin(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
            raise ValueError("Invalid ISIN format")
        digits = "".join(str(int(c, 36)) for c in value)
        total = 0
        for i, digit in enumerate(reversed(digits)):
            n = int(digit) * (2 if i % 2 else 1)
            total += n // 10 + n % 10
        if total % 10:
            raise ValueError("Invalid ISIN checksum")
        return value

    @model_validator(mode="after")
    def eligibility(self) -> "Instrument":
        if self.potentially_tradeable == "externally_verified" and not self.eligibility_evidence:
            raise ValueError("Explicit external eligibility evidence required")
        return self

    @property
    def id(self) -> str:
        # Currency disambiguates multi-currency trading lines on the same MIC.
        return f"{self.isin}:{self.mic}:{self.currency}"

    def active(self, day: date) -> bool:
        return max(self.inception_date, self.listing_date, self.known_from) <= day and (
            self.delisting_date is None or day <= self.delisting_date
        )


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)
    instrument_id: str
    timestamp: datetime
    action: Literal["LONG", "EXIT", "HOLD"]
    reason: str
    stop_distance: float = 0.0


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True)
    instrument_id: str
    side: Side
    quantity: int = Field(gt=0)
    created_at: datetime
    reason: str
    stop_distance: float = Field(default=0, ge=0)


class Fill(BaseModel):
    instrument_id: str
    side: Side
    quantity: int
    timestamp: datetime
    price: float
    fx_rate: float
    commission: float
    fx_cost: float
    spread_cost: float
    slippage_cost: float
    reason: str
