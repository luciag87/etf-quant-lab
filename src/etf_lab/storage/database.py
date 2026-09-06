import json
import sqlite3
from pathlib import Path
from typing import Any


class ResultsDatabase:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS backtest_runs "
                "(run_id TEXT PRIMARY KEY, strategy TEXT, dataset TEXT, "
                "split TEXT, total_return REAL, max_drawdown REAL, sharpe REAL, "
                "expectancy REAL, trades INTEGER, costs REAL, metadata TEXT)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS datasets (dataset_id TEXT PRIMARY KEY, metadata TEXT)"
            )

    def save(self, run_id: str, metadata: dict[str, Any], metrics: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute(
                "INSERT OR REPLACE INTO backtest_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    metadata["config"]["strategy"]["name"],
                    metadata["dataset_hash"],
                    metadata["split"],
                    metrics["total_return"],
                    metrics["max_drawdown"],
                    metrics["Sharpe"],
                    metrics["expectancy"],
                    metrics["number_of_trades"],
                    metrics["total_costs"],
                    json.dumps(metadata),
                ),
            )

    def list(self, sort: str = "expectancy") -> list[dict[str, Any]]:
        if sort not in {"expectancy", "sharpe", "max_drawdown"}:
            raise ValueError("Sort by expectancy, sharpe or max_drawdown")
        with sqlite3.connect(self.path) as con:
            con.row_factory = sqlite3.Row
            return [
                dict(r) for r in con.execute(f"SELECT * FROM backtest_runs ORDER BY {sort} DESC")
            ]
