import pandas as pd
import pytest

from etf_lab.config import ExecutionConfig, LabConfig
from etf_lab.execution.paper import PaperBroker
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.models import Fill, OrderIntent, Side, Signal
from etf_lab.portfolio.portfolio import Portfolio
from etf_lab.risk.manager import RiskManager

IID = "ZZ0000000008:XETR:EUR"
TS = pd.Timestamp("2024-01-02T10:00Z")


def test_fill_latency_partial_cash_costs() -> None:
    order = OrderIntent(
        instrument_id=IID, side=Side.BUY, quantity=100, created_at=TS, reason="test"
    )
    broker = PaperBroker(ExecutionConfig())
    assert broker.execute(order, TS, 100, 1, 10000, 1000, 4) is None
    fill = broker.execute(order, TS + pd.Timedelta(minutes=5), 100, 1, 10000, 1000, 4)
    assert fill is not None and fill.quantity == 50
    assert fill.price > 100 and fill.commission >= 1 and fill.fx_cost > 0
    assert fill.spread_cost > 0 and fill.slippage_cost > 0
    small = broker.execute(order, TS + pd.Timedelta(minutes=5), 100, 1, 150, 1000, 4)
    assert small is not None and small.quantity == 1


def make_fill(side: Side, price: float, rate: float = 1, qty: int = 5) -> Fill:
    return Fill(
        instrument_id=IID,
        side=side,
        quantity=qty,
        timestamp=TS,
        price=price,
        fx_rate=rate,
        commission=1,
        fx_cost=0,
        spread_cost=0,
        slippage_cost=0,
        reason="test",
    )


def test_portfolio_pnl_fx_and_cash() -> None:
    p = Portfolio(1000)
    p.apply(make_fill(Side.BUY, 100, 0.9))
    p.apply(make_fill(Side.SELL, 110, 0.95))
    assert p.cash == pytest.approx(1070.5)
    assert p.realized_pnl == pytest.approx(70.5)
    assert p.fx_pnl == pytest.approx(27.5)
    assert p.trades[0]["local_pnl"] + p.trades[0]["fx_pnl"] - 2 == pytest.approx(70.5)
    with pytest.raises(ValueError, match="cash"):
        Portfolio(1).apply(make_fill(Side.BUY, 100))


@pytest.mark.parametrize("sizing", ["fixed", "percentage", "atr", "volatility"])
def test_sizing_limits(config: LabConfig, registry: InstrumentRegistry, sizing: str) -> None:
    config.risk.sizing = sizing  # type: ignore[assignment]
    risk, p = RiskManager(config.risk), Portfolio()
    signal = Signal(instrument_id=IID, timestamp=TS, action="LONG", reason="test", stop_distance=2)
    row = pd.Series(
        {"close": 100, "average_volume": 10000, "spread_bps": 4, "daily_annual_vol": 0.2}
    )
    order = risk.approve(signal, row, p, 1, registry, 0)
    assert order is not None and 0 < order.quantity <= 10
    p.cash = 50
    assert risk.approve(signal, row, p, 1, registry, 0) is None


def test_drawdown_halt(config: LabConfig) -> None:
    risk, p = RiskManager(config.risk), Portfolio()
    assert not risk.observe(p, TS)
    p.cash = 8000
    assert risk.observe(p, TS)
    assert risk.observe(p, TS + pd.Timedelta(days=1))
