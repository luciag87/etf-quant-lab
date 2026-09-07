import json
import platform
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from etf_lab.analytics.reports import save_report
from etf_lab.backtest.engine import Backtester, BacktestResult
from etf_lab.backtest.optimizer import optimize as run_optimize
from etf_lab.backtest.walkforward import walkforward as run_walkforward
from etf_lab.config import LabConfig, load_config
from etf_lab.data.corporate_actions import CorporateAction
from etf_lab.data.fixtures import generate
from etf_lab.data.fx import TableFXProvider
from etf_lab.data.importer import import_data, latest
from etf_lab.data.validator import validate
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.storage.database import ResultsDatabase

app = typer.Typer(help="ETF QUANT LAB — RESEARCH / SIMULATED ONLY", no_args_is_help=True)
console = Console()
ROOT = Path.cwd()
OptionPath = Annotated[Path | None, typer.Option()]


def registry() -> InstrumentRegistry:
    return InstrumentRegistry.load(ROOT / "config/universe.example.yaml")


def setup(
    dataset: Path | None, config: Path | None, strategy: str | None, fx_file: Path | None = None
) -> tuple[pd.DataFrame, LabConfig, TableFXProvider]:
    c = load_config(config)
    path = dataset or latest(ROOT)
    frame = pd.read_parquet(path)
    if path.with_suffix(".json").exists():
        metadata = json.loads(path.with_suffix(".json").read_text())
        if metadata.get("adjustment_method", "raw") != "raw":
            raise ValueError("Engine accepts raw OHLC only")
        tf = metadata["timeframe"]
        if config and c.strategy.timeframe != tf:
            raise ValueError("Strategy and dataset timeframes differ")
        c.strategy.timeframe = tf
    if strategy:
        c.strategy.name = strategy  # type: ignore[assignment]
    if c.strategy.timeframe == "1d" and config is None:
        c.strategy.entry_start_minutes_after_open = 0
        c.strategy.entry_end_minutes_before_close = 0
        c.strategy.end_of_day_exit = False
    frame, _ = validate(frame, registry(), c.strategy.timeframe)
    fx = TableFXProvider(pd.read_csv(fx_file) if fx_file else None, c.fx_max_age_hours)
    return frame, c, fx


@app.command()
def doctor() -> None:
    """Check offline environment and calendar availability."""
    from etf_lab.data.calendars import schedule

    for mic in ["XNYS", "XNAS", "XLON", "XETR", "XAMS", "XPAR"]:
        schedule(mic, "2024-01-02", "2024-01-05")
    console.print(
        {
            "status": "PASS",
            "python": platform.python_version(),
            "instruments": len(registry().items),
            "execution": "SIMULATED ONLY",
        }
    )


@app.command()
def instruments() -> None:
    """List catalogued listings; no inference of legal availability."""
    for instrument in registry().items.values():
        console.print(instrument.model_dump(mode="json", by_alias=True))


@app.command("fixtures")
def fixtures_command() -> None:
    generate(ROOT)
    console.print("Deterministic synthetic CSV/Parquet fixtures generated")


@app.command("import")
def import_command(
    path: Path, timeframe: str = "5m", mapping: OptionPath = None, adjustment: str = "raw"
) -> None:
    """Import a user file; --mapping JSON maps source column names to canonical names."""
    target, report = import_data(
        path,
        ROOT,
        registry(),
        timeframe,  # type: ignore[arg-type]
        json.loads(mapping.read_text()) if mapping else None,
        adjustment,
    )
    console.print(report)
    console.print(str(target))


@app.command("doctor-data")
def doctor_data(dataset: OptionPath = None, timeframe: str = "5m") -> None:
    path = dataset or latest(ROOT)
    try:
        if path.with_suffix(".json").exists():
            timeframe = json.loads(path.with_suffix(".json").read_text())["timeframe"]
        frame = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
        _, report = validate(frame, registry(), timeframe)  # type: ignore[arg-type]
        console.print(report)
    except ValueError as error:
        console.print({"status": "FAIL", "error": str(error)})
        raise typer.Exit(1) from error


def load_actions(path: Path | None) -> list[CorporateAction]:
    if path is None:
        return []
    return [
        CorporateAction(
            instrument_id=r["instrument_id"],
            kind=r["kind"],
            value=r["value"],
            effective_at=pd.Timestamp(r["effective_at"]),
            known_at=pd.Timestamp(r["known_at"]),
        )
        for r in json.loads(path.read_text())
    ]


def benchmark_run(
    data: pd.DataFrame,
    config: LabConfig,
    universe: InstrumentRegistry,
    fx: TableFXProvider,
    actions: list[CorporateAction],
) -> tuple[BacktestResult, dict[str, Any]]:
    # Membership is frozen using only listings observed at the initial opening.
    # Later listings do not retroactively dilute initial target weights.
    start = data.bar_start.min()
    ids = sorted(data.loc[data.bar_start == start, "instrument_id"].unique().tolist())
    baseline = config.model_copy(deep=True)
    baseline.strategy.name = "buy-and-hold"
    baseline.risk.sizing = "percentage"
    baseline.risk.position_size_pct = 100 / len(ids)
    baseline.risk.max_position_pct = baseline.risk.max_sector_exposure_pct = 100
    baseline.risk.max_total_exposure_pct = 100
    baseline.risk.max_open_positions = baseline.risk.max_trades_per_day = len(ids)
    baseline.risk.max_daily_loss_pct = baseline.risk.max_drawdown_pct = 100
    baseline.execution.mode = "ideal"
    eligible = data[data.instrument_id.isin(ids)].copy()
    result = Backtester(baseline, universe, fx).run(
        eligible, [a for a in actions if a.instrument_id in ids]
    )
    return result, {
        "membership": "frozen at first observed opening; later listings excluded",
        "instrument_ids": ids,
        "as_of": str(start),
        "config": baseline.model_dump(mode="json"),
        "allocation": "equal target weights; integer rounding, warm-up and liquidity apply",
    }


def execute(
    dataset: Path | None,
    config: Path | None,
    strategy: str | None,
    fx_file: Path | None,
    actions_file: Path | None = None,
) -> Path:
    data, c, fx = setup(dataset, config, strategy, fx_file)
    actions = load_actions(actions_file)
    results = {}
    for mode in ["ideal", "realistic", "pessimistic"]:
        scenario = c.model_copy(deep=True)
        scenario.execution.mode = mode  # type: ignore[assignment]
        results[mode] = Backtester(scenario, registry(), fx).run(data, actions)
    benchmark, policy = benchmark_run(data, c, registry(), fx, actions)
    provenance: dict[str, Any] = {
        "registry": [i.model_dump(mode="json", by_alias=True) for i in registry().items.values()],
        "benchmark_policy": policy,
        "fx_table": fx.frame.to_json(date_format="iso"),
        "corporate_actions": actions_file.read_text() if actions_file else [],
    }
    target = save_report(ROOT, data, c, results, benchmark, extra_provenance=provenance)
    console.print(json.loads((target / "metrics.json").read_text()))
    console.print(str(target / "report.html"))
    return target


@app.command()
def backtest(
    dataset: OptionPath = None,
    config: OptionPath = None,
    strategy: str | None = None,
    fx_file: OptionPath = None,
    actions_file: OptionPath = None,
) -> None:
    execute(dataset, config, strategy, fx_file, actions_file)


@app.command()
def paper(
    dataset: OptionPath = None,
    config: OptionPath = None,
    strategy: str | None = None,
    fx_file: OptionPath = None,
    actions_file: OptionPath = None,
) -> None:
    """Offline historical paper replay using the SAME engine. Not a live feed."""
    data, c, fx = setup(dataset, config, strategy, fx_file)
    result = Backtester(c, registry(), fx).run(data, load_actions(actions_file))
    table = Table(title="ETF QUANT LAB — SIMULATED PAPER REPLAY (historical)")
    table.add_column("Item")
    table.add_column("Value")
    for key, value in {
        "Strategy": c.strategy.name,
        "As of": str(data.timestamp.max()),
        "Equity": result.portfolio.equity,
        "Cash": result.portfolio.cash,
        "Unrealized": result.portfolio.unrealized_pnl,
        "Positions": str(result.portfolio.positions),
        "Exit fills": len(result.trades),
        "Closed position cycles": len(result.portfolio.closed_cycles),
        "Pending orders": len(result.pending_orders),
        "Estimated liquidation cost": result.estimated_liquidation_cost,
    }.items():
        table.add_row(key, str(value))
    console.print(table)


@app.command()
def optimize(
    dataset: OptionPath = None,
    config: OptionPath = None,
    strategy: str | None = None,
    fx_file: OptionPath = None,
    evaluate_test: bool = False,
    random_count: int | None = None,
    actions_file: OptionPath = None,
) -> None:
    if actions_file is not None:
        raise ValueError("Corporate actions are not supported in optimization folds yet")
    data, c, fx = setup(dataset, config, strategy, fx_file)
    result = run_optimize(
        data, c, registry(), fx, random_count=random_count, evaluate_test=evaluate_test
    )
    target = ROOT / "data/backtests/optimization.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "selected": result.config.model_dump(),
                "trials": result.trials,
                "final_test": result.final_test,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    console.print(str(target))


@app.command()
def walkforward(
    dataset: OptionPath = None,
    config: OptionPath = None,
    strategy: str | None = None,
    fx_file: OptionPath = None,
    train_months: int = 12,
    test_months: int = 3,
    step_months: int = 3,
    actions_file: OptionPath = None,
) -> None:
    if actions_file is not None:
        raise ValueError("Corporate actions are not supported in walk-forward folds yet")
    # A bundled two-year daily synthetic dataset makes the default command reproducible.
    if dataset is None and config is None:
        dataset = ROOT / "data/sample_daily.parquet"
        c = LabConfig()
        c.strategy.timeframe = "1d"
        c.strategy.entry_start_minutes_after_open = 0
        c.strategy.entry_end_minutes_before_close = 0
        c.strategy.end_of_day_exit = False
        c.strategy.name = strategy or "momentum"  # type: ignore[assignment]
        data, _ = validate(pd.read_parquet(dataset), registry(), "1d")
        fx = TableFXProvider()
    else:
        data, c, fx = setup(dataset, config, strategy, fx_file)
    output = run_walkforward(data, c, registry(), fx, train_months, test_months, step_months)
    target = ROOT / "data/backtests/walkforward.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2), encoding="utf-8")
    console.print(output)


@app.command()
def report() -> None:
    """Show the latest generated HTML report path."""
    run_id = (ROOT / "data/reports/latest.txt").read_text().strip()
    console.print(str(ROOT / "data/reports" / run_id / "report.html"))


@app.command()
def experiments(sort: str = "expectancy") -> None:
    for row in ResultsDatabase(ROOT / "data/results.sqlite").list(sort):
        row.pop("metadata")
        console.print(row)


@app.command()
def download() -> None:
    console.print(
        "No licensed remote adapter configured. Use etf-lab import CSV/Parquet. "
        "See docs/DATA_SOURCES.md."
    )
    raise typer.Exit(2)


@app.command()
def record() -> None:
    console.print(
        "No realtime/delayed provider configured. Offline replay is available with paper."
    )
    raise typer.Exit(2)


@app.command(hidden=True)
def live() -> None:
    console.print("Live trading is intentionally unavailable in this research-only build.")
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
