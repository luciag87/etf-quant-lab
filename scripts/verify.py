"""Offline gates; run with uv run python scripts/verify.py after uv sync."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for command in [
    ["ruff", "format", "--check"],
    ["ruff", "check"],
    ["mypy", "src"],
    ["pytest", "-q"],
]:
    subprocess.run([sys.executable, "-m", *command], cwd=root, check=True)
