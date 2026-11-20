"""Command-line entry point for the data collectors.

Examples (run from the `sunny_playground` folder):

    python -m eventlens.collectors yahoo
    python -m eventlens.collectors markets --since 2024-01-01 --min-volume 10000
    python -m eventlens.collectors prices --max-markets 3000
    python -m eventlens.collectors all

Every step caches raw responses, so an interrupted run can simply be rerun.
"""

from __future__ import annotations

import argparse

from eventlens.collectors import gamma, prices, yahoo
from eventlens.config import get_paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m eventlens.collectors", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["yahoo", "markets", "prices", "all"])
    parser.add_argument("--since", default="2024-01-01", help="Earliest market end date / price date")
    parser.add_argument("--min-volume", type=float, default=10_000, help="Minimum lifetime market volume (USD)")
    parser.add_argument("--max-pages", type=int, default=200, help="Safety cap on Gamma pages (500 markets each)")
    parser.add_argument("--max-markets", type=int, default=None, help="Only fetch prices for the first N markets")
    args = parser.parse_args(argv)

    universe = get_paths().universe
    if args.step in ("yahoo", "all"):
        yahoo.collect(get_paths().yahoo, since="2022-01-01")
    if args.step in ("markets", "all"):
        gamma.collect_pages(universe / "gamma", args.since, args.min_volume, args.max_pages)
        count = gamma.normalise_markets(universe / "gamma", universe / "markets.csv")
        print(f"markets.csv: {count} resolved binary markets")
    if args.step in ("prices", "all"):
        prices.collect_histories(universe / "markets.csv", universe / "price_history", args.max_markets)
        rows = prices.normalise_histories(universe / "price_history", universe / "prices.csv")
        print(f"prices.csv: {rows} daily price points")


if __name__ == "__main__":
    main()
