import numpy as np
import pandas as pd
import pytest

from etf_lab.config import LabConfig
from etf_lab.features.pipeline import HistoryView, features
from etf_lab.strategies.base import ConfiguredStrategy


def test_feature_values(bars: pd.DataFrame, config: LabConfig) -> None:
    f = features(bars, config.strategy)
    assert f.returns.iloc[1] == pytest.approx(bars.close.iloc[1] / bars.close.iloc[0] - 1)
    assert f.momentum.iloc[6] == pytest.approx(bars.close.iloc[6] / bars.close.iloc[0] - 1)
    typical = (bars.high + bars.low + bars.close) / 3
    assert f.vwap.iloc[5] == pytest.approx(
        (typical[:6] * bars.volume[:6]).sum() / bars.volume[:6].sum()
    )
    assert f.volume_ratio.iloc[6] == pytest.approx(bars.volume.iloc[6] / bars.volume[:6].mean())
    assert f.previous_high.iloc[6] == bars.high.iloc[:6].max()
    assert f.volatility.iloc[7] == pytest.approx(f.returns.iloc[2:8].std())
    tr = pd.concat(
        [
            bars.high - bars.low,
            (bars.high - bars.close.shift()).abs(),
            (bars.low - bars.close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    assert f.atr.iloc[13] == pytest.approx(tr.iloc[:14].mean())


@pytest.mark.parametrize("column", ["close", "high", "low", "volume"])
def test_future_features(bars: pd.DataFrame, config: LabConfig, column: str) -> None:
    original = features(bars, config.strategy)
    changed = bars.copy()
    changed.loc[100:, column] *= 20
    pd.testing.assert_frame_equal(
        original.iloc[:100], features(changed, config.strategy).iloc[:100]
    )
    pd.testing.assert_frame_equal(original.iloc[:100], features(bars.iloc[:100], config.strategy))


def test_view_and_signals(bars: pd.DataFrame, config: LabConfig) -> None:
    view = HistoryView(bars, bars.timestamp.iloc[10])
    assert len(view.frame()) == 11
    modified = view.frame()
    modified.loc[0, "close"] = -1
    assert view.frame().close.iloc[0] > 0
    row = features(bars, config.strategy).iloc[40].copy()
    row["momentum"], row["volume_ratio"], row["volatility"] = 0.1, 2, 0.01
    row["close"], row["vwap"] = 110, 100
    assert ConfiguredStrategy(config.strategy).decide(row, False).action == "LONG"
    row["volatility"] = np.nan
    assert ConfiguredStrategy(config.strategy).decide(row, False).action == "HOLD"
