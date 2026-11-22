"""Summary features of a probability distribution over Fed outcomes.

One implementation serves both the market distribution (``extract_event_features``
in ``forecast_models.py``) and each wallet cluster's implied distribution
(``cluster_regression.py``). That keeps the "M features per distribution" in the
N x M design identical in meaning for the market and for every cluster.

Input is long: one row per (group..., outcome) with a ``probability`` column and
a ``move`` column in basis points. Probabilities are renormalized within each
group, because snapshots sometimes omit a contract.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12
TAIL_THRESHOLD_BP = 50.0

# Level features of one distribution.
LEVEL_FEATURES = [
    "expected_move",          # probability-weighted signed move (bp)
    "expected_abs_move",      # expected size of the move (bp)
    "move_variance",          # dispersion of the move (bp^2)
    "move_std",               # sqrt(move_variance), same units as the move
    "entropy",                # Shannon entropy (nats)
    "entropy_normalized",     # entropy / log(K): comparable across outcome counts
    "max_probability",        # probability of the modal outcome
    "probability_increase",
    "probability_decrease",
    "probability_no_change",
    "tail_probability",       # P(|move| >= 50 bp): large-surprise mass
]

# Features of a distribution relative to a reference (the market).
RELATIVE_FEATURES = [
    "expected_move_gap",      # E_c[move] - E_mkt[move]; directional view
    "move_std_gap",           # extra/less dispersion than the market
    "tail_probability_gap",   # extra/less large-move mass than the market
    "kl_from_market",         # KL(cluster || market); size of disagreement
    "total_variation",        # 0.5 * sum |p_c - p_mkt|; bounded in [0, 1]
]


def _normalize(frame: pd.DataFrame, keys: list[str], column: str) -> pd.Series:
    total = frame.groupby(keys)[column].transform("sum")
    return frame[column] / total.where(total > 0)


def summarize(frame: pd.DataFrame, keys: list[str],
              probability: str = "probability", move: str = "move") -> pd.DataFrame:
    """Return one row per group with :data:`LEVEL_FEATURES` plus ``outcome_count``."""
    data = frame.dropna(subset=[probability, move]).copy()
    data["p"] = _normalize(data, keys, probability)
    data = data.dropna(subset=["p"])
    m = data[move].astype(float)
    p = data["p"]
    data["_m"] = p * m
    data["_abs"] = p * m.abs()
    data["_sq"] = p * m.pow(2)
    data["_h"] = -p * np.log(p.clip(lower=EPS))
    data["_inc"] = p.where(m > 0, 0.0)
    data["_dec"] = p.where(m < 0, 0.0)
    data["_nc"] = p.where(m == 0, 0.0)
    data["_tail"] = p.where(m.abs() >= TAIL_THRESHOLD_BP, 0.0)
    out = data.groupby(keys, as_index=False).agg(
        expected_move=("_m", "sum"), expected_abs_move=("_abs", "sum"),
        expected_square_move=("_sq", "sum"), entropy=("_h", "sum"),
        max_probability=("p", "max"), outcome_count=("p", "size"),
        probability_increase=("_inc", "sum"), probability_decrease=("_dec", "sum"),
        probability_no_change=("_nc", "sum"), tail_probability=("_tail", "sum"))
    out["move_variance"] = (out["expected_square_move"] - out["expected_move"].pow(2)).clip(lower=0)
    out["move_std"] = np.sqrt(out["move_variance"])
    k = out["outcome_count"].astype(float)
    out["entropy_normalized"] = np.where(k > 1, out["entropy"] / np.log(k.clip(lower=2)), 0.0)
    return out


def compare(frame: pd.DataFrame, keys: list[str], reference: str,
            probability: str = "probability", move: str = "move") -> pd.DataFrame:
    """Return :data:`RELATIVE_FEATURES` of ``probability`` versus ``reference``.

    Both columns live on the same long rows, so the outcome sets are aligned by
    construction. Both are renormalized over the outcomes present in the group.
    """
    data = frame.dropna(subset=[probability, reference, move]).copy()
    data["p"] = _normalize(data, keys, probability)
    data["q"] = _normalize(data, keys, reference)
    data = data.dropna(subset=["p", "q"])
    data["_kl"] = data["p"] * (np.log(data["p"].clip(lower=EPS)) - np.log(data["q"].clip(lower=EPS)))
    data["_tv"] = 0.5 * (data["p"] - data["q"]).abs()
    divergence = data.groupby(keys, as_index=False).agg(
        kl_from_market=("_kl", "sum"), total_variation=("_tv", "sum"))
    own = summarize(data, keys, "p", move)
    ref = summarize(data, keys, "q", move)
    merged = own.merge(ref, on=keys, suffixes=("", "_ref"))
    for name in ("expected_move", "move_std", "tail_probability"):
        merged[f"{name}_gap"] = merged[name] - merged[f"{name}_ref"]
    gaps = merged[keys + ["expected_move_gap", "move_std_gap", "tail_probability_gap"]]
    return divergence.merge(gaps, on=keys, validate="one_to_one")[keys + RELATIVE_FEATURES]
