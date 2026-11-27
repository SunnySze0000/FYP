"""H0: are Polymarket prices calibrated, and what is a fair YES probability for a given price?"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from walletlens.analytics.stats import wilson_interval

EPS = 0.005


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-np.asarray(x, float)))


@dataclass(frozen=True)
class FairValue:
    """``fair = sigmoid(a + b * logit(price))``. a=0, b=1 means the price is already fair.

    b < 1 means extremes are over-confident (long shots too expensive, favourites too cheap
    in probability terms); a shifts everything towards YES or NO.
    """

    a: float = 0.0
    b: float = 1.0
    n: int = 0
    fitted: bool = False

    def __call__(self, price):
        if not self.fitted:
            return np.asarray(price, float)
        return sigmoid(self.a + self.b * logit(price))

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "n": self.n, "fitted": self.fitted}


def price_at(prices: pd.DataFrame, markets: pd.DataFrame, seconds_before_close: int) -> pd.DataFrame:
    """Last YES price observed at or before ``close - h`` (and after the market opened)."""
    targets = markets[["market_id", "start_ts", "close_ts", "outcome_yes", "group_id"]].copy()
    targets["t"] = targets["close_ts"].astype("int64") - seconds_before_close
    targets = targets[targets["t"] > targets["start_ts"]].sort_values("t")
    series = prices.astype({"ts": "int64"}).sort_values("ts")
    merged = pd.merge_asof(targets, series.rename(columns={"ts": "t"}), on="t", by="market_id",
                           direction="backward")
    merged = merged.dropna(subset=["yes_price"])
    merged["horizon_s"] = seconds_before_close
    return merged


def calibration_points(prices: pd.DataFrame, markets: pd.DataFrame, horizons_days) -> pd.DataFrame:
    return pd.concat([price_at(prices, markets, int(d * 86_400)).assign(horizon_days=d) for d in horizons_days],
                     ignore_index=True)


def calibration_table(points: pd.DataFrame, bins: int) -> pd.DataFrame:
    if points.empty:
        return pd.DataFrame(columns=["horizon_days", "bucket", "n", "mean_price", "yes_rate", "yes_rate_low",
                                     "yes_rate_high", "gap"])
    edges = np.linspace(0, 1, bins + 1)
    frame = points.assign(bucket=pd.cut(points["yes_price"], edges, include_lowest=True))
    rows = []
    for (horizon, bucket), part in frame.groupby(["horizon_days", "bucket"], observed=True):
        n, hits = len(part), float(part["outcome_yes"].sum())
        low, high = wilson_interval(hits, n)
        rows.append({"horizon_days": horizon, "bucket": str(bucket), "n": n,
                     "mean_price": float(part["yes_price"].mean()), "yes_rate": hits / n,
                     "yes_rate_low": low, "yes_rate_high": high,
                     "gap": hits / n - float(part["yes_price"].mean())})
    return pd.DataFrame(rows)


def brier(points: pd.DataFrame) -> pd.DataFrame:
    if points.empty:
        return pd.DataFrame(columns=["horizon_days", "brier", "count"])
    return (points.assign(sq=(points["yes_price"] - points["outcome_yes"]) ** 2)
            .groupby("horizon_days")["sq"].agg(["mean", "count"]).rename(columns={"mean": "brier"}).reset_index())


def fit_fair_value(prices, outcomes, min_n: int = 100, iterations: int = 50) -> FairValue:
    """Logistic recalibration by IRLS. Falls back to identity with too little data."""
    p = np.asarray(prices, float)
    y = np.asarray(outcomes, float)
    if len(p) < min_n or len(np.unique(y)) < 2:
        return FairValue(n=int(len(p)))
    x = np.column_stack([np.ones_like(p), logit(p)])
    beta = np.array([0.0, 1.0])
    for _ in range(iterations):
        mu = sigmoid(x @ beta)
        w = np.clip(mu * (1 - mu), 1e-9, None)
        hessian = x.T @ (x * w[:, None]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(hessian, x.T @ (y - mu))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    if not np.all(np.isfinite(beta)):
        return FairValue(n=int(len(p)))
    return FairValue(a=float(beta[0]), b=float(beta[1]), n=int(len(p)), fitted=True)


def log_loss(p, y) -> float:
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(p) else math.nan
