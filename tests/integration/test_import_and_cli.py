from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from etf_lab import cli
from etf_lab.data.importer import import_data
from etf_lab.instruments.registry import InstrumentRegistry


def test_csv_parquet_cache(
    tmp_path: Path, bars: pd.DataFrame, registry: InstrumentRegistry
) -> None:
    source = tmp_path / "input.csv"
    bars.to_csv(source, index=False)
    a, report = import_data(source, tmp_path, registry)
    b, _ = import_data(source, tmp_path, registry)
    assert a == b and report["status"] == "PASS"
    assert len(pd.read_parquet(a)) == len(bars)
    pq = tmp_path / "input.parquet"
    bars.to_parquet(pq, index=False)
    c, _ = import_data(pq, tmp_path, registry)
    pd.testing.assert_frame_equal(pd.read_parquet(a), pd.read_parquet(c), check_dtype=False)
    with pytest.raises(ValueError, match="raw"):
        import_data(source, tmp_path, registry, adjustment="adjusted")


def test_live_rejected() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["live"])
    assert result.exit_code == 2
    assert "Live trading is intentionally unavailable" in result.stdout
    assert next(c for c in cli.app.registered_commands if c.callback == cli.live).hidden


def test_offline_diagnostics() -> None:
    runner = CliRunner()
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 0
    assert runner.invoke(cli.app, ["instruments"]).exit_code == 0
    for command in ["download", "record"]:
        assert runner.invoke(cli.app, [command]).exit_code == 2
