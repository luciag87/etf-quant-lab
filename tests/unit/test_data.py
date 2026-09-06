from datetime import date

import numpy as np
import pandas as pd
import pytest

from etf_lab.data.calendars import expected_bars, schedule
from etf_lab.data.fx import TableFXProvider, return_attribution
from etf_lab.data.validator import validate
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.models import Instrument


def test_identity(registry: InstrumentRegistry) -> None:
    i = registry.resolve("CSPX")
    assert i.id == "IE00B5BMR087:XLON:USD"
    assert i.potentially_tradeable == "unknown"
    assert not i.active(date(2024, 1, 1))  # today's metadata isn't historical membership
    other = i.model_copy(update={"currency": "GBP"})
    both = InstrumentRegistry([i, other])
    with pytest.raises(ValueError, match="ambiguous"):
        both.resolve("CSPX")
    assert both.resolve(i.isin, "XLON", "GBP") == other


def test_isin_and_external_evidence(registry: InstrumentRegistry) -> None:
    data = registry.resolve("CSPX").model_dump(by_alias=True)
    data["ISIN"] = "IE00B5BMR088"
    with pytest.raises(ValueError, match="checksum"):
        Instrument.model_validate(data)
    data["ISIN"] = "IE00B5BMR087"
    data["potentially_tradeable"] = "externally_verified"
    with pytest.raises(ValueError, match="evidence"):
        Instrument.model_validate(data)


@pytest.mark.parametrize("mic", ["XNYS", "XNAS", "XLON", "XETR", "XAMS", "XPAR"])
def test_calendars(mic: str) -> None:
    assert len(schedule(mic, "2024-01-02", "2024-01-05")) == 4


def test_half_day_holiday_dst() -> None:
    assert len(expected_bars("XNYS", "2024-11-29", "2024-11-29", "5m")) == 42
    s = schedule("XNYS", "2024-03-08", "2024-04-02")
    assert s.loc["2024-03-08", "open"].hour == 14
    assert s.loc["2024-03-11", "open"].hour == 13
    assert s.loc["2024-03-11", "open"].tz_convert("Europe/Madrid").hour == 14
    assert s.loc["2024-04-02", "open"].tz_convert("Europe/Madrid").hour == 15
    assert "2024-03-29" not in s.index.strftime("%Y-%m-%d")


@pytest.mark.parametrize(
    "timeframe,count", [("1m", 390), ("5m", 78), ("15m", 26), ("30m", 13), ("1h", 7), ("1d", 1)]
)
def test_resolutions(timeframe: str, count: int) -> None:
    grid = expected_bars("XNYS", "2024-01-02", "2024-01-02", timeframe)  # type: ignore[arg-type]
    assert len(grid) == count
    assert grid.timestamp.iloc[-1] == grid.session_close.iloc[-1]


@pytest.mark.parametrize(
    "defect", ["duplicate", "order", "zero", "negative", "ohlc", "tz", "nan", "quote"]
)
def test_invalid_bars(bars: pd.DataFrame, registry: InstrumentRegistry, defect: str) -> None:
    bad = bars.copy()
    if defect == "duplicate":
        bad = pd.concat([bad, bad.iloc[:1]])
    elif defect == "order":
        bad = bad.iloc[::-1]
    elif defect in {"zero", "negative", "nan"}:
        bad.loc[0, "close"] = {"zero": 0, "negative": -1, "nan": np.nan}[defect]
    elif defect == "ohlc":
        bad.loc[0, "high"] = 1
    elif defect == "tz":
        bad["timestamp"] = bad.timestamp.dt.tz_localize(None)
    elif defect == "quote":
        bad.loc[0, "ask"] = 0.01
    with pytest.raises(ValueError):
        validate(bad, registry, "5m")


def test_missing_and_existence(bars: pd.DataFrame, registry: InstrumentRegistry) -> None:
    _, report = validate(bars.drop(index=20), registry, "5m")
    assert report["missing_intervals"] == 1 and report["status"] == "WARN"
    i = registry.resolve("DEMO").model_copy(update={"inception_date": date(2025, 1, 1)})
    with pytest.raises(ValueError, match="not yet"):
        validate(bars, InstrumentRegistry([i]), "5m")


def test_fx_asof() -> None:
    fx = TableFXProvider(
        pd.DataFrame(
            {
                "timestamp": ["2024-01-02T10:00Z", "2024-01-03T10:00Z"],
                "currency": ["USD"] * 2,
                "base": ["EUR"] * 2,
                "rate": [0.9, 0.95],
            }
        )
    )
    assert fx.rate("USD", "EUR", pd.Timestamp("2024-01-02T11:00Z")) == 0.9
    with pytest.raises(ValueError, match="as-of"):
        fx.rate("USD", "EUR", pd.Timestamp("2024-01-02T09:00Z"))
    with pytest.raises(ValueError, match="stale"):
        fx.rate("USD", "EUR", pd.Timestamp("2024-02-02T09:00Z"))
    assert return_attribution(0.05, -0.03)["base_currency_return"] == pytest.approx(0.0185)
