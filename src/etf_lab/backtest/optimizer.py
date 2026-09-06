from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from etf_lab.analytics.metrics import metrics
from etf_lab.backtest.engine import Backtester
from etf_lab.config import LabConfig
from etf_lab.data.fx import FXProvider
from etf_lab.instruments.registry import InstrumentRegistry


def chronological_split(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sessions = sorted(data.session.unique())
    if len(sessions) < 10:
        raise ValueError("At least 10 sessions required for train/validation/test")
    a, b = int(len(sessions) * 0.6), int(len(sessions) * 0.8)
    return tuple(
        data[data.session.isin(s)].copy() for s in [sessions[:a], sessions[a:b], sessions[b:]]
    )  # type: ignore[return-value]


@dataclass
class Optimization:
    config: LabConfig
    trials: list[dict[str, Any]]
    final_test: dict[str, Any] | None = None


def optimize(
    data: pd.DataFrame,
    config: LabConfig,
    registry: InstrumentRegistry,
    fx: FXProvider,
    grid: dict[str, list[Any]] | None = None,
    random_count: int | None = None,
    seed: int = 42,
    evaluate_test: bool = False,
) -> Optimization:
    train, validation, test = chronological_split(data)
    grid = grid or {"lookback": [4, 6, 12], "momentum_threshold": [0.001, 0.002]}
    combinations = list(product(*grid.values()))
    if len(combinations) > 100:
        raise ValueError("Grid exceeds 100 trials; reduce search to limit data snooping")
    if random_count is not None:
        if random_count < 1:
            raise ValueError("random_count must be positive")
        rng = np.random.default_rng(seed)
        combinations = [
            combinations[int(i)]
            for i in rng.choice(
                len(combinations), min(random_count, len(combinations)), replace=False
            )
        ]
    trials, candidates = [], []
    for values in combinations:
        params = dict(zip(grid, values, strict=True))
        payload = config.model_dump()
        payload["strategy"].update(params)
        candidate = LabConfig.model_validate(payload)
        train_metrics = metrics(Backtester(candidate, registry, fx).run(train))
        val_metrics = metrics(Backtester(candidate, registry, fx).run(validation))
        # Transparent heuristic, not an estimator of probability of future profitability.
        divergence = abs(train_metrics["total_return"] - val_metrics["total_return"])
        scarcity = 1 / (1 + val_metrics["number_of_trades"])
        score = val_metrics["total_return"] + val_metrics["max_drawdown"] - divergence - scarcity
        trials.append(
            {
                "parameters": params,
                "train": train_metrics,
                "validation": val_metrics,
                "stability": divergence,
                "score": score,
            }
        )
        candidates.append(candidate)
    best = max(range(len(trials)), key=lambda i: trials[i]["score"])
    outcome = Optimization(candidates[best], trials)
    if evaluate_test:
        outcome.final_test = metrics(Backtester(outcome.config, registry, fx).run(test))
    return outcome
