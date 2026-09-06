from pathlib import Path

import pandas as pd
import pytest

from etf_lab.config import LabConfig
from etf_lab.data.fixtures import fixture
from etf_lab.instruments.registry import InstrumentRegistry


@pytest.fixture
def registry() -> InstrumentRegistry:
    return InstrumentRegistry.load(Path(__file__).parents[1] / "config/universe.example.yaml")


@pytest.fixture
def bars() -> pd.DataFrame:
    return fixture(start="2024-01-02", end="2024-01-04")


@pytest.fixture
def config() -> LabConfig:
    c = LabConfig()
    c.strategy.volume_ratio_min = 0
    c.strategy.momentum_threshold = 0.0001
    return c
