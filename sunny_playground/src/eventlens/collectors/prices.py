"""Collect daily YES-token price history from the public CLOB API."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from eventlens.collectors.http import cached_json, get_json

PRICES_HISTORY_URL = "https://clob.polymarket.com/prices-history"
DAILY_FIDELITY_MINUTES = 1440
PRICE_FIELDS = ["market_id", "timestamp_utc", "yes_price"]


def _unix(iso: str) -> int | None:
    if not iso:
        return None
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def fetch_history(token_id: str, start_iso: str, end_iso: str) -> dict:
    """Daily history between market start and close; falls back to interval=max."""
    start, end = _unix(start_iso), _unix(end_iso)
    if start and end and end > start:
        payload = get_json(PRICES_HISTORY_URL, {
            "market": token_id, "startTs": start, "endTs": end, "fidelity": DAILY_FIDELITY_MINUTES})
        if payload.get("history"):
            return payload
    return get_json(PRICES_HISTORY_URL, {"market": token_id, "interval": "max", "fidelity": DAILY_FIDELITY_MINUTES})


def collect_histories(markets_csv: Path, directory: Path, max_markets: int | None) -> int:
    """Cache one JSON file per market; returns the number of markets processed."""
    with markets_csv.open(encoding="utf-8") as handle:
        markets = list(csv.DictReader(handle))
    markets = markets[:max_markets] if max_markets else markets
    for index, market in enumerate(markets, start=1):
        path = directory / f"{market['market_id']}.json"
        end = market["closed_time"] or market["end_date"]
        try:
            cached_json(path, lambda: fetch_history(market["yes_token_id"], market["start_date"], _iso(end)))
        except RuntimeError as error:
            print(f"skip {market['market_id']}: {error}", flush=True)
        if index % 100 == 0:
            print(f"price histories: {index}/{len(markets)}", flush=True)
    return len(markets)


def _iso(value: str) -> str:
    """Gamma closedTime looks like '2024-11-06 05:12:00+00'; make it ISO 8601."""
    value = value.strip().replace(" ", "T")
    return value + ":00" if value.endswith("+00") else value


def normalise_histories(directory: Path, output_csv: Path) -> int:
    rows = 0
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRICE_FIELDS)
        writer.writeheader()
        for path in sorted(directory.glob("*.json")):
            history = json.loads(path.read_text(encoding="utf-8")).get("history", [])
            for point in history:
                writer.writerow({
                    "market_id": path.stem,
                    "timestamp_utc": datetime.fromtimestamp(int(point["t"]), tz=timezone.utc).isoformat(),
                    "yes_price": point["p"],
                })
                rows += 1
    return rows
