"""Price-based features around announcement dates.

All volatility normalisation uses returns strictly before the event day, so
standardised event-day moves are comparable across calm and turbulent years.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRE_WINDOW = 20
POST_WINDOW = 5


def single_ticker(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Trading-day series for one ticker with trailing volatility."""
    series = prices.loc[prices["ticker"].eq(ticker), ["date", "log_return"]].dropna()
    series = series.sort_values("date").reset_index(drop=True)
    series["pre_vol"] = series["log_return"].shift(1).rolling(PRE_WINDOW).std()
    series["z"] = series["log_return"] / series["pre_vol"]
    return series


def event_windows(series: pd.DataFrame, event_dates: pd.Series) -> pd.DataFrame:
    """Announcement-day and post-event statistics for each event date.

    Event dates that are not trading days, or lack enough history or future
    data, are dropped.
    """
    position = pd.Series(series.index, index=series["date"])
    returns = series["log_return"].to_numpy()
    rows = []
    for date in pd.to_datetime(event_dates):
        if date not in position.index:
            continue
        i = int(position[date])
        if i < PRE_WINDOW + 1 or i + POST_WINDOW > len(series):
            continue
        pre_vol = series.at[i, "pre_vol"]
        post = returns[i : i + POST_WINDOW]
        pre = returns[i - POST_WINDOW : i]
        rows.append(
            {
                "announcement_date": date,
                "event_return": returns[i],
                "pre_vol": pre_vol,
                "event_z": returns[i] / pre_vol,
                "event_abs_z": abs(returns[i] / pre_vol),
                "post_rv": float(np.sum(post**2)),
                "pre_rv": float(np.sum(pre**2)),
                "rv_ratio": float(np.sum(post**2) / (POST_WINDOW * pre_vol**2)),
            }
        )
    return pd.DataFrame(rows)


def non_event_days(series: pd.DataFrame, event_dates: pd.Series, buffer_days: int = 1) -> pd.DataFrame:
    """Trading days at least `buffer_days` trading days away from any event."""
    is_event = series["date"].isin(pd.to_datetime(event_dates))
    near = is_event.copy()
    for shift in range(1, buffer_days + 1):
        near |= is_event.shift(shift, fill_value=False) | is_event.shift(-shift, fill_value=False)
    return series.loc[~near & series["z"].notna()]
