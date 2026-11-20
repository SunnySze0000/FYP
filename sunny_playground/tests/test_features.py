import numpy as np
import pandas as pd
import pytest

from eventlens.features.events import distribution_features, pre_event_snapshot
from eventlens.features.returns import event_windows, single_ticker
from tests.test_data_layer import make_probabilities


def test_snapshot_never_uses_announcement_day_or_later():
    probs = make_probabilities([
        ("2024-03-18", "2024-03", "no change", 1, 0.6, 1),
        ("2024-03-19", "2024-03", "no change", 1, 0.7, 1),
        ("2024-03-20", "2024-03", "no change", 1, 1.0, 1),
    ])
    snapshot = pre_event_snapshot(probs, "2024-03", pd.Timestamp("2024-03-20"), snapshot_lag_days=1)
    assert snapshot["date"].unique().tolist() == [pd.Timestamp("2024-03-19")]


def test_distribution_features_match_hand_calculation():
    snapshot = make_probabilities([
        ("2024-03-19", "2024-03", "no change", 1, 0.75, 1),
        ("2024-03-19", "2024-03", "25 bps decrease", 2, 0.25, 0),
    ])
    features = distribution_features(snapshot, "no change", 0.0)
    assert features["expected_move_bp"] == pytest.approx(-6.25)
    assert features["p_realised"] == pytest.approx(0.75)
    assert features["surprise_bp"] == pytest.approx(6.25)
    assert features["entropy"] == pytest.approx(-(0.75 * np.log(0.75) + 0.25 * np.log(0.25)))


def test_invalid_distribution_is_not_rescaled():
    snapshot = make_probabilities([
        ("2024-03-19", "2024-03", "no change", 1, 0.40, 1),
        ("2024-03-19", "2024-03", "25 bps decrease", 2, 0.20, 0),
    ])
    features = distribution_features(snapshot, "no change", 0.0)
    assert not features["distribution_valid"]
    assert np.isnan(features["expected_move_bp"])


def test_small_unmapped_bucket_is_dropped_but_large_one_invalidates():
    rows = [("2024-11-06", "2024-11", "25 bps decrease", 1, 0.95, 1), ("2024-11-06", "2024-11", "other", 2, 0.04, 0)]
    assert distribution_features(make_probabilities(rows), "25 bps decrease", -25)["distribution_valid"]
    rows[1] = ("2024-11-06", "2024-11", "other", 2, 0.06, 0)
    rows[0] = ("2024-11-06", "2024-11", "25 bps decrease", 1, 0.94, 1)
    assert not distribution_features(make_probabilities(rows), "25 bps decrease", -25)["distribution_valid"]


def _prices(returns):
    dates = pd.bdate_range("2024-01-01", periods=len(returns))
    close = 100 * np.exp(np.cumsum(returns))
    frame = pd.DataFrame({"date": dates, "ticker": "SPY", "close": close})
    frame["log_return"] = np.log(frame["close"]).diff()
    return frame


def test_pre_event_volatility_ignores_event_day_and_future():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, 60)
    base = single_ticker(_prices(returns), "SPY")
    event_date = base["date"].iloc[40]
    shocked = returns.copy()
    shocked[41:] *= 10  # series row 40 holds returns[41] (row 0 is dropped)
    changed = single_ticker(_prices(shocked), "SPY")
    left = event_windows(base, pd.Series([event_date]))
    right = event_windows(changed, pd.Series([event_date]))
    assert left["pre_vol"].iloc[0] == pytest.approx(right["pre_vol"].iloc[0])
    assert right["event_abs_z"].iloc[0] > left["event_abs_z"].iloc[0]
