import math

import pandas as pd

from etf_lab.config import RiskConfig
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.models import OrderIntent, Side, Signal
from etf_lab.portfolio.portfolio import Portfolio


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self.peak = config.starting_equity
        self.day_equity = config.starting_equity
        self.day = ""
        self.trades_today = 0
        self.cooldown_until: dict[str, int] = {}
        self.halted = False
        self.daily_halted = False
        self.last_equity = config.starting_equity

    def record_loss(self, instrument_id: str, bar_number: int) -> None:
        self.cooldown_until[instrument_id] = max(
            self.cooldown_until.get(instrument_id, -1),
            bar_number + self.config.cooldown_after_losses_bars,
        )

    def observe(self, portfolio: Portfolio, ts: pd.Timestamp) -> bool:
        day = str(ts.tz_convert(self.config.risk_timezone).date())
        if day != self.day:
            self.day, self.day_equity, self.trades_today = day, self.last_equity, 0
            self.daily_halted = False
        self.peak = max(self.peak, portfolio.equity)
        self.halted |= portfolio.equity / self.peak - 1 <= -self.config.max_drawdown_pct / 100
        self.daily_halted |= (
            portfolio.equity / self.day_equity - 1 <= -self.config.max_daily_loss_pct / 100
        )
        self.last_equity = portfolio.equity
        return self.halted or self.daily_halted

    def approve(
        self,
        signal: Signal,
        row: pd.Series,
        portfolio: Portfolio,
        fx: float,
        registry: InstrumentRegistry,
        bar_number: int,
    ) -> OrderIntent | None:
        c, iid = self.config, signal.instrument_id
        blocked = self.observe(portfolio, pd.Timestamp(signal.timestamp))
        if signal.action == "EXIT":
            if iid not in portfolio.positions:
                return None
            quantity, side = math.floor(portfolio.positions[iid].quantity), Side.SELL
        elif signal.action == "LONG":
            if (
                blocked
                or iid in portfolio.positions
                or bar_number < self.cooldown_until.get(iid, -1)
                or self.trades_today >= c.max_trades_per_day
                or len(portfolio.positions) >= c.max_open_positions
            ):
                return None
            avg = row.get("average_volume", float("nan"))
            if (
                row.close < c.minimum_price
                or pd.isna(avg)
                or avg < c.minimum_average_volume
                or row.spread_bps > c.maximum_spread_bps
            ):
                return None
            equity, unit = portfolio.equity, row.close * fx
            notional = equity * c.position_size_pct / 100
            if c.sizing == "fixed":
                notional = c.fixed_notional
            elif c.sizing == "atr":
                if signal.stop_distance <= 0:
                    return None
                notional = equity * c.risk_per_trade_pct / 100 / (signal.stop_distance * fx) * unit
            elif c.sizing == "volatility":
                # Daily volatility is derived from completed session returns in the engine.
                vol = row.get("daily_annual_vol", float("nan"))
                if pd.isna(vol) or vol <= 0:
                    return None
                notional = equity * min(1, c.target_annual_vol / vol)
            sector = registry.items[iid].sector
            sector_value = sum(
                p.quantity * portfolio.marks[k][0] * portfolio.marks[k][1]
                for k, p in portfolio.positions.items()
                if registry.items[k].sector == sector
            )
            notional = min(
                notional,
                equity * c.max_position_pct / 100,
                equity * c.max_total_exposure_pct / 100 - portfolio.exposure,
                equity * c.max_sector_exposure_pct / 100 - sector_value,
                portfolio.cash,
            )
            quantity, side = math.floor(max(0, notional) / unit), Side.BUY
        else:
            return None
        if quantity <= 0:
            return None
        return OrderIntent(
            instrument_id=iid,
            side=side,
            quantity=quantity,
            created_at=signal.timestamp,
            reason=signal.reason,
            stop_distance=signal.stop_distance,
        )
