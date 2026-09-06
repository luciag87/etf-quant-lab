import pandas as pd
import pytest

from etf_lab.backtest.engine import Backtester
from etf_lab.config import LabConfig
from etf_lab.data.corporate_actions import CorporateAction
from etf_lab.data.fx import TableFXProvider
from etf_lab.instruments.registry import InstrumentRegistry


def test_future_split_does_not_change_past(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    ts = bars.bar_start.iloc[200]
    a = Backtester(config, registry).run(bars)
    changed = bars.copy()
    changed.loc[200:, ["open", "high", "low", "close", "bid", "ask"]] /= 2
    action = CorporateAction(bars.instrument_id.iloc[0], ts, ts, "split", 2)
    b = Backtester(config, registry).run(changed, [action])
    pd.testing.assert_frame_equal(
        a.curve[a.curve.timestamp <= ts], b.curve[b.curve.timestamp <= ts]
    )


def test_distribution_cash(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    a = Backtester(config, registry).run(bars)
    ts = bars.bar_start.iloc[200]
    action = CorporateAction(bars.instrument_id.iloc[0], ts, ts, "distribution", 1)
    b = Backtester(config, registry).run(bars, [action])
    quantity = next(iter(a.portfolio.positions.values())).quantity
    assert b.portfolio.cash - a.portfolio.cash == pytest.approx(quantity)


def test_future_fx_and_multi_cash(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    eur = registry.resolve("DEMO")
    usd = eur.model_copy(update={"currency": "USD", "symbol": "DEMO_USD"})
    both = InstrumentRegistry([eur, usd])
    foreign = bars.copy()
    foreign["instrument_id"] = usd.id
    data = pd.concat([bars, foreign]).sort_values(["timestamp", "instrument_id"])
    fx_data = pd.DataFrame(
        {
            "timestamp": ["2024-01-02T00:00Z", "2024-01-03T00:00Z"],
            "currency": ["USD"] * 2,
            "base": ["EUR"] * 2,
            "rate": [0.9, 0.95],
        }
    )
    a = Backtester(config, both, TableFXProvider(fx_data)).run(data)
    fx_data.loc[1, "rate"] = 1.2
    b = Backtester(config, both, TableFXProvider(fx_data)).run(data)
    cutoff = pd.Timestamp("2024-01-03T00:00Z")
    pd.testing.assert_frame_equal(
        a.curve[a.curve.timestamp < cutoff], b.curve[b.curve.timestamp < cutoff]
    )
    assert a.curve.cash.min() >= 0
    assert (a.curve.exposure <= a.curve.equity).all()


def test_leveraged_requires_optin(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    special = registry.resolve("DEMO").model_copy(update={"leveraged": True})
    with pytest.raises(ValueError, match="excluded"):
        Backtester(config, InstrumentRegistry([special])).run(bars)
