"""Phase 2: does Polymarket's pre-meeting view explain the equity reaction?

The unit of observation is the meeting, not the day. Hypotheses are fixed in
advance (`HYPOTHESES`) to avoid searching many specifications on 27 events.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from eventlens.features.returns import event_windows
from eventlens.stats import detectable_correlation, spearman_test


@dataclass(frozen=True)
class Hypothesis:
    name: str
    feature: str
    target: str
    expected_sign: int
    rationale: str


HYPOTHESES = (
    Hypothesis("surprise_size_moves_market", "abs_surprise_bp", "event_abs_z", +1,
               "Larger policy surprises cause larger announcement-day moves."),
    Hypothesis("surprise_direction", "surprise_bp", "event_z", -1,
               "Hawkish surprises (higher rate than expected) lower equity prices."),
    Hypothesis("uncertainty_moves_market", "entropy", "event_abs_z", +1,
               "More pre-meeting uncertainty means a larger announcement-day move."),
    Hypothesis("uncertainty_raises_post_vol", "entropy", "rv_ratio", +1,
               "More uncertainty raises volatility over the five days after the meeting."),
    Hypothesis("low_confidence_moves_market", "log_loss", "event_abs_z", +1,
               "Outcomes the market found unlikely produce larger moves."),
)


def build_event_dataset(event_table: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    """Join meeting expectations with the asset's announcement-window moves."""
    windows = event_windows(series, event_table["announcement_date"])
    data = event_table.merge(windows, on="announcement_date", how="inner")
    data = data.loc[data["distribution_valid"].astype(bool)].copy()
    data["abs_surprise_bp"] = data["surprise_bp"].abs()
    return data


def test_hypotheses(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    rows = []
    for hypothesis in HYPOTHESES:
        estimate = spearman_test(data[hypothesis.feature], data[hypothesis.target])
        rows.append(
            {
                "ticker": ticker,
                "hypothesis": hypothesis.name,
                "feature": hypothesis.feature,
                "target": hypothesis.target,
                "expected_sign": hypothesis.expected_sign,
                **estimate.as_dict("rho_"),
                "sign_as_expected": estimate.value * hypothesis.expected_sign > 0,
                "detectable_rho_80pct_power": detectable_correlation(estimate.n),
            }
        )
    return pd.DataFrame(rows)


def power_table(sample_sizes: tuple[int, ...] = (10, 27, 50, 100, 200, 500, 1000)) -> pd.DataFrame:
    """Smallest correlation detectable with 80% power at alpha 0.05."""
    return pd.DataFrame(
        {"n_independent_events": sample_sizes,
         "min_detectable_abs_rho": [detectable_correlation(n) for n in sample_sizes]}
    )
