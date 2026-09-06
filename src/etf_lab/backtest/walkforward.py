from typing import Any

import pandas as pd

from etf_lab.analytics.metrics import metrics
from etf_lab.backtest.engine import Backtester
from etf_lab.backtest.optimizer import optimize
from etf_lab.config import LabConfig
from etf_lab.data.fx import FXProvider
from etf_lab.instruments.registry import InstrumentRegistry


def windows(
    data: pd.DataFrame, train_months: int = 12, test_months: int = 3, step_months: int = 3
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    if min(train_months, test_months, step_months) < 1 or step_months < test_months:
        raise ValueError("Positive months and non-overlapping OOS windows required")
    day = pd.to_datetime(data.session)
    start, end = day.min(), day.max() + pd.Timedelta(days=1)
    folds = []
    while start + pd.DateOffset(months=train_months + test_months) <= end:
        cutoff = start + pd.DateOffset(months=train_months)
        stop = cutoff + pd.DateOffset(months=test_months)
        train, test = data[(day >= start) & (day < cutoff)], data[(day >= cutoff) & (day < stop)]
        if not train.empty and not test.empty:
            folds.append((train.copy(), test.copy()))
        start += pd.DateOffset(months=step_months)
    if not folds:
        raise ValueError("Insufficient history for requested walk-forward windows")
    return folds


def walkforward(
    data: pd.DataFrame,
    config: LabConfig,
    registry: InstrumentRegistry,
    fx: FXProvider,
    train_months: int = 12,
    test_months: int = 3,
    step_months: int = 3,
) -> dict[str, Any]:
    folds = []
    wealth = 1.0
    for train, test in windows(data, train_months, test_months, step_months):
        # Internal selection cannot access outer OOS data.
        selected = optimize(
            train,
            config,
            registry,
            fx,
            grid={"lookback": [config.strategy.lookback, config.strategy.lookback * 2]},
        )
        result = metrics(Backtester(selected.config, registry, fx).run(test))
        wealth *= 1 + result["total_return"]
        folds.append(
            {
                "train_start": str(train.timestamp.min()),
                "train_end": str(train.timestamp.max()),
                "test_start": str(test.timestamp.min()),
                "test_end": str(test.timestamp.max()),
                "parameters": selected.config.strategy.model_dump(),
                "out_of_sample": result,
            }
        )
    return {
        "folds": folds,
        "geometric_fold_return": wealth - 1,
        "method": (
            "Independent cash-reset folds, marked open positions; geometric summary "
            "is not an executable stitched portfolio"
        ),
    }
