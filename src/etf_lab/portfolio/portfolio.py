from dataclasses import dataclass
from typing import Any

import pandas as pd

from etf_lab.models import Fill, Side


@dataclass
class Position:
    quantity: float
    average_price: float
    average_fx: float
    cost_base: float
    entry_at: pd.Timestamp
    entry_fees: float = 0
    stop_distance: float = 0
    atr_at_entry: float = 0
    peak: float = 0
    bars_held: int = 0


class Portfolio:
    def __init__(self, cash: float = 10000, base_currency: str = "EUR") -> None:
        self.base_currency = base_currency
        self.cash = cash
        self.initial_equity = cash
        self.positions: dict[str, Position] = {}
        self.marks: dict[str, tuple[float, float]] = {}
        self.realized_pnl = 0.0
        self.fx_pnl = 0.0
        self.fees = 0.0
        self.trades: list[dict[str, Any]] = []
        self.fills: list[Fill] = []

    @property
    def exposure(self) -> float:
        return sum(
            p.quantity * self.marks[i][0] * self.marks[i][1] for i, p in self.positions.items()
        )

    @property
    def equity(self) -> float:
        return self.cash + self.exposure

    @property
    def unrealized_pnl(self) -> float:
        return self.exposure - sum(p.cost_base for p in self.positions.values())

    def apply(self, fill: Fill, stop_distance: float = 0, atr: float = 0) -> None:
        iid, q = fill.instrument_id, fill.quantity
        notional = q * fill.price * fill.fx_rate
        fees = fill.commission + fill.fx_cost
        if fill.side == Side.BUY:
            if notional + fees > self.cash + 1e-8:
                raise ValueError("Insufficient cash")
            self.cash -= notional + fees
            if iid in self.positions:
                p = self.positions[iid]
                total = p.quantity + q
                local_cost = p.quantity * p.average_price + q * fill.price
                p.average_price = local_cost / total
                p.cost_base += notional
                p.average_fx = p.cost_base / local_cost
                p.quantity = total
                p.entry_fees += fees
            else:
                self.positions[iid] = Position(
                    q,
                    fill.price,
                    fill.fx_rate,
                    notional,
                    pd.Timestamp(fill.timestamp),
                    fees,
                    stop_distance,
                    atr,
                    fill.price,
                )
        else:
            p = self.positions[iid]
            if q > p.quantity + 1e-8:
                raise ValueError("Short selling forbidden")
            fraction = q / p.quantity
            basis, entry_fees = p.cost_base * fraction, p.entry_fees * fraction
            pnl = notional - basis - fees - entry_fees
            local_pnl = q * (fill.price - p.average_price) * p.average_fx
            fx_pnl = q * fill.price * (fill.fx_rate - p.average_fx)
            self.fx_pnl += fx_pnl
            self.realized_pnl += pnl
            self.cash += notional - fees
            self.trades.append(
                {
                    "instrument_id": iid,
                    "entry_at": p.entry_at,
                    "exit_at": fill.timestamp,
                    "quantity": q,
                    "pnl": pnl,
                    "local_pnl": local_pnl,
                    "fx_pnl": fx_pnl,
                    "fees": fees + entry_fees,
                    "holding_seconds": (pd.Timestamp(fill.timestamp) - p.entry_at).total_seconds(),
                    "reason": fill.reason,
                }
            )
            p.quantity -= q
            p.cost_base -= basis
            p.entry_fees -= entry_fees
            if p.quantity < 1e-8:
                del self.positions[iid]
        self.fees += fees
        self.marks[iid] = (fill.price, fill.fx_rate)
        self.fills.append(fill)
