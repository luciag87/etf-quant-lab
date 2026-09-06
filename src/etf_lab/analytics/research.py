"""Descriptive segmentation; never feeds future session results into a strategy."""

import numpy as np
import pandas as pd


def session_analysis(
    data: pd.DataFrame, large_gap: float = 0.01, flat_gap: float = 0.001
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = data.copy()
    after = (df.timestamp - df.session_open).dt.total_seconds() / 60
    before = (df.session_close - df.timestamp).dt.total_seconds() / 60
    # Disjoint bins: last 30 has precedence over last 90; boundary closes belong to prior bin.
    df["time_bucket"] = np.select(
        [after <= 30, after <= 60, before < 30, before < 90],
        ["first_30", "30_to_60", "last_30", "last_90_ex_last_30"],
        default="midday",
    )
    df["bar_intraday_return"] = df.close / df.open - 1
    by_time = df.groupby(["instrument_id", "time_bucket"]).bar_intraday_return.agg(
        observations="size", mean_return="mean", std_return="std"
    )
    sessions = df.groupby(["instrument_id", "session"], sort=True).agg(
        open=("open", "first"), close=("close", "last")
    )
    sessions["previous_close"] = sessions.groupby(level=0).close.shift()
    sessions["gap"] = sessions.open / sessions.previous_close - 1
    sessions["intraday_return"] = sessions.close / sessions.open - 1
    g = sessions.gap
    sessions["gap_bucket"] = np.select(
        [g < -large_gap, g < -flat_gap, g <= flat_gap, g <= large_gap, g > large_gap],
        ["large_down", "small_down", "flat", "small_up", "large_up"],
        default="unknown",
    )
    sessions["continuation"] = np.sign(g) * sessions.intraday_return
    return pd.DataFrame(by_time), sessions
