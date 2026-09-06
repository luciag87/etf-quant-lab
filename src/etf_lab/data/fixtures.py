from pathlib import Path

import numpy as np
import pandas as pd

from etf_lab.data.calendars import expected_bars

KINDS = [
    "trending_up",
    "trending_down",
    "sideways",
    "high_vol",
    "gap_up",
    "gap_down",
    "low_volume",
    "wide_spread",
]


def fixture(
    kind: str = "trending_up",
    start: str = "2024-01-02",
    end: str = "2024-01-12",
    timeframe: str = "5m",
) -> pd.DataFrame:
    if kind not in KINDS:
        raise ValueError("Unknown fixture")
    grid = expected_bars("XETR", start, end, timeframe)  # type: ignore[arg-type]
    rng = np.random.default_rng(42)
    n = len(grid)
    drift = {"trending_up": 0.00035, "trending_down": -0.00035}.get(kind, 0)
    noise = 0.005 if kind == "high_vol" else 0.0008
    returns = drift + rng.normal(0, noise, n)
    close = 100 * np.exp(np.cumsum(returns))
    op = np.r_[100, close[:-1]]
    if kind in {"gap_up", "gap_down"}:
        first = grid.session != grid.session.shift()
        factors = np.cumprod(np.where(first, 1.01 if kind == "gap_up" else 0.99, 1))
        close *= factors
        op *= factors
    grid["open"], grid["close"] = op, close
    grid["high"] = np.maximum(op, close) * 1.0003
    grid["low"] = np.minimum(op, close) * 0.9997
    grid["volume"] = rng.integers(10000, 30000, n) if kind != "low_volume" else np.ones(n)
    spread = 0.01 if kind == "wide_spread" else 0.0004
    grid["bid"], grid["ask"] = close * (1 - spread / 2), close * (1 + spread / 2)
    grid["instrument_id"] = "ZZ0000000008:XETR:EUR"
    grid["symbol"] = "DEMO"
    return grid


def generate(root: Path) -> None:
    target = root / "tests/fixtures"
    target.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        fixture(kind).to_parquet(target / f"{kind}.parquet", index=False)
    sample = fixture()
    (root / "data").mkdir(exist_ok=True)
    sample.to_csv(root / "data/sample.csv", index=False)
    fixture(start="2023-01-02", end="2024-12-31", timeframe="1d").to_parquet(
        root / "data/sample_daily.parquet", index=False
    )
