from dataclasses import dataclass
from math import isfinite
from typing import Literal

import pandas as pd


@dataclass(frozen=True)
class CorporateAction:
    instrument_id: str
    effective_at: pd.Timestamp
    known_at: pd.Timestamp
    kind: Literal["split", "distribution"]
    value: float

    def __post_init__(self) -> None:
        if self.kind not in {"split", "distribution"} or not isfinite(self.value):
            raise ValueError("Invalid corporate action type/value")
        if self.value <= 0 or self.known_at.tzinfo is None or self.effective_at.tzinfo is None:
            raise ValueError("Invalid corporate action")
        if self.known_at > self.effective_at:
            raise ValueError("Late-known actions need corrected point-in-time dataset")
