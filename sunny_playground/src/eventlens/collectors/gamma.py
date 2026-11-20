"""Collect resolved Polymarket markets from the public Gamma API.

Pages are cached under `<universe>/gamma/`, so rerunning resumes where it
stopped. `normalise_markets` turns cached pages into one tidy CSV of binary
markets with a known winner.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from eventlens.collectors.http import cached_json, get_json

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
PAGE_SIZE = 500

MARKET_FIELDS = [
    "market_id", "event_id", "question", "slug", "category", "condition_id",
    "yes_token_id", "no_token_id", "start_date", "end_date", "closed_time",
    "volume_usd", "liquidity_usd", "yes_won",
]


def collect_pages(directory: Path, since: str, min_volume: float, max_pages: int) -> list[Path]:
    """Fetch pages of closed markets ending on/after `since` with volume >= `min_volume`."""
    pages = []
    for page in range(max_pages):
        offset = page * PAGE_SIZE
        path = directory / f"page_{offset:08d}.json"
        params = {
            "closed": "true", "limit": PAGE_SIZE, "offset": offset, "order": "id", "ascending": "true",
            "end_date_min": f"{since}T00:00:00Z", "volume_num_min": min_volume,
        }
        payload = cached_json(path, lambda: get_json(GAMMA_MARKETS_URL, params))
        pages.append(path)
        print(f"gamma page {page + 1}: {len(payload)} markets", flush=True)
        if len(payload) < PAGE_SIZE:
            break
    return pages


def iter_cached_markets(directory: Path) -> Iterator[dict]:
    for path in sorted(directory.glob("page_*.json")):
        yield from json.loads(path.read_text(encoding="utf-8"))


def parse_market(raw: dict) -> dict | None:
    """Return a tidy record for a resolved two-outcome market, else None."""
    outcomes = _json_list(raw.get("outcomes"))
    prices = _json_list(raw.get("outcomePrices"))
    tokens = _json_list(raw.get("clobTokenIds"))
    if len(outcomes) != 2 or len(prices) != 2 or len(tokens) != 2:
        return None
    try:
        final = [float(price) for price in prices]
    except (TypeError, ValueError):
        return None
    if sorted(final) != [0.0, 1.0]:
        return None
    yes_index = _yes_index(outcomes)
    events = raw.get("events") or [{}]
    return {
        "market_id": str(raw.get("id")),
        "event_id": str(events[0].get("id", "")),
        "question": raw.get("question", ""),
        "slug": raw.get("slug", ""),
        "category": raw.get("category") or events[0].get("category") or "",
        "condition_id": raw.get("conditionId", ""),
        "yes_token_id": str(tokens[yes_index]),
        "no_token_id": str(tokens[1 - yes_index]),
        "start_date": raw.get("startDate", ""),
        "end_date": raw.get("endDate", ""),
        "closed_time": raw.get("closedTime", ""),
        "volume_usd": raw.get("volumeNum") or raw.get("volume") or "",
        "liquidity_usd": raw.get("liquidityNum") or raw.get("liquidity") or "",
        "yes_won": int(final[yes_index] == 1.0),
    }


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _yes_index(outcomes: list) -> int:
    """Index of the 'Yes' outcome; for named outcomes (A vs B) the first is treated as YES."""
    labels = [str(outcome).strip().lower() for outcome in outcomes]
    return labels.index("yes") if "yes" in labels else 0


def normalise_markets(directory: Path, output_csv: Path) -> int:
    records = {}
    for raw in iter_cached_markets(directory):
        record = parse_market(raw)
        if record:
            records[record["market_id"]] = record
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_FIELDS)
        writer.writeheader()
        writer.writerows(records.values())
    return len(records)
