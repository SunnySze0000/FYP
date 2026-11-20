"""Phase 1: reproduce known facts before trusting any new result.

If the pipeline cannot recover (a) the official Fed decisions from market
resolution and (b) the documented rise in equity volatility on FOMC days,
something upstream is wrong and later findings are not interpretable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eventlens.features.returns import event_windows, non_event_days
from eventlens.stats import DEFAULT_RESAMPLES, DEFAULT_SEED


def decision_reconciliation(event_table: pd.DataFrame) -> dict:
    verified = event_table.loc[event_table["official_verified"]]
    return {
        "meetings_with_markets": len(event_table),
        "meetings_verifiable": len(verified),
        "resolutions_matching_fed": int(verified["resolution_matches_official"].sum()),
    }


def fomc_day_volatility(
    series: pd.DataFrame,
    event_dates: pd.Series,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Compare squared standardised returns on FOMC days with placebo days.

    The placebo distribution draws the same number of random non-event
    trading days many times. The p-value is the share of placebo draws whose
    mean squared z is at least the observed FOMC-day value.
    """
    events = event_windows(series, event_dates)
    others = non_event_days(series, event_dates)
    observed = float(np.mean(events["event_z"] ** 2))
    pool = (others["z"] ** 2).to_numpy()
    rng = np.random.default_rng(seed)
    placebo = np.array([pool[rng.integers(0, len(pool), len(events))].mean() for _ in range(resamples)])
    return {
        "event_days": len(events),
        "event_mean_z2": observed,
        "non_event_mean_z2": float(pool.mean()),
        "variance_ratio": observed / float(pool.mean()),
        "placebo_p_value": float((np.sum(placebo >= observed) + 1) / (resamples + 1)),
        "event_mean_return_pct": float(events["event_return"].mean() * 100),
    }
