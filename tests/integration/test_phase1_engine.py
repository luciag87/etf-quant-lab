import json

import pandas as pd
import pytest
import yaml

from etf_lab import cli
from etf_lab.analytics.metrics import metrics
from etf_lab.backtest.engine import Backtester
from etf_lab.data.corporate_actions import CorporateAction
from etf_lab.data.fx import TableFXProvider
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.models import Signal
from etf_lab.risk.manager import RiskManager
from etf_lab.strategies.base import ConfiguredStrategy


def test_simultaneous_marks_do_not_latch_false_drawdown(bars, config, registry, monkeypatch):
    a = bars.iloc[:40].copy()
    a[["open", "high", "low", "close", "bid", "ask"]] = 100.0
    b = a.copy()
    eur = registry.resolve("DEMO")
    usd = eur.model_copy(update={"currency": "USD"})
    b["instrument_id"] = usd.id
    a.loc[a.index[20:], ["close", "low", "bid", "ask"]] = 90.0
    b.loc[b.index[20:], ["close", "high", "bid", "ask"]] = 110.0
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    config.risk.position_size_pct = config.risk.max_position_pct = 50
    config.risk.max_sector_exposure_pct = 100
    config.risk.max_drawdown_pct = 3
    config.execution.mode = "ideal"
    fx = TableFXProvider(
        pd.DataFrame(
            dict(timestamp=["2024-01-02T00:00Z"], currency=["USD"], base=["EUR"], rate=[1])
        )
    )
    observed = []
    original = RiskManager.observe

    def observe(self, portfolio, ts):
        blocked = original(self, portfolio, ts)
        observed.append(self.halted)
        return blocked

    monkeypatch.setattr(RiskManager, "observe", observe)
    result = Backtester(config, InstrumentRegistry([eur, usd]), fx).run(
        pd.concat([a, b]).sort_values(["timestamp", "instrument_id"])
    )
    assert len(result.portfolio.positions) == 2
    assert result.portfolio.equity == pytest.approx(10000)
    assert not any(observed)


def test_terminal_distribution_reconciles(bars, config, registry):
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    ts = bars.timestamp.max()
    action = CorporateAction(bars.instrument_id.iloc[0], ts, ts, "distribution", 1)
    result = Backtester(config, registry).run(bars, [action])
    assert result.curve.equity.iloc[-1] == pytest.approx(result.portfolio.equity)


def test_fractional_reverse_split_rejected(bars, config, registry):
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    ts = bars.timestamp.max()
    action = CorporateAction(bars.instrument_id.iloc[0], ts, ts, "split", 0.001)
    with pytest.raises(ValueError, match="Fractional"):
        Backtester(config, registry).run(bars, [action])


def test_pending_ioc_expiry_and_latency(bars, config, registry):
    data = bars.iloc[:25].copy()
    data["volume"] = 0
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    config.risk.minimum_average_volume = 0
    config.execution.latency_ms = 600001
    result = Backtester(config, registry).run(data)
    assert result.fills.empty
    assert "IOC no fill" in result.order_events.reason.tolist()
    for event in result.order_events.query("reason == 'IOC no fill'").itertuples():
        assert event.timestamp > event.created_at + pd.Timedelta(minutes=10)
    assert result.pending_orders


def test_reversed_signal_cancels_delayed_entry(bars, config, registry, monkeypatch):
    data = bars.iloc[:30]
    first = data.timestamp.iloc[19]
    config.risk.sizing = "percentage"
    config.execution.latency_ms = 600001

    def decide(self, row, held):
        return Signal(
            instrument_id=row.instrument_id,
            timestamp=row.timestamp,
            action="LONG" if row.timestamp == first else "HOLD",
            reason="pulse",
        )

    monkeypatch.setattr(ConfiguredStrategy, "decide", decide)
    result = Backtester(config, registry).run(data)
    assert result.fills.empty
    assert "signal invalidated" in result.order_events.reason.tolist()


def test_metrics_open_positions_and_first_intraday_day(bars, config, registry):
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    result = Backtester(config, registry).run(bars)
    before = result.portfolio.cash
    m = metrics(result)
    assert m["marked_to_market_return"] == m["total_return"]
    assert m["open_position_value"] == result.portfolio.exposure
    assert m["estimated_liquidation_cost"] > 0
    assert result.portfolio.cash == before
    assert m["realized_return"] + result.portfolio.unrealized_pnl / 10000 == pytest.approx(
        m["total_return"]
    )


def test_cli_preserves_risk_and_rejects_adjusted(tmp_path, bars, config, registry, monkeypatch):
    monkeypatch.setattr(cli, "registry", lambda: registry)
    dataset = tmp_path / "input.parquet"
    bars.to_parquet(dataset)
    path = tmp_path / "config.yaml"
    config.strategy.name = "buy-and-hold"
    config.risk.max_position_pct = 7
    path.write_text(yaml.safe_dump(config.model_dump()))
    _, loaded, _ = cli.setup(dataset, path, None)
    assert loaded.risk == config.risk
    dataset.with_suffix(".json").write_text(
        json.dumps(dict(timeframe="5m", adjustment_method="adjusted"))
    )
    with pytest.raises(ValueError, match="raw"):
        cli.setup(dataset, path, None)


def test_benchmark_future_listing_does_not_change_prefix(bars, config, registry):
    eur = registry.resolve("DEMO")
    usd = eur.model_copy(update={"currency": "USD"})
    universe = InstrumentRegistry([eur, usd])
    foreign = bars[bars.timestamp >= pd.Timestamp("2024-01-04T00:00Z")].copy()
    foreign["instrument_id"] = usd.id
    combined = pd.concat([bars, foreign]).sort_values(["timestamp", "instrument_id"])
    a, policy_a = cli.benchmark_run(bars, config, universe, TableFXProvider(), [])
    b, policy_b = cli.benchmark_run(combined, config, universe, TableFXProvider(), [])
    pd.testing.assert_frame_equal(a.curve, b.curve)
    assert policy_a == policy_b
    assert policy_a["instrument_ids"] == [eur.id]


def test_partial_exit_keeps_intention_and_fills_use_next_open(bars, config, registry, monkeypatch):
    data = bars.iloc[:35].copy()
    data["volume"] = 100
    entry, exit_at = data.timestamp.iloc[19], data.timestamp.iloc[22]
    config.risk.minimum_average_volume = 0
    config.risk.sizing = "percentage"
    config.execution.mode = "ideal"
    config.execution.max_volume_participation = 0.03
    config.strategy.end_of_day_exit = False
    config.strategy.take_profit_atr_multiple = 0

    def decide(self, row, held):
        action = (
            "LONG" if row.timestamp == entry else "EXIT" if row.timestamp == exit_at else "HOLD"
        )
        return Signal(
            instrument_id=row.instrument_id,
            timestamp=row.timestamp,
            action=action,
            reason="one-time exit",
        )

    monkeypatch.setattr(ConfiguredStrategy, "decide", decide)
    # Entry fills three shares. Reduced subsequent volume only permits one per exit.
    data.loc[data.timestamp >= exit_at, "volume"] = 34
    result = Backtester(config, registry).run(data)
    assert len(result.trades) == 3
    assert len(result.portfolio.closed_cycles) == 1
    assert not result.portfolio.positions
    linked = result.order_events[result.order_events.reason == "fill"]
    assert len(linked) == len(result.fills)
    for event, fill_row in zip(linked.itertuples(), result.fills.itertuples(), strict=True):
        assert event.timestamp >= event.created_at
        opening = data[data.bar_start == event.timestamp].iloc[0]
        assert opening.timestamp > event.created_at
        assert fill_row.price == opening.open


def test_split_inside_bar_rejected(bars, config, registry):
    ts = bars.bar_start.iloc[25] + pd.Timedelta(minutes=1)
    action = CorporateAction(bars.instrument_id.iloc[0], ts, ts, "split", 2)
    with pytest.raises(ValueError, match="inside"):
        Backtester(config, registry).run(bars, [action])


def test_full_report_and_paper_actions_parity(tmp_path, bars, config, registry, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "registry", lambda: registry)
    dataset = tmp_path / "input.parquet"
    bars.to_parquet(dataset)
    config.strategy.name = "buy-and-hold"
    config.risk.sizing = "percentage"
    config.execution.mode = "realistic"
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(config.model_dump()))
    actions_file = tmp_path / "actions.json"
    actions_file.write_text(
        json.dumps(
            [
                dict(
                    instrument_id=bars.instrument_id.iloc[0],
                    effective_at=str(bars.timestamp.max()),
                    known_at=str(bars.timestamp.max()),
                    kind="distribution",
                    value=1,
                )
            ]
        )
    )
    captured = []

    class RecordingBacktester(Backtester):
        def run(self, data, actions=None):
            result = super().run(data, actions)
            captured.append(result)
            return result

    monkeypatch.setattr(cli, "Backtester", RecordingBacktester)
    target = cli.execute(dataset, config_file, None, None, actions_file)
    report = json.loads((target / "metrics.json").read_text())
    assert report["realistic"]["distribution_income"] > 0
    assert (target / "report.html").is_file()
    assert (target / "pending-realistic.json").is_file()
    cli.paper(dataset, config_file, None, None, actions_file)
    pd.testing.assert_frame_equal(captured[1].curve, captured[-1].curve)
    pd.testing.assert_frame_equal(captured[1].fills, captured[-1].fills)
    with pytest.raises(ValueError, match="not supported"):
        cli.optimize(actions_file=actions_file)
    with pytest.raises(ValueError, match="not supported"):
        cli.walkforward(actions_file=actions_file)
