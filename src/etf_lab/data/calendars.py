from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd

from etf_lab.config import Timeframe

MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 1440}
# NASDAQ uses the library's US equities alias; auction details are outside this bar model.
CALENDARS = {
    "XNYS": "XNYS",
    "ARCX": "XNYS",
    "XNAS": "NASDAQ",
    "XLON": "XLON",
    "XETR": "XETR",
    "XAMS": "XAMS",
    "XPAR": "XPAR",
}


@lru_cache(maxsize=64)
def schedule(mic: str, start: str, end: str) -> pd.DataFrame:
    if mic not in CALENDARS:
        raise ValueError(f"Unsupported MIC calendar: {mic}")
    # Library requires a nonempty construction span, including for one-day queries.
    cal = xcals.get_calendar(
        CALENDARS[mic],
        start=str((pd.Timestamp(start) - pd.Timedelta(days=7)).date()),
        end=str((pd.Timestamp(end) + pd.Timedelta(days=7)).date()),
    )
    return cal.schedule.loc[start:end, ["open", "close"]].copy()


def expected_bars(mic: str, start: str, end: str, timeframe: Timeframe) -> pd.DataFrame:
    rows = []
    for day, session in schedule(mic, start, end).iterrows():
        op, cl = session["open"], session["close"]
        ends = (
            [cl]
            if timeframe == "1d"
            else list(pd.date_range(op, cl, freq=f"{MINUTES[timeframe]}min")[1:])
        )
        if not ends or ends[-1] != cl:
            ends.append(cl)
        previous = op
        for ts in ends:
            rows.append(
                {
                    "timestamp": ts,
                    "bar_start": previous,
                    "session": str(pd.Timestamp(str(day)).date()),
                    "session_open": op,
                    "session_close": cl,
                }
            )
            previous = ts
    return pd.DataFrame(rows)
