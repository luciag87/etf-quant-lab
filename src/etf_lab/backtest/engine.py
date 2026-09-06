"""Global clock: completed bars, corporate actions, then next opens at equal time."""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from etf_lab.config import LabConfig
from etf_lab.data.corporate_actions import CorporateAction
from etf_lab.data.fx import FXProvider, TableFXProvider
from etf_lab.data.validator import validate
from etf_lab.execution.paper import PaperBroker
from etf_lab.features.pipeline import features
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.models import OrderIntent, Side, Signal
from etf_lab.portfolio.portfolio import Portfolio
from etf_lab.risk.manager import RiskManager
from etf_lab.strategies.base import ConfiguredStrategy


@dataclass
class BacktestResult:
    curve: pd.DataFrame
    trades: pd.DataFrame
    fills: pd.DataFrame
    decisions: pd.DataFrame
    portfolio: Portfolio


class Backtester:
    def __init__(
        self, config: LabConfig, registry: InstrumentRegistry, fx: FXProvider | None = None
    ) -> None:
        self.config, self.registry = config, registry
        self.fx = fx or TableFXProvider()

    def run(
        self, data: pd.DataFrame, actions: list[CorporateAction] | None = None
    ) -> BacktestResult:
        c = self.config
        data, _ = validate(data, self.registry, c.strategy.timeframe)
        for iid in data.instrument_id.unique():
            i = self.registry.items[iid]
            if not i.researchable or ((i.leveraged or i.inverse) and not c.allow_special_products):
                raise ValueError("Instrument excluded from research universe")
        actions = actions or []
        keys = [(a.instrument_id, a.effective_at, a.kind) for a in actions]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate corporate action")
        for action in actions:
            if action.instrument_id not in self.registry.items:
                raise ValueError("Unregistered corporate action identity")
        # Reset feature warm-up after splits instead of back-adjusting past signals.
        segments = []
        for iid, group in data.groupby("instrument_id"):
            boundaries = sorted(
                a.effective_at for a in actions if a.instrument_id == iid and a.kind == "split"
            )
            labels = group.bar_start.map(lambda t, bounds=boundaries: sum(t >= b for b in bounds))
            for _, segment in group.groupby(labels):
                segments.append(features(segment, c.strategy))
        enriched = (
            pd.concat(segments).sort_values(["timestamp", "instrument_id"]).reset_index(drop=True)
        )
        p = Portfolio(c.risk.starting_equity, c.risk.base_currency)
        risk, strategy = RiskManager(c.risk), ConfiguredStrategy(c.strategy)
        pending: dict[str, OrderIntent] = {}
        last: dict[str, pd.Series] = {}
        counters: dict[str, int] = {}
        daily_closes: dict[str, list[float]] = {}
        curve: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        events: list[tuple[pd.Timestamp, int, str, int]] = []
        for idx, (_, row) in enumerate(enriched.iterrows()):
            events.extend(
                [
                    (row.bar_start, 2, row.instrument_id, int(idx)),
                    (row.timestamp, 0, row.instrument_id, int(idx)),
                ]
            )
        for idx, action in enumerate(actions):
            events.append((action.effective_at, 1, action.instrument_id, idx))
        events.sort()
        initial = min(data.bar_start)
        curve.append(
            {
                "timestamp": initial,
                "equity": p.equity,
                "cash": p.cash,
                "exposure": 0.0,
                "unrealized_pnl": 0.0,
                "fx_pnl": 0.0,
            }
        )
        for ts, kind, iid, idx in events:
            if ts < initial or ts > data.timestamp.max():
                continue
            instrument = self.registry.items[iid]
            rate = self.fx.rate(instrument.currency, p.base_currency, ts)
            for held_iid in p.positions:
                held_price, _ = p.marks[held_iid]
                p.marks[held_iid] = (
                    held_price,
                    self.fx.rate(self.registry.items[held_iid].currency, p.base_currency, ts),
                )
            if kind == 1:
                action = actions[idx]
                if action.kind == "split":
                    pending.pop(iid, None)
                    last.pop(iid, None)
                    daily_closes.pop(iid, None)
                    if iid in p.positions:
                        pos = p.positions[iid]
                        pos.quantity *= action.value
                        pos.average_price /= action.value
                        pos.stop_distance /= action.value
                        pos.atr_at_entry /= action.value
                        pos.peak /= action.value
                        old, old_fx = p.marks[iid]
                        p.marks[iid] = (old / action.value, old_fx)
                elif iid in p.positions:
                    # Accrual at ex-date; payment lag and withholding deliberately excluded.
                    p.cash += p.positions[iid].quantity * action.value * rate
                continue
            row = enriched.iloc[idx].copy()
            if kind == 2:
                p.marks[iid] = (float(row.open), rate)
                if iid not in pending or iid not in last:
                    continue
                order = pending[iid]
                if (
                    c.strategy.end_of_day_exit
                    and c.strategy.name != "buy-and-hold"
                    and order.side == Side.BUY
                    and last[iid].session != row.session
                ):
                    pending.pop(iid)
                    continue
                if order.side == Side.BUY:
                    # Revalidate at actual opening price/cash after gaps and other fills.
                    check_row = last[iid].copy()
                    multiplier = {"ideal": 0, "realistic": 1, "pessimistic": 2}[c.execution.mode]
                    cost_bound = (
                        multiplier
                        * (
                            float(last[iid].spread_bps) / 2
                            + c.execution.slippage_bps
                            + c.execution.impact_bps * c.execution.max_volume_participation
                        )
                        / 10000
                    )
                    check_row["close"] = row.open * (1 + cost_bound)
                    signal = Signal(
                        instrument_id=iid,
                        timestamp=ts,
                        action="LONG",
                        reason=order.reason,
                        stop_distance=order.stop_distance,
                    )
                    approved = risk.approve(
                        signal, check_row, p, rate, self.registry, counters.get(iid, 0)
                    )
                    if approved is None:
                        pending.pop(iid)
                        continue
                    order = order.model_copy(
                        update={"quantity": min(order.quantity, approved.quantity)}
                    )
                else:
                    if iid not in p.positions:
                        pending.pop(iid)
                        continue
                    order = order.model_copy(
                        update={"quantity": min(order.quantity, int(p.positions[iid].quantity))}
                    )
                execution = c.execution.model_copy(deep=True)
                if instrument.currency == p.base_currency:
                    execution.fx_cost_bps = 0
                fill = PaperBroker(execution).execute(
                    order,
                    ts,
                    float(row.open),
                    rate,
                    p.cash,
                    float(last[iid].volume),
                    float(last[iid].spread_bps),
                )
                if fill:
                    atr = float(last[iid].atr) if pd.notna(last[iid].atr) else 0
                    p.apply(fill, order.stop_distance, atr)
                    if fill.side == Side.BUY:
                        risk.trades_today += 1
                    elif p.trades[-1]["pnl"] < 0:
                        risk.cooldown_until = (
                            counters.get(iid, 0) + c.risk.cooldown_after_losses_bars
                        )
                    # IOC: unfilled remainder cancels, never silently assumes full execution.
                    pending.pop(iid)
                continue
            # Only now are this bar's OHLCV and indicators available to decisions.
            p.marks[iid] = (float(row.close), rate)
            counters[iid] = counters.get(iid, 0) + 1
            row["spread_bps"] = (
                (row.ask - row.bid) / ((row.ask + row.bid) / 2) * 10000
                if "bid" in row
                else c.execution.spread_bps
            )
            closes = daily_closes.setdefault(iid, [])
            if ts == row.session_close:
                closes.append(float(row.close))
            row["daily_annual_vol"] = (
                pd.Series(closes[-21:]).pct_change().std() * 252**0.5
                if len(closes) >= 21
                else float("nan")
            )
            last[iid] = row
            signal = strategy.decide(row, iid in p.positions)
            halted = risk.observe(p, ts)
            if iid in p.positions and c.strategy.name != "buy-and-hold":
                pos = p.positions[iid]
                pos.bars_held += 1
                pos.peak = max(pos.peak, float(row.close))
                reason = ""
                if pos.stop_distance > 0 and row.close <= pos.average_price - pos.stop_distance:
                    reason = "close-observed stop"
                elif (
                    c.strategy.take_profit_atr_multiple > 0
                    and row.close
                    >= pos.average_price + pos.atr_at_entry * c.strategy.take_profit_atr_multiple
                ):
                    reason = "close-observed take profit"
                elif (
                    c.strategy.trailing_atr_multiple > 0
                    and row.close <= pos.peak - pos.atr_at_entry * c.strategy.trailing_atr_multiple
                ):
                    reason = "close-observed trailing stop"
                elif pos.bars_held >= c.strategy.max_holding_bars:
                    reason = "time exit"
                # Submit early enough to leave a later opening after configured latency.
                bar_minutes = (row.timestamp - row.bar_start).total_seconds() / 60
                if c.strategy.end_of_day_exit and row.minutes_before_close <= 2 * bar_minutes:
                    reason = "end of day"
                if halted:
                    reason = "risk halt"
                if reason:
                    signal = signal.model_copy(update={"action": "EXIT", "reason": reason})
            if signal.action != "HOLD" and iid not in pending:
                new_order = risk.approve(signal, row, p, rate, self.registry, counters[iid])
                decisions.append(
                    {**signal.model_dump(mode="json"), "approved": new_order is not None}
                )
                if new_order:
                    pending[iid] = new_order
            # FX marks of every held listing refreshed as of the global clock, never backfilled.
            for key in p.positions:
                px, _ = p.marks[key]
                p.marks[key] = (
                    px,
                    self.fx.rate(self.registry.items[key].currency, p.base_currency, ts),
                )
            curve.append(
                {
                    "timestamp": ts,
                    "equity": p.equity,
                    "cash": p.cash,
                    "exposure": p.exposure,
                    "unrealized_pnl": p.unrealized_pnl,
                    "fx_pnl": p.fx_pnl,
                }
            )
        return BacktestResult(
            pd.DataFrame(curve).drop_duplicates("timestamp", keep="last"),
            pd.DataFrame(p.trades),
            pd.DataFrame([f.model_dump() for f in p.fills]),
            pd.DataFrame(decisions),
            p,
        )
