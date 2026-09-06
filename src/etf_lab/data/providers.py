"""Offline adapters share the same contract as future licensed adapters."""

from pathlib import Path
from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    name: str

    def read(self) -> pd.DataFrame: ...


class FileProvider:
    name = "user-file"

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> pd.DataFrame:
        if self.path.suffix.lower() == ".csv":
            return pd.read_csv(self.path)
        if self.path.suffix.lower() == ".parquet":
            return pd.read_parquet(self.path)
        raise ValueError("Expected CSV or Parquet")
