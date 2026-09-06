import math

import pandas as pd

from etf_lab.config import ExecutionConfig
from etf_lab.models import Fill, OrderIntent, Side


class PaperBroker:
    """Discrete-open execution; liquidity/spread estimated from last completed bar."""

    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config

    def execute(
        self,
        order: OrderIntent,
        timestamp: pd.Timestamp,
        opening_price: float,
        fx: float,
        cash: float,
        previous_volume: float,
        previous_spread_bps: float,
    ) -> Fill | None:
        c = self.config
        latency = 0 if c.mode == "ideal" else c.latency_ms
        if timestamp < pd.Timestamp(order.created_at) + pd.Timedelta(milliseconds=latency):
            return None
        multiplier = {"ideal": 0, "realistic": 1, "pessimistic": 2}[c.mode]
        capacity = math.floor(previous_volume * c.max_volume_participation)
        q = min(order.quantity, capacity)
        if q <= 0:
            return None
        participation = q / max(previous_volume, 1)
        half_spread = previous_spread_bps / 20000 * multiplier
        slip = (c.slippage_bps + c.impact_bps * participation) / 10000 * multiplier
        sign = 1 if order.side == Side.BUY else -1
        price = opening_price * (1 + sign * (half_spread + slip))
        if price <= 0:
            raise ValueError("Execution costs imply non-positive fill")
        fx_bps = c.fx_cost_bps / 10000 * multiplier
        commission_rate = c.commission_bps / 10000 * multiplier
        minimum = c.minimum_commission * multiplier
        if order.side == Side.BUY:
            # Upper-bound both proportional and minimum commission before flooring.
            affordable = math.floor(
                max(0, cash - minimum) / (price * fx * (1 + fx_bps + commission_rate))
            )
            q = min(q, affordable)
        if q <= 0:
            return None
        notional = q * price * fx
        return Fill(
            instrument_id=order.instrument_id,
            side=order.side,
            quantity=q,
            timestamp=timestamp,
            price=price,
            fx_rate=fx,
            commission=max(minimum, notional * commission_rate),
            fx_cost=notional * fx_bps,
            spread_cost=q * opening_price * fx * half_spread,
            slippage_cost=q * opening_price * fx * slip,
            reason=order.reason,
        )
