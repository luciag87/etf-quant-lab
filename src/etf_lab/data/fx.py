from typing import Protocol

import numpy as np
import pandas as pd


class FXProvider(Protocol):
    def rate(self, currency: str, base: str, timestamp: pd.Timestamp) -> float: ...


class TableFXProvider:
    """Rows: timestamp (availability time), currency, base, rate (base per local unit)."""

    def __init__(self, frame: pd.DataFrame | None = None, max_age_hours: float = 96) -> None:
        self.frame = frame.copy() if frame is not None else pd.DataFrame()
        self.max_age = pd.Timedelta(hours=max_age_hours)
        if not self.frame.empty:
            if any(pd.Timestamp(t).tzinfo is None for t in self.frame.timestamp):
                raise ValueError("FX timestamps require timezone")
            self.frame["timestamp"] = pd.to_datetime(self.frame.timestamp, utc=True, format="mixed")
            if (self.frame.rate <= 0).any() or not np.isfinite(self.frame.rate).all():
                raise ValueError("Invalid FX rate")
            if self.frame.duplicated(["timestamp", "currency", "base"]).any():
                raise ValueError("Duplicate FX observations")
            self.frame = self.frame.sort_values("timestamp")

    def rate(self, currency: str, base: str, timestamp: pd.Timestamp) -> float:
        if currency == base:
            return 1.0
        if self.frame.empty:
            raise ValueError(f"Missing FX {currency}/{base}")
        valid = self.frame[
            (self.frame.currency == currency)
            & (self.frame.base == base)
            & (self.frame.timestamp <= timestamp)
        ]
        if valid.empty or timestamp - valid.iloc[-1].timestamp > self.max_age:
            raise ValueError(f"Missing/stale as-of FX {currency}/{base} at {timestamp}")
        return float(valid.iloc[-1].rate)


def return_attribution(asset_return: float, fx_return: float) -> dict[str, float]:
    return {
        "local_currency_return": asset_return,
        "FX_return": fx_return,
        "interaction": asset_return * fx_return,
        "base_currency_return": (1 + asset_return) * (1 + fx_return) - 1,
    }
