"""Phase 3a: are Polymarket prices calibrated, and is any mispricing tradeable?

The panel has one row per (market, snapshot date) before the announcement.
Rows of one meeting share an outcome, so all uncertainty is computed by
resampling whole meetings (clusters), never individual rows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from eventlens.stats import cluster_mean_test

DEFAULT_BINS = (0.0, 0.02, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.98, 1.0)
HORIZON_BUCKETS = ((1, 7), (8, 30), (31, 90), (91, 400))


def market_day_panel(probabilities: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Pre-announcement market prices with days remaining and the resolved label."""
    panel = probabilities.merge(calendar[["meeting_month", "announcement_date"]], on="meeting_month")
    panel["days_to_event"] = (panel["announcement_date"] - panel["date"]).dt.days
    panel = panel.loc[panel["days_to_event"] >= 1].copy()
    panel["price"] = panel["market_probability"].clip(0, 1)
    return panel


def calibration_table(panel: pd.DataFrame, bins: tuple[float, ...] = DEFAULT_BINS) -> pd.DataFrame:
    """Observed YES frequency against average price within price bins."""
    binned = panel.assign(price_bin=pd.cut(panel["price"], bins, include_lowest=True))
    table = binned.groupby("price_bin", observed=True).agg(
        rows=("price", "size"),
        markets=("market_id", "nunique"),
        meetings=("meeting_month", "nunique"),
        mean_price=("price", "mean"),
        yes_rate=("final_outcome", "mean"),
    )
    table["gap"] = table["yes_rate"] - table["mean_price"]
    return table.reset_index()


def brier_by_horizon(panel: pd.DataFrame) -> pd.DataFrame:
    """Brier score of prices vs. a constant base-rate forecast, by days to event."""
    rows = []
    for low, high in HORIZON_BUCKETS:
        part = panel.loc[panel["days_to_event"].between(low, high)]
        if part.empty:
            continue
        outcome = part["final_outcome"].to_numpy()
        price_brier = np.mean((part["price"] - outcome) ** 2)
        base_brier = np.mean((outcome.mean() - outcome) ** 2)
        rows.append(
            {
                "days_to_event": f"{low}-{high}",
                "rows": len(part),
                "meetings": part["meeting_month"].nunique(),
                "brier_price": price_brier,
                "brier_base_rate": base_brier,
                "skill_vs_base_rate": 1 - price_brier / base_brier,
            }
        )
    return pd.DataFrame(rows)


PRICE_BANDS = ((0.60, 0.80), (0.80, 0.90), (0.90, 0.95), (0.95, 0.99))


def favourite_trades(
    panel: pd.DataFrame, days_before: int, low: float, high: float, cost_per_share: float
) -> pd.DataFrame:
    """One trade per market: buy whichever side is priced in [low, high).

    Uses the latest snapshot at least `days_before` days before the
    announcement. Buying YES at p pays 1 if YES; buying NO costs 1 - p.
    `cost_per_share` is added to the entry price for spread and fees.
    """
    eligible = panel.loc[panel["days_to_event"] >= days_before]
    entry = eligible.sort_values("date").groupby("market_id").tail(1)
    yes_side = entry["price"].between(low, high, inclusive="left")
    no_side = (1 - entry["price"]).between(low, high, inclusive="left")
    trades = entry.loc[yes_side | no_side].copy()
    trades["side"] = np.where(yes_side[yes_side | no_side], "YES", "NO")
    trades["entry_price"] = np.where(trades["side"].eq("YES"), trades["price"], 1 - trades["price"])
    trades["entry_cost"] = (trades["entry_price"] + cost_per_share).clip(upper=1.0)
    won = np.where(trades["side"].eq("YES"), trades["final_outcome"].eq(1), trades["final_outcome"].eq(0))
    trades["payoff"] = won.astype(float)
    trades["return"] = trades["payoff"] / trades["entry_cost"] - 1
    return trades


def win_rate_bounds(wins: int, trials: int, level: float = 0.95) -> tuple[float, float]:
    """Clopper-Pearson interval for a win rate."""
    alpha = 1 - level
    low = stats.beta.ppf(alpha / 2, wins, trials - wins + 1) if wins > 0 else 0.0
    high = stats.beta.ppf(1 - alpha / 2, wins + 1, trials - wins) if wins < trials else 1.0
    return float(low), float(high)


def favourite_strategy_grid(
    panel: pd.DataFrame,
    days_before: tuple[int, ...] = (1, 7, 30),
    bands: tuple[tuple[float, float], ...] = PRICE_BANDS,
    cost_per_share: float = 0.01,
) -> pd.DataFrame:
    """Hold-to-resolution results of the favourite rule per price band.

    A rule that never lost in-sample can look significant while being one
    surprise away from a loss. The decisive column is therefore
    `edge_credible`: the lower 95% bound of the win rate must exceed the
    break-even win rate (the average entry cost per share).
    """
    rows = []
    for days in days_before:
        for low, high in bands:
            trades = favourite_trades(panel, days, low, high, cost_per_share)
            if trades.empty:
                continue
            estimate = cluster_mean_test(trades["return"].to_numpy(), trades["meeting_month"].to_numpy())
            wins = int(trades["payoff"].sum())
            win_low, _ = win_rate_bounds(wins, len(trades))
            breakeven = float(trades["entry_cost"].mean())
            rows.append(
                {
                    "days_before": days,
                    "price_band": f"{low:.2f}-{high:.2f}",
                    "trades": len(trades),
                    "meetings": estimate.n,
                    "win_rate": wins / len(trades),
                    "win_rate_ci_low": win_low,
                    "breakeven_win_rate": breakeven,
                    "edge_credible": win_low > breakeven,
                    "mean_return": estimate.value,
                    "return_ci_low": estimate.ci_low,
                    "return_ci_high": estimate.ci_high,
                }
            )
    return pd.DataFrame(rows)


def chronological_split_check(
    panel: pd.DataFrame, days_before: int, low: float, high: float, cost_per_share: float = 0.01
) -> pd.DataFrame:
    """Mean return of one rule in the earlier and later halves of meetings."""
    trades = favourite_trades(panel, days_before, low, high, cost_per_share)
    meetings = sorted(trades["meeting_month"].unique())
    midpoint = meetings[len(meetings) // 2]
    trades["period"] = np.where(trades["meeting_month"] < midpoint, "first_half", "second_half")
    return (
        trades.groupby("period")
        .agg(trades=("return", "size"), meetings=("meeting_month", "nunique"),
             mean_return=("return", "mean"), losses=("payoff", lambda x: int((x == 0).sum())))
        .reset_index()
    )
