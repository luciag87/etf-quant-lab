from typing import Literal, Protocol

import pandas as pd

from etf_lab.config import StrategyConfig
from etf_lab.models import Signal


class Strategy(Protocol):
    config: StrategyConfig

    def decide(self, row: pd.Series, held: bool) -> Signal: ...


class ConfiguredStrategy:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def decide(self, row: pd.Series, held: bool) -> Signal:
        c = self.config
        action: Literal["LONG", "EXIT", "HOLD"] = "HOLD"
        reason = "filters"
        if c.name == "buy-and-hold":
            action, reason = ("HOLD", "held") if held else ("LONG", "baseline")
        elif held:
            if (
                (c.name == "momentum" and row.momentum < 0)
                or (c.name == "mean-reversion" and row.zscore >= 0)
                or (c.name == "breakout" and row.close < row.previous_low)
            ):
                action, reason = "EXIT", "signal reversal"
        elif pd.notna(row.atr) and pd.notna(row.volatility):
            valid = (
                row.volume_ratio >= c.volume_ratio_min
                and c.volatility_min <= row.volatility <= c.volatility_max
                and row.minutes_after_open >= c.entry_start_minutes_after_open
                and row.minutes_before_close >= c.entry_end_minutes_before_close
                and (not c.allowed_regimes or row.regime in c.allowed_regimes)
            )
            trigger = False
            if c.name == "momentum":
                trigger = row.momentum > c.momentum_threshold and (
                    not c.require_above_vwap or row.close > row.vwap
                )
            elif c.name == "breakout":
                trigger = row.close > row.previous_high * (1 + c.breakout_buffer_bps / 10000)
            elif c.name == "mean-reversion":
                trigger = (
                    row.zscore < c.zscore_entry
                    and row.rsi < c.rsi_max
                    and row.distance_from_vwap < 0
                    and row.trend_regime != "TRENDING"
                )
            if valid and trigger:
                action, reason = "LONG", c.name
        return Signal(
            instrument_id=row.instrument_id,
            timestamp=row.timestamp,
            action=action,
            reason=reason,
            stop_distance=float(row.atr * c.stop_atr_multiple) if pd.notna(row.atr) else 0,
        )


class IntradayMomentumStrategy(ConfiguredStrategy):
    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__((config or StrategyConfig()).model_copy(update={"name": "momentum"}))


class BuyAndHoldStrategy(ConfiguredStrategy):
    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__((config or StrategyConfig()).model_copy(update={"name": "buy-and-hold"}))


class BreakoutStrategy(ConfiguredStrategy):
    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__((config or StrategyConfig()).model_copy(update={"name": "breakout"}))


class MeanReversionStrategy(ConfiguredStrategy):
    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__((config or StrategyConfig()).model_copy(update={"name": "mean-reversion"}))
