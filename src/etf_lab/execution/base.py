from typing import Protocol

import pandas as pd

from etf_lab.models import Fill, OrderIntent


class ExecutionBroker(Protocol):
    def execute(
        self,
        order: OrderIntent,
        timestamp: pd.Timestamp,
        opening_price: float,
        fx: float,
        cash: float,
        previous_volume: float,
        previous_spread_bps: float,
    ) -> Fill | None: ...
