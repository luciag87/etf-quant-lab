import numpy as np
import pandas as pd

from etf_lab.config import StrategyConfig


def features(frame: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """Causal transforms; rolling extrema/volume reference exclude the decision bar."""
    result = []
    for _, g in frame.groupby("instrument_id", sort=False):
        g = g.sort_values("timestamp").copy()
        close, n = g.close, cfg.lookback
        g["returns"] = close.pct_change()
        g["log_returns"] = np.log(close / close.shift())
        g["momentum"] = close.pct_change(n)
        g["sma"] = close.rolling(n).mean()
        g["ema"] = close.ewm(span=n, adjust=False, min_periods=n).mean()
        typical = (g.high + g.low + close) / 3
        g["vwap"] = (typical * g.volume).groupby(g.session).cumsum() / (
            g.volume.groupby(g.session).cumsum().replace(0, np.nan)
        )
        tr = pd.concat(
            [g.high - g.low, (g.high - close.shift()).abs(), (g.low - close.shift()).abs()], axis=1
        ).max(axis=1)
        g["atr"] = tr.rolling(cfg.atr_period).mean()
        g["volatility"] = g.returns.rolling(n).std(ddof=1)
        g["std"] = close.rolling(n).std(ddof=1)
        g["average_volume"] = g.volume.shift().rolling(n).mean()
        g["volume_ratio"] = g.volume / g.average_volume.replace(0, np.nan)
        g["previous_high"] = g.high.shift().rolling(n).max()
        g["previous_low"] = g.low.shift().rolling(n).min()
        g["distance_from_vwap"] = close / g.vwap - 1
        g["zscore"] = (close - g.sma) / g["std"].replace(0, np.nan)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = -delta.clip(upper=0).rolling(n).mean()
        g["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        g.loc[(loss == 0) & (gain > 0), "rsi"] = 100
        g.loc[(loss == 0) & (gain == 0), "rsi"] = 50
        opens = g.groupby("session", sort=False).open.first()
        previous_close = g.groupby("session", sort=False).close.last().shift()
        g["gap"] = g.session.map(opens / previous_close - 1)
        g["intraday_return"] = close / g.session.map(opens) - 1
        # Explicitly missing unless a caller supplies aligned benchmark momentum.
        g["relative_strength"] = np.nan
        g["regime"] = np.where(
            g.volatility > cfg.volatility_max,
            "HIGH_VOL",
            np.where(g.volatility < cfg.volatility_min, "LOW_VOL", "NORMAL_VOL"),
        )
        g["trend_regime"] = np.where(g.momentum.abs() > 2 * g.volatility, "TRENDING", "RANGING")
        g["minutes_after_open"] = (g.timestamp - g.session_open).dt.total_seconds() / 60
        g["minutes_before_close"] = (g.session_close - g.timestamp).dt.total_seconds() / 60
        result.append(g)
    return pd.concat(result).sort_values(["timestamp", "instrument_id"]).reset_index(drop=True)


class HistoryView:
    """Only a defensive copy of completed rows is exposed to a strategy."""

    def __init__(self, frame: pd.DataFrame, as_of: pd.Timestamp) -> None:
        self._frame = frame.loc[frame.timestamp <= as_of].copy(deep=True)

    def frame(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)
