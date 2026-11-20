"""One row per FOMC meeting: what Polymarket expected just before it.

Timing rule: the snapshot used for a meeting is the latest one dated at
least `snapshot_lag_days` calendar days before the announcement date. With
the default of 1 day, a snapshot stamped 00:00 UTC on the day before the
announcement is the latest allowed, so it cannot contain the 14:00 ET
decision even if daily stamps mark the end of the period rather than the
start.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eventlens.data.taxonomy import bucket_for
from eventlens.validation.checks import PROBABILITY_SUM_TOLERANCE

MAX_UNMAPPED_MASS = 0.05


def resolve_meetings(probabilities: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Realised outcome of each meeting from market resolution, checked against the Fed."""
    markets = probabilities.drop_duplicates("market_id")
    resolved = (
        markets.loc[markets["final_outcome"].eq(1), ["meeting_month", "outcome"]]
        .groupby("meeting_month")["outcome"]
        .agg(lambda labels: labels.iloc[0] if len(labels) == 1 else None)
        .rename("resolved_outcome")
        .reset_index()
    )
    table = calendar.merge(resolved, on="meeting_month", how="inner")
    table["polymarket_move_bp"] = table["resolved_outcome"].map(
        lambda label: bucket_for(label).representative_bp if label else np.nan
    )
    table["official_verified"] = table["official_move_bp"].notna()
    table["resolution_matches_official"] = [
        _bucket_contains(label, official)
        for label, official in zip(table["resolved_outcome"], table["official_move_bp"])
    ]
    table["realised_move_bp"] = table["official_move_bp"].astype(float).fillna(table["polymarket_move_bp"])
    return table


def _bucket_contains(label: str | None, official: float | None) -> bool | None:
    if label is None or official is None or pd.isna(official):
        return None
    return bucket_for(label).contains(float(official))


def pre_event_snapshot(
    probabilities: pd.DataFrame, meeting_month: str, announcement_date: pd.Timestamp, snapshot_lag_days: int = 1
) -> pd.DataFrame:
    """Outcome probabilities for one meeting from the latest allowed snapshot."""
    cutoff = announcement_date - pd.Timedelta(days=snapshot_lag_days)
    rows = probabilities.loc[
        probabilities["meeting_month"].eq(meeting_month) & probabilities["date"].le(cutoff)
    ]
    if rows.empty:
        return rows
    return rows.loc[rows["date"].eq(rows["date"].max())]


def distribution_features(snapshot: pd.DataFrame, realised_label: str, realised_move_bp: float) -> dict:
    """Summaries of one pre-event probability distribution.

    Probabilities are renormalised only when their sum is within tolerance of
    1 and unmapped buckets (such as "other") hold at most
    `MAX_UNMAPPED_MASS`; otherwise the distribution features are left missing
    and the `distribution_valid` flag is False.
    """
    total = snapshot["market_probability"].sum()
    mapped = snapshot.loc[snapshot["move_bp"].notna()]
    unmapped_mass = total - mapped["market_probability"].sum()
    valid = abs(total - 1) <= PROBABILITY_SUM_TOLERANCE and unmapped_mass <= MAX_UNMAPPED_MASS
    features = {
        "probability_sum": total,
        "unmapped_mass": unmapped_mass,
        "outcomes_listed": len(snapshot),
        "distribution_valid": valid,
    }
    if not valid:
        return features | dict.fromkeys(
            ["expected_move_bp", "move_std_bp", "entropy", "p_realised", "surprise_bp", "log_loss"], np.nan
        )
    p = mapped["market_probability"].to_numpy()
    p = p / p.sum()
    moves = mapped["move_bp"].to_numpy()
    expected = float(p @ moves)
    p_realised = float(p[mapped["outcome"].to_numpy() == realised_label].sum())
    return features | {
        "expected_move_bp": expected,
        "move_std_bp": float(np.sqrt(p @ (moves - expected) ** 2)),
        "entropy": float(-(p[p > 0] * np.log(p[p > 0])).sum()),
        "p_realised": p_realised,
        "surprise_bp": realised_move_bp - expected,
        "log_loss": float(-np.log(max(p_realised, 1e-6))),
    }


def build_event_table(
    probabilities: pd.DataFrame, calendar: pd.DataFrame, snapshot_lag_days: int = 1
) -> pd.DataFrame:
    """Meeting-level table of pre-event expectations and realised outcomes."""
    meetings = resolve_meetings(probabilities, calendar)
    rows = []
    for meeting in meetings.itertuples(index=False):
        snapshot = pre_event_snapshot(
            probabilities, meeting.meeting_month, meeting.announcement_date, snapshot_lag_days
        )
        base = meeting._asdict()
        if snapshot.empty:
            rows.append(base | {"snapshot_date": pd.NaT, "distribution_valid": False})
            continue
        base["snapshot_date"] = snapshot["date"].iloc[0]
        rows.append(base | distribution_features(snapshot, meeting.resolved_outcome, meeting.realised_move_bp))
    return pd.DataFrame(rows)
