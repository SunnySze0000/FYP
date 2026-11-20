"""Cross-market calibration on thousands of resolved Polymarket markets.

This is where sample size stops being the binding constraint. The trading
rule is evaluated walk-forward: a calibration map is learnt only from
markets that closed before the test month (minus the horizon), then applied
to that month's markets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eventlens.config import Paths
from eventlens.stats import cluster_mean_test

HORIZONS_DAYS = (1, 7, 30)
PRICE_BINS = (0.0, 0.03, 0.07, 0.15, 0.30, 0.50, 0.70, 0.85, 0.93, 0.97, 1.0)
SMOOTHING_WEIGHT = 20.0


def has_universe_data(paths: Paths) -> bool:
    return (paths.universe / "markets.csv").exists() and (paths.universe / "prices.csv").exists()


def build_panel(paths: Paths, horizons_days: tuple[int, ...] = HORIZONS_DAYS) -> pd.DataFrame:
    markets = pd.read_csv(paths.universe / "markets.csv", dtype={"market_id": str, "event_id": str})
    prices = pd.read_csv(paths.universe / "prices.csv", dtype={"market_id": str})
    return panel_from_frames(markets, prices, horizons_days)


def panel_from_frames(markets: pd.DataFrame, prices: pd.DataFrame,
                      horizons_days: tuple[int, ...] = HORIZONS_DAYS) -> pd.DataFrame:
    """One row per (market, horizon): the last YES price at least `horizon` days before close."""
    markets = markets.copy()
    close = pd.to_datetime(markets["closed_time"].fillna(markets["end_date"]), utc=True, format="mixed")
    markets["close_time"] = close
    prices = prices.copy()
    prices["timestamp_utc"] = pd.to_datetime(prices["timestamp_utc"], utc=True, format="mixed")
    prices = prices.loc[prices["yes_price"].between(0.001, 0.999)].sort_values("timestamp_utc")
    rows = []
    for horizon in horizons_days:
        probe = markets[["market_id", "close_time"]].dropna().copy()
        probe["timestamp_utc"] = probe["close_time"] - pd.Timedelta(days=horizon)
        matched = pd.merge_asof(
            probe.sort_values("timestamp_utc"), prices, on="timestamp_utc", by="market_id", direction="backward",
            tolerance=pd.Timedelta(days=3),
        )
        rows.append(matched.dropna(subset=["yes_price"]).assign(horizon_days=horizon))
    panel = pd.concat(rows, ignore_index=True).merge(
        markets[["market_id", "event_id", "category", "yes_won", "volume_usd"]], on="market_id")
    panel["close_month"] = panel["close_time"].dt.tz_localize(None).dt.to_period("M")
    panel["price_bin"] = pd.cut(panel["yes_price"], PRICE_BINS, include_lowest=True)
    return panel.rename(columns={"timestamp_utc": "price_time", "yes_price": "price"})


def coverage(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.groupby("horizon_days").agg(
        markets=("market_id", "nunique"), events=("event_id", "nunique"),
        first_close=("close_time", "min"), last_close=("close_time", "max"),
        yes_rate=("yes_won", "mean"),
    ).reset_index()


def calibration_by_bucket(panel: pd.DataFrame) -> pd.DataFrame:
    table = panel.groupby(["horizon_days", "price_bin"], observed=True).agg(
        markets=("market_id", "size"), mean_price=("price", "mean"), yes_rate=("yes_won", "mean"))
    table["gap"] = table["yes_rate"] - table["mean_price"]
    table["gap_se"] = np.sqrt(table["yes_rate"] * (1 - table["yes_rate"]) / table["markets"])
    return table.reset_index()


def fit_calibration_map(train: pd.DataFrame) -> pd.DataFrame:
    """Mispricing per price bin: `gap` = observed YES rate - mean price.

    The gap is shrunk towards zero (no mispricing) for thin bins. `se` is its
    binomial standard error. A market's fair value is its own price plus its
    bin's gap, so markets are never pulled towards the bin centre.
    """
    grouped = train.groupby("price_bin", observed=False).agg(
        wins=("yes_won", "sum"), n=("yes_won", "size"), mean_price=("price", "mean"))
    n = grouped["n"].astype(float)
    raw_gap = (grouped["wins"] / n.replace(0, np.nan) - grouped["mean_price"]).fillna(0.0)
    gap = raw_gap * n / (n + SMOOTHING_WEIGHT)
    rate = (grouped["mean_price"].fillna(0.5) + gap).clip(0.001, 0.999)
    se = np.sqrt(rate * (1 - rate) / (n + SMOOTHING_WEIGHT))
    return pd.DataFrame({"gap": gap, "se": se})


def apply_rule(test: pd.DataFrame, calibration_map: pd.DataFrame, cost_per_share: float,
               min_edge: float, z_required: float = 2.0) -> pd.DataFrame:
    """Buy the side whose expected value beats cost by a margin that is
    both economically (`min_edge`) and statistically (`z_required` standard
    errors of the bin's gap) meaningful."""
    trades = test.copy()
    trades["fair"] = (trades["price"] + trades["price_bin"].map(calibration_map["gap"]).astype(float)).clip(0, 1)
    hurdle = np.maximum(min_edge, z_required * trades["price_bin"].map(calibration_map["se"]).astype(float))
    yes_edge = trades["fair"] - (trades["price"] + cost_per_share)
    no_edge = (1 - trades["fair"]) - (1 - trades["price"] + cost_per_share)
    trades["side"] = np.select([yes_edge >= hurdle, no_edge >= hurdle], ["YES", "NO"], default="")
    trades = trades.loc[trades["side"].ne("")].copy()
    trades["entry_cost"] = np.where(trades["side"].eq("YES"), trades["price"], 1 - trades["price"]) + cost_per_share
    won = np.where(trades["side"].eq("YES"), trades["yes_won"].eq(1), trades["yes_won"].eq(0))
    trades["return"] = won.astype(float) / trades["entry_cost"] - 1
    return trades


def walk_forward_trades(panel: pd.DataFrame, horizon_days: int, cost_per_share: float = 0.01,
                        min_edge: float = 0.02, min_train_markets: int = 300) -> pd.DataFrame:
    data = panel.loc[panel["horizon_days"].eq(horizon_days)]
    trades = []
    for month in sorted(data["close_month"].unique()):
        month_start = month.to_timestamp().tz_localize("UTC")
        train = data.loc[data["close_time"] < month_start - pd.Timedelta(days=horizon_days)]
        if len(train) < min_train_markets:
            continue
        test = data.loc[data["close_month"].eq(month)]
        trades.append(apply_rule(test, fit_calibration_map(train), cost_per_share, min_edge))
    return pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()


def walk_forward_rule(panel: pd.DataFrame, cost_per_share: float = 0.01, min_edge: float = 0.02) -> pd.DataFrame:
    rows = []
    for horizon in sorted(panel["horizon_days"].unique()):
        trades = walk_forward_trades(panel, horizon, cost_per_share, min_edge)
        if trades.empty:
            continue
        clusters = trades["event_id"].fillna(trades["market_id"]).to_numpy()
        estimate = cluster_mean_test(trades["return"].to_numpy(), clusters)
        monthly = trades.groupby("close_month")["return"].mean()
        rows.append({
            "horizon_days": horizon, "trades": len(trades), "events": estimate.n,
            "share_yes_side": float(trades["side"].eq("YES").mean()),
            "mean_return": estimate.value, "ci_low": estimate.ci_low, "ci_high": estimate.ci_high,
            "p_value": estimate.p_value, "test_months": len(monthly),
            "share_months_positive": float((monthly > 0).mean()),
        })
    return pd.DataFrame(rows)
