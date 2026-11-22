"""Shared Fed-outcome vocabulary for every model and wallet module.

Two problems motivated this module:

* Datasets spell the same outcome differently (``"No change"`` in the wallet
  pilot, ``"no change"`` in ``forward_probabilities.csv``). Always pass labels
  through :func:`normalize_outcome` before joining or mapping.
* Open-ended buckets need one documented convention. ``"25+ bps increase"``
  means "an increase of at least 25 bp", so it maps to its lower bound, +25 bp
  (it was previously mapped to +50 bp). ``"50+"`` and ``"75+"`` buckets follow
  the same lower-bound rule.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Signed policy-rate move in basis points; keys are normalized labels.
OUTCOME_MOVE: dict[str, float] = {
    "75+ bps decrease": -75.0,
    "50+ bps decrease": -50.0,
    "50 bps decrease": -50.0,
    "25 bps decrease": -25.0,
    "no change": 0.0,
    "25 bps increase": 25.0,
    "25+ bps increase": 25.0,
    "50 bps increase": 50.0,
    "50+ bps increase": 50.0,
    "75 bps increase": 75.0,
}


def normalize_outcome(label):
    """Lower-case, trim and collapse whitespace; missing stays missing."""
    if label is None or (isinstance(label, float) and np.isnan(label)):
        return label
    return " ".join(str(label).strip().lower().split())


def normalize_outcomes(labels: pd.Series) -> pd.Series:
    return labels.map(normalize_outcome)


def outcome_move(labels: pd.Series) -> pd.Series:
    """Map labels of any capitalization to basis points; unknown -> NaN."""
    return normalize_outcomes(labels).map(OUTCOME_MOVE)
