"""Thin wrappers around the three public Polymarket APIs used by the project.

* Gamma (market metadata):  https://gamma-api.polymarket.com
* Data API (trades, prices): https://data-api.polymarket.com
* CLOB (order book, prices): https://clob.polymarket.com

Every function returns plain Python objects; callers decide what to cache.
"""

from __future__ import annotations

import json
from typing import Callable, Iterator

from walletlens.polymarket.http import ApiError, get_json

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

GAMMA_PAGE = 100            # Gamma serves at most 100 markets per request
GAMMA_MAX_OFFSET = 1900     # offsets past ~2000 return HTTP 422, so windows are split instead

Fetch = Callable[..., object]


def as_list(value) -> list:
    """Gamma encodes lists as JSON strings ('["Yes", "No"]')."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith("["):
        return json.loads(value)
    return []


# --------------------------------------------------------------------------- Gamma

def gamma_markets_page(params: dict, offset: int, fetch: Fetch = get_json) -> list[dict]:
    page = fetch(f"{GAMMA}/markets", {**params, "limit": GAMMA_PAGE, "offset": offset})
    if not isinstance(page, list):
        raise ApiError(None, "gamma/markets", "unexpected payload")
    return page


def gamma_market(market_id: str, fetch: Fetch = get_json) -> dict:
    return fetch(f"{GAMMA}/markets/{market_id}")


def gamma_active_markets(limit: int = 100, offset: int = 0, order: str = "volume24hr",
                         fetch: Fetch = get_json, **extra) -> list[dict]:
    params = {"active": "true", "closed": "false", "limit": limit, "offset": offset,
              "order": order, "ascending": "false", **extra}
    return fetch(f"{GAMMA}/markets", params)


# --------------------------------------------------------------------------- Data API: trades

def trade_pages(condition_id: str, filter_type: str, filter_amount: float, page_size: int,
                max_pages: int, fetch: Fetch = get_json, start_cursor: str | None = None
                ) -> Iterator[tuple[str | None, dict]]:
    """Yield ``(request_cursor, response)`` for each page of ``/v2/trades`` (newest first)."""
    cursor = start_cursor
    for _ in range(max_pages):
        params = {"condition": condition_id, "limit": page_size, "taker_only": "false",
                  "filter_type": filter_type, "filter_amount": filter_amount, "cursor": cursor}
        response = fetch(f"{DATA}/v2/trades", params)
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise ApiError(None, "data/v2/trades", "unexpected payload")
        yield cursor, response
        cursor = (response.get("pagination") or {}).get("next_cursor")
        if not cursor:
            return


def recent_trades(condition_id: str, limit: int = 500, fetch: Fetch = get_json) -> list[dict]:
    """Latest trades of one market (used live by the app)."""
    response = fetch(f"{DATA}/v2/trades", {"condition": condition_id, "limit": limit,
                                            "taker_only": "false"})
    return response.get("data", []) if isinstance(response, dict) else []


def wallet_trades(wallet: str, limit: int = 500, fetch: Fetch = get_json) -> list[dict]:
    """Latest trades of one wallet (used live by the app)."""
    response = fetch(f"{DATA}/v2/trades", {"user": wallet, "limit": limit, "taker_only": "false"})
    return response if isinstance(response, list) else response.get("data", [])


# --------------------------------------------------------------------------- prices

def price_history(token_id: str, bucket_seconds: int, fetch: Fetch = get_json, max_pages: int = 200,
                  start_ts: int | None = None, end_ts: int | None = None) -> tuple[list[dict], str]:
    """Whole-life price history of one token as ``[{"t": unix, "p": price}]``.

    1. Data API ``/v2/prices-history`` (paged). Fine buckets (1 hour) only reach back about a month.
    2. CLOB ``/prices-history`` with ``interval=max``.
    3. CLOB in explicit windows of at most 14 days (its cap is 15), when the market's life is known.
    Sources are combined when the first ones do not cover the start of the market's life.
    """
    errors, points, used = [], [], []
    try:
        found, params = [], {"token_id": token_id, "interval": "max", "bucket_seconds": bucket_seconds}
        for _ in range(max_pages):
            payload = fetch(f"{DATA}/v2/prices-history", params)
            found += [{"t": int(p["timestamp"]), "p": float(p["price"])} for p in payload.get("data", [])]
            cursor = (payload.get("pagination") or {}).get("next_cursor")
            if not cursor:
                break
            params = {"token_id": token_id, "cursor": cursor}
        if found:
            points, used = points + found, used + ["data_api"]
    except ApiError as error:
        errors.append(str(error))
    fidelity = max(1, bucket_seconds // 60)

    def covers_start() -> bool:
        return bool(points) and (start_ts is None or min(p["t"] for p in points) <= start_ts + 2 * 86_400)

    if not covers_start():
        try:
            payload = fetch(f"{CLOB}/prices-history", {"market": token_id, "interval": "max", "fidelity": fidelity})
            found = [{"t": int(p["t"]), "p": float(p["p"])} for p in payload.get("history", [])]
            if found:
                points, used = points + found, used + ["clob_max"]
        except ApiError as error:
            errors.append(str(error))
    if not covers_start() and start_ts and end_ts and end_ts > start_ts:
        left, found = start_ts, []
        while left < end_ts:
            right = min(left + 14 * 86_400, end_ts)
            try:
                payload = fetch(f"{CLOB}/prices-history", {"market": token_id, "startTs": left, "endTs": right,
                                                           "fidelity": fidelity})
                found += [{"t": int(p["t"]), "p": float(p["p"])} for p in payload.get("history", [])]
            except ApiError as error:
                errors.append(str(error))
            left = right
        if found:
            points, used = points + found, used + ["clob_windows"]
    if points:
        return _dedupe(points), "+".join(used)
    return [], "; ".join(errors) or "empty"


def _dedupe(points: list[dict]) -> list[dict]:
    unique = {p["t"]: p["p"] for p in points}
    return [{"t": t, "p": unique[t]} for t in sorted(unique)]


def order_book(token_id: str, fetch: Fetch = get_json) -> dict:
    return fetch(f"{CLOB}/book", {"token_id": token_id})
