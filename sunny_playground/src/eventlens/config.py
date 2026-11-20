"""Filesystem locations used by the package.

Every path can be overridden with an environment variable so the same code
runs on a teammate's laptop, in CI, or in a sandbox with data elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PLAYGROUND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PLAYGROUND_ROOT.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


@dataclass(frozen=True)
class Paths:
    """Resolved input and output directories."""

    team_data: Path
    raw_data: Path
    reports: Path

    @property
    def probabilities_csv(self) -> Path:
        return self.team_data / "forward_probabilities.csv"

    @property
    def prices_csv(self) -> Path:
        return self.team_data / "index_daily.csv"

    @property
    def fed_wallets(self) -> Path:
        return self.raw_data / "fed_wallets"

    @property
    def universe(self) -> Path:
        """Output of the Polymarket universe collectors."""
        return self.raw_data / "polymarket_universe"

    @property
    def yahoo(self) -> Path:
        return self.raw_data / "yahoo"


def get_paths() -> Paths:
    return Paths(
        team_data=_env_path("EVENTLENS_TEAM_DATA", REPO_ROOT / "datasets"),
        raw_data=_env_path("EVENTLENS_RAW_DATA", PLAYGROUND_ROOT / "data" / "raw"),
        reports=_env_path("EVENTLENS_REPORTS", PLAYGROUND_ROOT / "reports"),
    )
