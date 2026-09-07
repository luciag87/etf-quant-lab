import pandas as pd
import pytest

from etf_lab.analytics.metrics import daily_returns
from etf_lab.config import RiskConfig
from etf_lab.models import Fill, Side, Signal
from etf_lab.portfolio.portfolio import Portfolio
from etf_lab.risk.manager import RiskManager


def fill(**updates: object) -> Fill:
    values = dict(
        instrument_id="ZZ0000000008:XETR:EUR",
        side=Side.BUY,
        quantity=2,
        timestamp=pd.Timestamp("2024-01-02T10:00Z"),
        price=100,
        fx_rate=1,
        commission=1,
        fx_cost=0,
        spread_cost=0,
        slippage_cost=0,
        reason="test",
    )
    values.update(updates)
    return Fill.model_validate(values)


@pytest.mark.parametrize(
    "update",
    [
        {"quantity": -2},
        {"quantity": 0},
        {"quantity": True},
        {"price": float("nan")},
        {"price": 0},
        {"fx_rate": float("inf")},
        {"commission": -1},
        {"timestamp": pd.Timestamp("2024-01-02")},
        {"unexpected": 1},
    ],
)
def test_invalid_fill_rejected_without_mutation(update: dict) -> None:
    p = Portfolio(1000)
    with pytest.raises(ValueError):
        p.apply(fill(**update))
    assert p.cash == 1000 and not p.positions and not p.fills


def test_impossible_sale_is_explicit_and_atomic() -> None:
    p = Portfolio(1000)
    with pytest.raises(ValueError, match="position"):
        p.apply(fill(side=Side.SELL))
    assert p.cash == 1000 and not p.fills


def test_fill_is_immutable() -> None:
    f = fill()
    with pytest.raises(ValueError):
        f.quantity = -1


def test_cooldown_scoped_and_boundary(registry) -> None:
    risk = RiskManager(RiskConfig(sizing="percentage"))
    iid = "ZZ0000000008:XETR:EUR"
    risk.record_loss("another-listing", 100)
    signal = Signal(
        instrument_id=iid, timestamp=pd.Timestamp("2024-01-02T10:00Z"), action="LONG", reason="test"
    )
    row = pd.Series(dict(close=100, average_volume=1000, spread_bps=0))
    p = Portfolio()
    assert risk.approve(signal, row, p, 1, registry, 2) is not None
    risk.record_loss(iid, 2)
    assert risk.approve(signal, row, p, 1, registry, 7) is None
    assert risk.approve(signal, row, p, 1, registry, 8) is not None
    risk.record_loss(iid, 4)
    assert risk.approve(signal, row, p, 1, registry, 8) is None
    zero = RiskManager(RiskConfig(cooldown_after_losses_bars=0, sizing="percentage"))
    zero.record_loss(iid, 0)
    assert zero.approve(signal, row, p, 1, registry, 0) is not None


@pytest.mark.parametrize(
    "zone,before,after",
    [
        ("Europe/Madrid", "2024-03-30T22:55Z", "2024-03-30T23:05Z"),
        ("America/New_York", "2024-03-11T03:55Z", "2024-03-11T04:05Z"),
        ("UTC", "2024-01-02T23:55Z", "2024-01-03T00:05Z"),
    ],
)
def test_daily_boundary_counts_gap_and_latches(zone, before, after) -> None:
    risk = RiskManager(RiskConfig(risk_timezone=zone, max_drawdown_pct=100))
    p = Portfolio()
    risk.observe(p, pd.Timestamp(before))
    p.cash = 9700
    assert risk.observe(p, pd.Timestamp(after))
    p.cash = 10000
    assert risk.observe(p, pd.Timestamp(after) + pd.Timedelta(minutes=1))
    assert not risk.observe(p, pd.Timestamp(after) + pd.Timedelta(days=1))


def test_first_loss_and_timezone_validation() -> None:
    p = Portfolio()
    p.cash = 9700
    assert RiskManager(RiskConfig()).observe(p, pd.Timestamp("2024-01-02T10:00Z"))
    with pytest.raises(ValueError):
        RiskConfig(risk_timezone="Not/A_Timezone")


def test_open_fees_and_partial_cycle_reconcile() -> None:
    p = Portfolio(1000)
    p.apply(fill(quantity=4))
    assert p.realized_pnl + p.unrealized_pnl == pytest.approx(p.equity - 1000)
    p.apply(fill(side=Side.SELL, quantity=2, price=110))
    assert not p.closed_cycles
    p.apply(fill(side=Side.SELL, quantity=2, price=120))
    assert len(p.trades) == 2 and len(p.closed_cycles) == 1
    assert p.closed_cycles[0]["pnl"] == pytest.approx(57)
    assert p.realized_pnl == pytest.approx(p.equity - 1000)
    p.apply(fill(quantity=1))
    p.apply(fill(side=Side.SELL, quantity=1, price=110))
    assert len(p.closed_cycles) == 2


def test_first_intraday_return_is_included() -> None:
    equity = pd.Series(
        [1000, 1100, 1100, 1100],
        index=pd.to_datetime(
            ["2024-01-02T09:00Z", "2024-01-02T16:00Z", "2024-01-03T16:00Z", "2024-01-04T16:00Z"]
        ),
    )
    returns = daily_returns(equity)
    assert returns.tolist() == pytest.approx([0.1, 0, 0])
    assert (1 + returns).prod() == pytest.approx(1.1)


def test_overflowing_fill_and_unfunded_fees_are_atomic() -> None:
    p = Portfolio(1000)
    p.apply(fill())
    before = p.cash
    for candidate in [
        fill(side=Side.SELL, price=1e308, fx_rate=1e308),
        fill(side=Side.SELL, commission=2000),
    ]:
        with pytest.raises(ValueError):
            p.apply(candidate)
        assert p.cash == before and len(p.fills) == 1
