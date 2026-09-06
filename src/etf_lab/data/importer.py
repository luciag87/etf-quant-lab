import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from etf_lab.config import Timeframe
from etf_lab.data.providers import FileProvider
from etf_lab.data.validator import validate
from etf_lab.instruments.registry import InstrumentRegistry
from etf_lab.storage.database import ResultsDatabase


def import_data(
    path: Path,
    root: Path,
    registry: InstrumentRegistry,
    timeframe: Timeframe = "5m",
    mapping: dict[str, str] | None = None,
    adjustment: str = "raw",
) -> tuple[Path, dict[str, Any]]:
    if adjustment != "raw":
        raise ValueError("Engine accepts raw OHLC only; adjusted series risk double adjustment")
    frame = FileProvider(path).read().rename(columns=mapping or {})
    if "instrument_id" not in frame:
        frame["instrument_id"] = [
            registry.resolve(str(row["symbol"]), row.get("mic"), row.get("currency")).id
            for row in frame.to_dict("records")
        ]
    clean, report = validate(frame, registry, timeframe)
    key = hashlib.sha256(
        path.read_bytes()
        + json.dumps(
            {
                "timeframe": timeframe,
                "adjustment": adjustment,
                "mapping": mapping,
                "registry": [
                    i.model_dump(mode="json", by_alias=True) for i in registry.items.values()
                ],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    target = root / "data/clean" / f"{key}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        clean.to_parquet(target, index=False)
    metadata = {
        "dataset_id": key,
        "provider": "user-file",
        "source": str(path),
        "created_at": datetime.now(UTC).isoformat(),
        "timeframe": timeframe,
        "adjustment_method": adjustment,
        "doctor": report,
    }
    target.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (root / "data/clean/latest.txt").write_text(target.name, encoding="utf-8")
    db = ResultsDatabase(root / "data/results.sqlite")
    with sqlite3.connect(db.path) as con:
        con.execute("INSERT OR IGNORE INTO datasets VALUES (?,?)", (key, json.dumps(metadata)))
    return target, report


def latest(root: Path) -> Path:
    return root / "data/clean" / (root / "data/clean/latest.txt").read_text().strip()


def load_dataset(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)
