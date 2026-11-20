"""Data-quality checks that report problems instead of silently fixing them.

Each check returns a DataFrame of offending rows (empty means pass). The
`run_probability_checks` function bundles them into a summary for reports.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from eventlens.data.taxonomy import BUCKETS, UNMAPPED_LABELS

PROBABILITY_SUM_TOLERANCE = 0.10


@dataclass(frozen=True)
class CheckResult:
    name: str
    description: str
    failures: pd.DataFrame

    @property
    def passed(self) -> bool:
        return self.failures.empty


def probability_sums(probabilities: pd.DataFrame, tolerance: float = PROBABILITY_SUM_TOLERANCE) -> pd.DataFrame:
    """Snapshots whose outcome probabilities for one meeting do not sum to ~1."""
    sums = (
        probabilities.groupby(["date", "meeting_month"])
        .agg(probability_sum=("market_probability", "sum"), outcomes=("outcome", "size"))
        .reset_index()
    )
    return sums.loc[(sums["probability_sum"] - 1).abs() > tolerance]


def unmapped_labels(probabilities: pd.DataFrame) -> pd.DataFrame:
    """Rows whose outcome label has no defined rate range."""
    known = set(BUCKETS)
    mask = ~probabilities["outcome"].isin(known) | probabilities["outcome"].isin(UNMAPPED_LABELS)
    return probabilities.loc[mask, ["date", "meeting_month", "outcome", "market_id"]]


def resolution_consistency(probabilities: pd.DataFrame) -> pd.DataFrame:
    """Meetings where the number of markets resolving YES is not exactly one."""
    per_market = probabilities.drop_duplicates("market_id")
    counts = per_market.groupby("meeting_month")["final_outcome"].sum().rename("yes_markets")
    return counts.loc[counts.ne(1)].reset_index()


def snapshot_gaps(probabilities: pd.DataFrame, max_gap_days: int = 5) -> pd.DataFrame:
    """Calendar gaps between consecutive snapshot dates longer than `max_gap_days`."""
    dates = pd.Series(sorted(probabilities["date"].unique()))
    gaps = dates.diff().dt.days
    frame = pd.DataFrame({"gap_end": dates, "gap_days": gaps})
    return frame.loc[frame["gap_days"] > max_gap_days]


def calendar_alignment(probabilities: pd.DataFrame, calendar: pd.DataFrame, max_lag_days: int = 5) -> pd.DataFrame:
    """Meetings whose market data stop too far from the official announcement date.

    Market price series should end on or shortly after the announcement. A
    mismatch means the meeting month or the calendar is wrong.
    """
    last = probabilities.groupby("meeting_month")["date"].max().rename("last_snapshot")
    joined = calendar.merge(last, on="meeting_month", how="inner")
    joined["lag_days"] = (joined["last_snapshot"] - joined["announcement_date"]).dt.days
    return joined.loc[(joined["lag_days"] < 0) | (joined["lag_days"] > max_lag_days)]


def missing_meetings(probabilities: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Announcements inside the data period with no Polymarket markets."""
    start, end = probabilities["date"].min(), probabilities["date"].max()
    in_range = calendar.loc[calendar["announcement_date"].between(start, end)]
    covered = set(probabilities["meeting_month"].unique())
    return in_range.loc[~in_range["meeting_month"].isin(covered)]


def run_probability_checks(probabilities: pd.DataFrame, calendar: pd.DataFrame) -> list[CheckResult]:
    return [
        CheckResult("probability_sums", "Meeting probabilities sum to 1 within 0.10", probability_sums(probabilities)),
        CheckResult("unmapped_labels", "Every outcome label maps to a rate range", unmapped_labels(probabilities)),
        CheckResult("resolution_consistency", "Exactly one market per meeting resolves YES", resolution_consistency(probabilities)),
        CheckResult("snapshot_gaps", "No snapshot gap longer than 5 days", snapshot_gaps(probabilities)),
        CheckResult("calendar_alignment", "Market data end 0-5 days after the announcement", calendar_alignment(probabilities, calendar)),
        CheckResult("missing_meetings", "Every FOMC meeting in range has markets", missing_meetings(probabilities, calendar)),
    ]


def summarise(results: list[CheckResult]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "check": [result.name for result in results],
            "description": [result.description for result in results],
            "passed": [result.passed for result in results],
            "failures": [len(result.failures) for result in results],
        }
    )
