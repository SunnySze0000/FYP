"""The single definition of Fed rate-outcome labels used everywhere.

Polymarket changed its bucket labels over time ("25 bps increase" vs
"25+ bps increase"). Each label is mapped to the closed interval of rate
changes (in basis points) it covers, and to one representative move used for
expected-move features. Open-ended buckets use their boundary value, which is
the realistic outcome in 2023-2026 (no Fed move larger than 50 bp occurred).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OutcomeBucket:
    label: str
    low_bp: float
    high_bp: float
    representative_bp: float

    def contains(self, move_bp: float) -> bool:
        return self.low_bp <= move_bp <= self.high_bp


_BUCKETS = (
    OutcomeBucket("75+ bps decrease", -math.inf, -75, -75),
    OutcomeBucket("50+ bps decrease", -math.inf, -50, -50),
    OutcomeBucket("50 bps decrease", -50, -50, -50),
    OutcomeBucket("25 bps decrease", -25, -25, -25),
    OutcomeBucket("no change", 0, 0, 0),
    OutcomeBucket("25 bps increase", 25, 25, 25),
    OutcomeBucket("25+ bps increase", 25, math.inf, 25),
    OutcomeBucket("50 bps increase", 50, 50, 50),
    OutcomeBucket("50+ bps increase", 50, math.inf, 50),
    OutcomeBucket("75 bps increase", 75, 75, 75),
)

BUCKETS: dict[str, OutcomeBucket] = {bucket.label: bucket for bucket in _BUCKETS}

#: Labels with no defined rate range. Rows carrying them are reported by the
#: validation layer and excluded from distribution features.
UNMAPPED_LABELS = frozenset({"other"})


def normalise_label(label: str) -> str:
    return " ".join(str(label).strip().lower().split())


def bucket_for(label: str) -> OutcomeBucket | None:
    return BUCKETS.get(normalise_label(label))


def representative_move(label: str) -> float:
    bucket = bucket_for(label)
    return math.nan if bucket is None else bucket.representative_bp
