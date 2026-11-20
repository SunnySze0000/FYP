import numpy as np
import pandas as pd
import pytest

from eventlens.analysis.calibration import favourite_trades, win_rate_bounds
from eventlens.stats import cluster_mean_test, detectable_correlation, spearman_test


def test_detectable_correlation_for_27_events():
    assert detectable_correlation(27) == pytest.approx(0.517, abs=0.01)
    assert detectable_correlation(1000) < 0.1


def test_spearman_detects_monotone_relation_and_not_noise():
    x = np.arange(50, dtype=float)
    assert spearman_test(x, x**3, resamples=500).p_value < 0.01
    rng = np.random.default_rng(1)
    assert spearman_test(rng.normal(size=50), rng.normal(size=50), resamples=500).p_value > 0.01


def test_cluster_mean_uses_cluster_count():
    values = np.array([1.0, 1.0, 1.0, -1.0])
    estimate = cluster_mean_test(values, np.array(["a", "a", "a", "b"]), resamples=200)
    assert estimate.value == pytest.approx(0.5)
    assert estimate.n == 2


def test_win_rate_bounds_for_perfect_record():
    low, high = win_rate_bounds(100, 100)
    assert high == 1.0 and 0.96 < low < 0.97


def test_favourite_trades_take_correct_side_and_payoff():
    panel = pd.DataFrame({
        "market_id": [1, 2], "meeting_month": ["2024-01", "2024-01"], "date": pd.to_datetime(["2024-01-01"] * 2),
        "days_to_event": [10, 10], "price": [0.9, 0.15], "final_outcome": [1, 1],
    })
    trades = favourite_trades(panel, days_before=7, low=0.8, high=0.95, cost_per_share=0.0).set_index("market_id")
    assert trades.loc[1, "side"] == "YES" and trades.loc[1, "return"] == pytest.approx(1 / 0.9 - 1)
    assert trades.loc[2, "side"] == "NO" and trades.loc[2, "return"] == pytest.approx(-1.0)
