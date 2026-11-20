import math

import pandas as pd

from eventlens.data import fomc
from eventlens.data.taxonomy import bucket_for, normalise_label, representative_move
from eventlens.validation import checks


def make_probabilities(rows):
    frame = pd.DataFrame(rows, columns=["date", "meeting_month", "outcome", "market_id", "market_probability", "final_outcome"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["move_bp"] = frame["outcome"].map(representative_move)
    return frame


def test_labels_are_normalised_and_mapped():
    assert normalise_label("  No   Change ") == "no change"
    assert bucket_for("25+ bps increase").contains(50)
    assert not bucket_for("25 bps increase").contains(50)
    assert bucket_for("50+ bps decrease").contains(-75)
    assert math.isnan(representative_move("other"))


def test_every_open_bucket_contains_its_representative_move():
    for label in ["25+ bps increase", "50+ bps increase", "50+ bps decrease", "75+ bps decrease"]:
        bucket = bucket_for(label)
        assert bucket.contains(bucket.representative_bp)


def test_calendar_is_sorted_and_unique():
    dates = fomc.calendar()["announcement_date"]
    assert dates.is_monotonic_increasing and dates.is_unique


def test_probability_sum_check_flags_only_bad_snapshots():
    probs = make_probabilities([
        ("2024-01-01", "2024-01", "no change", 1, 0.9, 1),
        ("2024-01-01", "2024-01", "25 bps decrease", 2, 0.1, 0),
        ("2024-01-02", "2024-01", "no change", 1, 0.9, 1),
        ("2024-01-02", "2024-01", "25 bps decrease", 2, 0.5, 0),
    ])
    failures = checks.probability_sums(probs)
    assert failures["date"].tolist() == [pd.Timestamp("2024-01-02")]


def test_resolution_check_requires_exactly_one_winner():
    probs = make_probabilities([
        ("2024-01-01", "2024-01", "no change", 1, 0.9, 1),
        ("2024-01-01", "2024-01", "25 bps decrease", 2, 0.1, 1),
    ])
    assert checks.resolution_consistency(probs)["meeting_month"].tolist() == ["2024-01"]


def test_gap_check_reports_long_gaps():
    probs = make_probabilities([
        ("2024-01-01", "2024-01", "no change", 1, 1.0, 1),
        ("2024-01-20", "2024-01", "no change", 1, 1.0, 1),
    ])
    assert checks.snapshot_gaps(probs)["gap_days"].tolist() == [19.0]
