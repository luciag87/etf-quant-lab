from pathlib import Path

import yaml

from etf_lab.models import Instrument


class InstrumentRegistry:
    def __init__(self, instruments: list[Instrument]) -> None:
        self.items = {i.id: i for i in instruments}
        if len(self.items) != len(instruments):
            raise ValueError("Duplicate instrument identity")

    @classmethod
    def load(cls, path: Path) -> "InstrumentRegistry":
        return cls([Instrument.model_validate(i) for i in yaml.safe_load(path.read_text())])

    def resolve(
        self, symbol: str, mic: str | None = None, currency: str | None = None
    ) -> Instrument:
        found = [
            i
            for i in self.items.values()
            if (i.symbol == symbol or i.isin == symbol or i.id == symbol)
            and (mic is None or i.mic == mic)
            and (currency is None or i.currency == currency)
        ]
        if len(found) != 1:
            raise ValueError(f"Unknown or ambiguous instrument: {symbol}; supply MIC/currency")
        return found[0]
