"""Small, dependency-light statistical helpers.

Every test in the project reports an effect size with an interval, not just a
p-value, and every resampling routine takes an explicit seed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import stats

DEFAULT_SEED = 7
DEFAULT_RESAMPLES = 5000


@dataclass(frozen=True)
class Estimate:
    value: float
    ci_low: float
    ci_high: float
    p_value: float
    n: int

    def as_dict(self, prefix: str = "") -> dict:
        return {
            f"{prefix}value": self.value,
            f"{prefix}ci_low": self.ci_low,
            f"{prefix}ci_high": self.ci_high,
            f"{prefix}p_value": self.p_value,
            f"{prefix}n": self.n,
        }


def bootstrap_ci(
    data: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    resamples: int = DEFAULT_RESAMPLES,
    level: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    """Percentile bootstrap over the first axis of `data` (rows or clusters)."""
    rng = np.random.default_rng(seed)
    n = len(data)
    draws = np.array([statistic(data[rng.integers(0, n, n)]) for _ in range(resamples)])
    alpha = (1 - level) / 2
    return float(np.nanquantile(draws, alpha)), float(np.nanquantile(draws, 1 - alpha))


def spearman_test(
    x: np.ndarray, y: np.ndarray, resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED
) -> Estimate:
    """Spearman correlation with a permutation p-value and bootstrap interval."""
    x, y = _paired_finite(x, y)
    rho = float(stats.spearmanr(x, y).statistic)
    rng = np.random.default_rng(seed)
    null = np.array([stats.spearmanr(x, rng.permutation(y)).statistic for _ in range(resamples)])
    p_value = float((np.sum(np.abs(null) >= abs(rho)) + 1) / (resamples + 1))
    pairs = np.column_stack([x, y])
    low, high = bootstrap_ci(pairs, lambda s: stats.spearmanr(s[:, 0], s[:, 1]).statistic, resamples, seed=seed)
    return Estimate(rho, low, high, p_value, len(x))


def mean_test(values: np.ndarray, resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED) -> Estimate:
    """Mean with bootstrap interval and a sign-flip permutation p-value for H0: mean = 0."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    mean = float(values.mean())
    low, high = bootstrap_ci(values, np.mean, resamples, seed=seed)
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], size=(resamples, len(values)))
    null = (flips * values).mean(axis=1)
    p_value = float((np.sum(np.abs(null) >= abs(mean)) + 1) / (resamples + 1))
    return Estimate(mean, low, high, p_value, len(values))


def cluster_mean_test(
    values: np.ndarray, clusters: np.ndarray, resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED
) -> Estimate:
    """Mean of `values` with uncertainty from resampling whole clusters.

    Use when observations within a cluster (e.g. markets of one FOMC meeting)
    are not independent. The p-value sign-flips whole clusters.
    """
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    labels = np.unique(clusters)
    sums = np.array([values[clusters == label].sum() for label in labels])
    counts = np.array([np.sum(clusters == label) for label in labels])
    mean = float(sums.sum() / counts.sum())
    rng = np.random.default_rng(seed)
    k = len(labels)
    draws = []
    for _ in range(resamples):
        pick = rng.integers(0, k, k)
        draws.append(sums[pick].sum() / counts[pick].sum())
    low, high = np.quantile(draws, [0.025, 0.975])
    centred = sums - mean * counts
    flips = rng.choice([-1.0, 1.0], size=(resamples, k))
    null = (flips * centred).sum(axis=1) / counts.sum()
    p_value = float((np.sum(np.abs(null) >= abs(mean)) + 1) / (resamples + 1))
    return Estimate(mean, float(low), float(high), p_value, int(k))


def detectable_correlation(n: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest |correlation| a two-sided test detects with the given power (Fisher z)."""
    z_needed = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return float(np.tanh(z_needed / np.sqrt(n - 3)))


def _paired_finite(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    return x[keep], y[keep]
