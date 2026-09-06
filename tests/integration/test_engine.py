import pandas as pd
import pytest

from etf_lab.analytics.metrics import metrics
from etf_lab.backtest.engine import Backtester
from etf_lab.backtest.optimizer import chronological_split, optimize
from etf_lab.backtest.walkforward import windows
from etf_lab.config import LabConfig
from etf_lab.data.corporate_actions import CorporateAction
from etf_lab.data.fixtures import fixture
from etf_lab.data.fx import TableFXProvider
from etf_lab.instruments.registry import InstrumentRegistry


def test_determinism_and_no_same_close(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    engine = Backtester(config, registry)
    a, b = engine.run(bars), engine.run(bars)
    pd.testing.assert_frame_equal(a.curve, b.curve)
    pd.testing.assert_frame_equal(a.fills, b.fills)
    assert len(a.fills) > 0
    assert a.curve.cash.min() >= 0
    for fill in a.fills.itertuples():
        decisions = a.decisions[pd.to_datetime(a.decisions.timestamp) < fill.timestamp]
        assert len(decisions) > 0


def test_engine_future_mutation(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    cutoff = bars.timestamp.iloc[150]
    a = Backtester(config, registry).run(bars)
    changed = bars.copy()
    mask = changed.timestamp > cutoff
    changed.loc[mask, ["open", "close", "high", "low", "bid", "ask"]] *= 2
    changed.loc[mask, "volume"] *= 100
    b = Backtester(config, registry).run(changed)
    pd.testing.assert_frame_equal(
        a.curve[a.curve.timestamp <= cutoff], b.curve[b.curve.timestamp <= cutoff]
    )
    pd.testing.assert_frame_equal(
        a.decisions[pd.to_datetime(a.decisions.timestamp) <= cutoff],
        b.decisions[pd.to_datetime(b.decisions.timestamp) <= cutoff],
    )


def test_stops_and_take_profit(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    config.strategy.take_profit_atr_multiple = 0.1
    a = Backtester(config, registry).run(bars)
    assert "close-observed take profit" in a.fills.reason.tolist()
    config.strategy.take_profit_atr_multiple = 0
    config.strategy.stop_atr_multiple = 0.01
    b = Backtester(config, registry).run(bars)
    assert "close-observed stop" in b.fills.reason.tolist()


def test_benchmark_metrics(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    a = Backtester(config, registry).run(bars)
    m = metrics(a, a)
    assert m["total_return"] == m["benchmark_return"]
    assert m["Sharpe"] is None and m["CAGR"] is None
    assert m["total_return"] > 0
    assert m["max_drawdown"] <= 0


def test_splits_preserve_equity(
    bars: pd.DataFrame, config: LabConfig, registry: InstrumentRegistry
) -> None:
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    original = Backtester(config, registry).run(bars)
    split_ts = bars.bar_start.iloc[150]
    split = bars.copy()
    split.loc[150:, ["open", "high", "low", "close", "bid", "ask"]] /= 2
    action = CorporateAction(bars.instrument_id.iloc[0], split_ts, split_ts, "split", 2)
    adjusted = Backtester(config, registry).run(split, [action])
    assert adjusted.portfolio.equity == pytest.approx(original.portfolio.equity)
    with pytest.raises(ValueError, match="Late-known"):
        CorporateAction(action.instrument_id, split_ts, split_ts + pd.Timedelta(days=1), "split", 2)


def test_chronological_and_walkforward() -> None:
    data = fixture(start="2022-01-03", end="2024-12-31", timeframe="1d")
    train, validation, test = chronological_split(data)
    assert train.timestamp.max() < validation.timestamp.min() < test.timestamp.min()
    folds = windows(data)
    assert len(folds) >= 3
    for train, test in folds:
        assert train.timestamp.max() < test.timestamp.min()
    for prev, nxt in zip(folds, folds[1:], strict=False):
        assert prev[1].timestamp.max() < nxt[1].timestamp.min()
    with pytest.raises(ValueError):
        windows(data, 12, 3, 1)


def test_test_isolation(config: LabConfig, registry: InstrumentRegistry) -> None:
    data = fixture(start="2023-01-02", end="2023-06-30", timeframe="1d")
    config.strategy.timeframe = "1d"
    config.strategy.end_of_day_exit = False
    a = optimize(data, config, registry, TableFXProvider(), grid={"lookback": [4, 6]})
    _, _, test = chronological_split(data)
    changed = data.copy()
    changed.loc[test.index, ["open", "high", "low", "close", "bid", "ask"]] *= 10
    b = optimize(changed, config, registry, TableFXProvider(), grid={"lookback": [4, 6]})
    assert a.config == b.config and a.trials == b.trials
    assert a.final_test is None
