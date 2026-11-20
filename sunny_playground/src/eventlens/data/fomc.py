"""FOMC announcement calendar and the official decisions used for cross-checks.

Source: federalreserve.gov FOMC calendars and implementation notes. The
statement is released at 14:00 US/Eastern on the announcement date, during
US trading hours, so the announcement-day close-to-close return contains the
reaction.

`OFFICIAL_MOVE_BP` is an independent reference used only to validate the
Polymarket resolution data. Decisions after 2025 are left as ``None`` and are
taken from market resolution, flagged as unverified.
"""

from __future__ import annotations

import pandas as pd

ANNOUNCEMENT_DATES: tuple[str, ...] = (
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
)

OFFICIAL_MOVE_BP: dict[str, int | None] = {
    "2023-02-01": 25, "2023-03-22": 25, "2023-05-03": 25, "2023-06-14": 0,
    "2023-07-26": 25, "2023-09-20": 0, "2023-11-01": 0, "2023-12-13": 0,
    "2024-01-31": 0, "2024-03-20": 0, "2024-05-01": 0, "2024-06-12": 0,
    "2024-07-31": 0, "2024-09-18": -50, "2024-11-07": -25, "2024-12-18": -25,
    "2025-01-29": 0, "2025-03-19": 0, "2025-05-07": 0, "2025-06-18": 0,
    "2025-07-30": 0, "2025-09-17": -25, "2025-10-29": -25, "2025-12-10": -25,
}


def calendar() -> pd.DataFrame:
    """One row per announcement: date, meeting month and official move."""
    dates = pd.to_datetime(list(ANNOUNCEMENT_DATES))
    frame = pd.DataFrame({"announcement_date": dates})
    frame["meeting_month"] = frame["announcement_date"].dt.strftime("%Y-%m")
    frame["official_move_bp"] = [
        OFFICIAL_MOVE_BP.get(day) for day in ANNOUNCEMENT_DATES
    ]
    return frame
