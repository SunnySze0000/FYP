"""Run every analysis and write `reports/results.md` plus one CSV per table.

Usage (from the `sunny_playground` folder):

    python scripts/run_research.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eventlens.pipeline import run_all  # noqa: E402


def main() -> None:
    started = time.time()
    report = run_all()
    print(f"Wrote {report.directory / 'results.md'} in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
