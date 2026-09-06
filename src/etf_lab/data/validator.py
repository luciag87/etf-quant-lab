from typing import Any

import numpy as np
import pandas as pd

from etf_lab.config import Timeframe
from etf_lab.data.calendars import expected_bars
from etf_lab.instruments.registry import InstrumentRegistry


def validate(
    frame: pd.DataFrame, registry: InstrumentRegistry, timeframe: Timeframe
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = frame.copy()
    required = {"timestamp", "open", "high", "low", "close", "volume", "instrument_id"}
    if missing := required - set(df):
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("Empty dataset")
    parsed = [pd.Timestamp(t) for t in df.timestamp]
    if any(pd.isna(t) or t.tzinfo is None for t in parsed):
        raise ValueError("Timezone ambiguity: timestamp must include UTC offset")
    df["timestamp"] = pd.to_datetime(df.timestamp, utc=True, format="mixed")
    if df.duplicated(["instrument_id", "timestamp"]).any():
        raise ValueError("Duplicate bars")
    for _, group in df.groupby("instrument_id"):
        if not group.timestamp.is_monotonic_increasing:
            raise ValueError("Out-of-order bars")
    columns = ["open", "high", "low", "close", "volume"]
    df[columns] = df[columns].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(df[columns].to_numpy()).all():
        raise ValueError("Non-finite OHLCV")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df.volume < 0).any():
        raise ValueError("Non-positive price or negative volume")
    if (
        (df.high < df[["open", "close", "low"]].max(axis=1))
        | (df.low > df[["open", "close", "high"]].min(axis=1))
    ).any():
        raise ValueError("Impossible OHLC")
    if ("bid" in df) != ("ask" in df):
        raise ValueError("Both bid and ask are required")
    if "bid" in df:
        if (
            not np.isfinite(df[["bid", "ask"]].to_numpy()).all()
            or ((df.bid <= 0) | (df.ask < df.bid)).any()
        ):
            raise ValueError("Invalid quote")
    pieces, missing_count, expected_count = [], 0, 0
    for iid, group in df.groupby("instrument_id", sort=True):
        if iid not in registry.items:
            raise ValueError(f"Unregistered identity: {iid}")
        instrument = registry.items[str(iid)]
        local = group.timestamp.dt.tz_convert(instrument.listing_timezone)
        if not all(instrument.active(d) for d in local.dt.date):
            raise ValueError("Instrument not yet known/listed or already delisted")
        grid = expected_bars(
            instrument.mic, str(local.min().date()), str(local.max().date()), timeframe
        )
        if not group.timestamp.isin(grid.timestamp).all():
            raise ValueError("Off-calendar or incorrectly labelled bar close")
        expected_count += len(grid)
        missing_count += len(grid) - len(group)
        extra = [c for c in grid if c != "timestamp" and c in group]
        pieces.append(group.drop(columns=extra).merge(grid, on="timestamp", validate="one_to_one"))
    clean = pd.concat(pieces).sort_values(["timestamp", "instrument_id"]).reset_index(drop=True)
    outliers = int(clean.groupby("instrument_id").close.pct_change().abs().gt(0.2).sum())
    report = {
        "status": "WARN" if missing_count or outliers else "PASS",
        "rows": len(clean),
        "start": str(clean.timestamp.min()),
        "end": str(clean.timestamp.max()),
        "coverage": len(clean) / expected_count,
        "missing_intervals": missing_count,
        "duplicates": 0,
        "timezone": "UTC",
        "outliers": outliers,
        "symbols": sorted(clean.instrument_id.unique().tolist()),
        "currencies": sorted({registry.items[i].currency for i in clean.instrument_id}),
        "corporate_actions": "separate event file; absence is not proof of no actions",
    }
    return clean, report
