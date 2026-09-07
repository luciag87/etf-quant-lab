from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

Timeframe = Literal["1d", "1h", "30m", "15m", "5m", "1m"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class StrategyConfig(StrictModel):
    name: Literal["momentum", "buy-and-hold", "breakout", "mean-reversion"] = "momentum"
    timeframe: Timeframe = "5m"
    lookback: int = Field(default=6, ge=2)
    atr_period: int = Field(default=14, ge=2)
    momentum_threshold: float = 0.002
    require_above_vwap: bool = True
    volume_ratio_min: float = Field(default=1.2, ge=0)
    volatility_min: float = Field(default=0, ge=0)
    volatility_max: float = Field(default=0.03, gt=0)
    entry_start_minutes_after_open: int = Field(default=30, ge=0)
    entry_end_minutes_before_close: int = Field(default=60, ge=0)
    stop_atr_multiple: float = Field(default=1.5, ge=0)
    take_profit_atr_multiple: float = Field(default=2.5, ge=0)
    trailing_atr_multiple: float = Field(default=0, ge=0)
    max_holding_bars: int = Field(default=60, ge=1)
    end_of_day_exit: bool = True
    breakout_buffer_bps: float = Field(default=2, ge=0)
    zscore_entry: float = -2
    rsi_max: float = Field(default=35, ge=0, le=100)
    allowed_regimes: list[str] = []


class RiskConfig(StrictModel):
    risk_timezone: str = "Europe/Madrid"

    @field_validator("risk_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Invalid risk timezone") from error
        return value

    starting_equity: float = Field(default=10000, gt=0)
    base_currency: str = "EUR"
    sizing: Literal["percentage", "fixed", "atr", "volatility"] = "atr"
    fixed_notional: float = Field(default=1000, gt=0)
    position_size_pct: float = Field(default=10, gt=0, le=100)
    risk_per_trade_pct: float = Field(default=0.5, gt=0, le=100)
    target_annual_vol: float = Field(default=0.10, gt=0)
    max_position_pct: float = Field(default=10, gt=0, le=100)
    max_sector_exposure_pct: float = Field(default=40, gt=0, le=100)
    max_total_exposure_pct: float = Field(default=100, gt=0, le=100)
    max_daily_loss_pct: float = Field(default=2, gt=0, le=100)
    max_drawdown_pct: float = Field(default=10, gt=0, le=100)
    max_open_positions: int = Field(default=5, ge=1)
    max_trades_per_day: int = Field(default=10, ge=1)
    cooldown_after_losses_bars: int = Field(default=6, ge=0)
    minimum_price: float = Field(default=1, gt=0)
    minimum_average_volume: float = Field(default=100, ge=0)
    maximum_spread_bps: float = Field(default=30, ge=0)


class ExecutionConfig(StrictModel):
    mode: Literal["ideal", "realistic", "pessimistic"] = "realistic"
    latency_ms: int = Field(default=250, ge=0)
    slippage_bps: float = Field(default=2, ge=0)
    spread_bps: float = Field(default=4, ge=0)
    impact_bps: float = Field(default=2, ge=0)
    commission_bps: float = Field(default=1, ge=0)
    minimum_commission: float = Field(default=1, ge=0)
    fx_cost_bps: float = Field(default=5, ge=0)
    max_volume_participation: float = Field(default=0.05, gt=0, le=1)


class LabConfig(StrictModel):
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    allow_special_products: bool = False
    currency_hedged: Literal[False] = False
    fx_max_age_hours: float = Field(default=96, gt=0)


def load_config(path: Path | None = None) -> LabConfig:
    return LabConfig.model_validate(yaml.safe_load(path.read_text()) if path else {})
