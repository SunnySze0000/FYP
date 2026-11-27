"""Statistics helpers (numpy/pandas only): cluster bootstrap, Spearman, permutation tests."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def cluster_bootstrap_mean(values: pd.Series, groups: pd.Series, draws: int, seed: int,
                           level: float = 0.95) -> dict:
    """Mean of ``values`` with a CI from resampling whole groups (e.g. events) with replacement.

    Use it when observations inside a group are correlated: markets of the same Fed meeting,
    trades of the same market, and so on.
    """
    frame = pd.DataFrame({"v": np.asarray(values, float), "g": np.asarray(groups)}).dropna()
    if frame.empty:
        return {"mean": math.nan, "low": math.nan, "high": math.nan, "n": 0, "groups": 0, "p_two_sided": math.nan}
    sums = frame.groupby("g")["v"].agg(["sum", "count"])
    s, c = sums["sum"].to_numpy(), sums["count"].to_numpy()
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(s), size=(draws, len(s)))
    means = s[picks].sum(axis=1) / c[picks].sum(axis=1)
    alpha = (1 - level) / 2
    mean = float(s.sum() / c.sum())
    # two-sided p for "mean = 0" from the bootstrap distribution, centred on zero
    centred = means - mean
    p = float(np.mean(np.abs(centred) >= abs(mean))) if len(s) > 1 else math.nan
    return {"mean": mean, "low": float(np.quantile(means, alpha)), "high": float(np.quantile(means, 1 - alpha)),
            "n": int(c.sum()), "groups": int(len(s)), "p_two_sided": p}


def spearman(x, y) -> float:
    x, y = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def spearman_test(x, y, permutations: int, seed: int) -> dict:
    """Spearman rho with a one-sided permutation p-value (H1: rho > 0) and bootstrap CI."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    rho = spearman(x, y)
    if math.isnan(rho):
        return {"rho": rho, "p_one_sided": math.nan, "low": math.nan, "high": math.nan, "n": int(len(x))}
    rng = np.random.default_rng(seed)
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    null = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(permutations)])
    boot = []
    for _ in range(min(permutations, 1000)):
        idx = rng.integers(0, len(x), len(x))
        boot.append(spearman(x[idx], y[idx]))
    boot = np.array([b for b in boot if not math.isnan(b)])
    return {"rho": rho, "p_one_sided": float((np.sum(null >= rho) + 1) / (permutations + 1)),
            "low": float(np.quantile(boot, 0.025)), "high": float(np.quantile(boot, 0.975)), "n": int(len(x))}


def wilson_interval(successes: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return math.nan, math.nan
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half
