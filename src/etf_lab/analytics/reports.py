import hashlib
import html
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / ".matplotlib"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from etf_lab import __version__  # noqa: E402
from etf_lab.analytics.metrics import metrics  # noqa: E402
from etf_lab.analytics.research import session_analysis  # noqa: E402
from etf_lab.analytics.statistics import block_bootstrap  # noqa: E402
from etf_lab.backtest.engine import BacktestResult  # noqa: E402
from etf_lab.config import LabConfig  # noqa: E402
from etf_lab.storage.database import ResultsDatabase  # noqa: E402


def save_report(
    root: Path,
    data: pd.DataFrame,
    config: LabConfig,
    results: dict[str, BacktestResult],
    benchmark: BacktestResult,
    split: str = "research",
    extra_provenance: dict[str, Any] | None = None,
) -> Path:
    serialized = config.model_dump(mode="json")
    data_hash = hashlib.sha256(data.to_csv(index=False).encode()).hexdigest()
    config_hash = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        commit = None
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "-" + config_hash[:8]
    target = root / "data/reports" / run_id
    target.mkdir(parents=True)
    data.to_parquet(target / "dataset.parquet", index=False)
    metadata = {
        "run_id": run_id,
        "config": serialized,
        "config_hash": config_hash,
        "dataset_hash": data_hash,
        "git_commit": commit,
        "software_version": __version__,
        "source_hash": hashlib.sha256(
            b"".join(
                file.relative_to(root).as_posix().encode() + file.read_bytes()
                for file in sorted((root / "src").rglob("*.py"))
            )
        ).hexdigest(),
        "timestamp": datetime.now(UTC).isoformat(),
        "split": split,
        "provenance": extra_provenance or {},
        "lock_hash": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
        if (root / "uv.lock").exists()
        else None,
    }
    all_metrics = {mode: metrics(result, benchmark) for mode, result in results.items()}
    all_metrics["benchmark"] = metrics(benchmark)
    (target / "metrics.json").write_text(
        json.dumps(all_metrics, indent=2, allow_nan=False), encoding="utf-8"
    )
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    benchmark.curve.to_csv(target / "benchmark.csv", index=False)
    fig, axes = plt.subplots(3, 2, figsize=(14, 12), constrained_layout=True)
    for mode, result in results.items():
        curve = result.curve.set_index("timestamp")
        curve.to_csv(target / f"equity-{mode}.csv")
        result.trades.to_csv(target / f"trades-{mode}.csv", index=False)
        result.fills.to_csv(target / f"fills-{mode}.csv", index=False)
        result.decisions.to_csv(target / f"decisions-{mode}.csv", index=False)
        axes[0, 0].plot(curve.index, curve.equity, label=mode)
        axes[0, 1].plot(curve.index, curve.equity / curve.equity.cummax() - 1, label=mode)
    b = benchmark.curve
    axes[0, 0].plot(
        b.timestamp,
        b.equity,
        label="Buy & Hold (ideal, full allocation)",
        color="black",
        linestyle="--",
    )
    primary = results.get("realistic", next(iter(results.values())))
    daily = primary.curve.set_index("timestamp").equity.resample("1D").last().dropna()
    daily_returns = daily.pct_change().dropna()
    axes[1, 0].plot(daily_returns.rolling(20).std() * 252**0.5)
    if len(daily_returns) < 20:
        axes[1, 0].text(
            0.5,
            0.5,
            "Insufficient history (<20 sessions)",
            ha="center",
            transform=axes[1, 0].transAxes,
        )
    monthly = daily.resample("ME").last().pct_change().dropna()
    axes[1, 1].bar(monthly.index, monthly, width=15)
    if monthly.empty:
        axes[1, 1].text(
            0.5, 0.5, "Insufficient monthly history", ha="center", transform=axes[1, 1].transAxes
        )
    if not primary.trades.empty:
        axes[2, 0].hist(primary.trades.pnl, bins=min(20, len(primary.trades)))
    costs = metrics(primary)
    keys = ["commission", "spread_cost", "slippage_cost", "fx_cost"]
    axes[2, 1].bar(["commission", "spread", "slippage", "FX"], [costs[k] for k in keys])
    titles = [
        "SIMULATED equity (base currency)",
        "Drawdown",
        "20-session annual volatility",
        "Monthly returns (complete month comparisons)",
        "Exit fill P&L",
        "Estimated costs",
    ]
    for ax, title in zip(axes.flat, titles, strict=True):
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=30)
        ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=8)
    fig.savefig(target / "overview.png", dpi=120)
    plt.close(fig)
    by_time, sessions = session_analysis(data)
    by_time.to_csv(target / "time-of-day.csv")
    sessions.to_csv(target / "sessions-gaps.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    if len(daily_returns) >= 30:
        rolling_sharpe = daily_returns.rolling(30).mean() / daily_returns.rolling(30).std()
        axes[0].plot(rolling_sharpe * 252**0.5)
    else:
        axes[0].text(
            0.5,
            0.5,
            "Insufficient history (<30 sessions)",
            ha="center",
            transform=axes[0].transAxes,
        )
    axes[0].set_title("30-session rolling Sharpe, rf=0")
    if not primary.trades.empty:
        axes[1].hist(primary.trades.holding_seconds / 60, bins=20)
    axes[1].set_title("Holding periods (minutes, exit fills)")
    fig.savefig(target / "diagnostics.png", dpi=120)
    plt.close(fig)
    bootstrap = block_bootstrap(daily_returns)
    (target / "statistics.json").write_text(json.dumps(bootstrap, indent=2), encoding="utf-8")
    body = (
        "<!doctype html><html lang='es'><meta charset='utf-8'><title>ETF Quant Lab</title>"
        "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px}"
        "img{width:100%}pre{overflow:auto;background:#eee;padding:20px}</style>"
        "<h1>ETF QUANT LAB — SIMULATED</h1><p>Research only. Historical performance "
        "does not guarantee future results. Las fixtures son sintéticas.</p>"
        "<p>Stops observados al cierre; ejecución posterior. Posiciones finales valoradas "
        "a mercado, sin liquidación ficticia.</p><img src='overview.png' alt='Curvas y costes'>"
        "<img src='diagnostics.png' alt='Sharpe y duración'>"
        "<p><a href='time-of-day.csv'>Franjas horarias (retornos de barras)</a> · "
        "<a href='sessions-gaps.csv'>Gap / overnight e intradía por sesión</a></p>"
        f"<h2>Métricas</h2><pre>{html.escape(json.dumps(all_metrics, indent=2))}</pre>"
        f"<h2>Reproducibilidad</h2><pre>{html.escape(json.dumps(metadata, indent=2))}</pre></html>"
    )
    (target / "report.html").write_text(body, encoding="utf-8")
    (root / "data/reports/latest.txt").write_text(run_id, encoding="utf-8")
    db = ResultsDatabase(root / "data/results.sqlite")
    for mode, metric in all_metrics.items():
        if mode != "benchmark":
            db.save(run_id + "-" + mode, {**metadata, "execution_scenario": mode}, metric)
    return target
