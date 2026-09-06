import numpy as np
import pandas as pd
import pytest

from etf_lab.analytics.metrics import metrics
from etf_lab.analytics.research import session_analysis
from etf_lab.analytics.statistics import block_bootstrap
from etf_lab.backtest.engine import BacktestResult
from etf_lab.portfolio.portfolio import Portfolio


def test_ratios_drawdown() -> None:
    returns = np.tile([0.01, -0.005, 0.002, -0.003], 20)
    equity = np.r_[10000, 10000 * np.cumprod(1 + returns)]
    curve = pd.DataFrame(
        {
            "timestamp": pd.bdate_range("2024-01-01", periods=len(equity), tz="UTC"),
            "equity": equity,
            "cash": np.zeros(len(equity)),
            "exposure": equity,
        }
    )
    result = BacktestResult(curve, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), Portfolio())
    m = metrics(result)
    assert m["Sharpe"] == pytest.approx(returns.mean() / returns.std(ddof=1) * np.sqrt(252))
    assert m["Sortino"] == pytest.approx(
        returns.mean() / np.sqrt(np.mean(np.minimum(returns, 0) ** 2)) * np.sqrt(252)
    )
    assert m["max_drawdown"] == pytest.approx((equity / np.maximum.accumulate(equity) - 1).min())
    ci = block_bootstrap(pd.Series(returns))
    assert ci == block_bootstrap(pd.Series(returns))
    assert block_bootstrap(pd.Series([0.01])) is None


def test_gap_time_separation(bars: pd.DataFrame) -> None:
    times, sessions = session_analysis(bars)
    assert times.observations.sum() == len(bars)
    assert pd.isna(sessions.gap.iloc[0])
    assert sessions.gap.iloc[1] == pytest.approx(sessions.open.iloc[1] / sessions.close.iloc[0] - 1)
