import numpy as np
import pandas as pd


def block_bootstrap(
    values: pd.Series, seed: int = 42, samples: int = 1000, block: int = 5
) -> dict[str, float | str] | None:
    x = values.dropna().to_numpy(dtype=float)
    if len(x) < max(30, 2 * block):
        return None
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(samples):
        starts = rng.integers(0, len(x), size=int(np.ceil(len(x) / block)))
        indices = np.concatenate([(s + np.arange(block)) % len(x) for s in starts])[: len(x)]
        means.append(float(x[indices].mean()))
    return {
        "mean_daily_return_low": float(np.quantile(means, 0.025)),
        "mean_daily_return_high": float(np.quantile(means, 0.975)),
        "method": (
            f"circular block bootstrap, block={block}, seed={seed}; not multiple-test corrected"
        ),
    }


def diversification(returns: pd.DataFrame, window: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    return returns.corr(), returns.rolling(window).corr()
