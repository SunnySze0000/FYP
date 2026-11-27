"""Turn Gamma market JSON into canonical ``markets`` rows."""

from __future__ import annotations

from datetime import datetime, timezone

from walletlens.data.schema import categorise
from walletlens.polymarket.api import as_list


def parse_time(value) -> int | None:
    """Gamma mixes '2026-07-29T00:00:00Z', '2026-07-29 20:01:42+00' and plain dates."""
    if not value:
        return None
    text = str(value).strip().replace(" ", "T").replace("Z", "+00:00")
    if text.endswith("+00"):
        text += ":00"
    if len(text) == 10:
        text += "T00:00:00+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


BINARY_LABELS = (["yes", "no"], ["up", "down"])   # "Up" is treated as YES


def outcome_from_prices(market: dict) -> int | None:
    """1 if YES (or Up) resolved true, 0 if NO; None if unresolved or ambiguous (e.g. 50/50)."""
    labels = [str(x).lower() for x in as_list(market.get("outcomes"))]
    prices = as_list(market.get("outcomePrices"))
    if labels not in BINARY_LABELS or len(prices) != 2:
        return None
    try:
        yes, no = float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return None
    if yes >= 0.99 and no <= 0.01:
        return 1
    if no >= 0.99 and yes <= 0.01:
        return 0
    return None


def market_row(market: dict) -> tuple[dict | None, str]:
    """Return ``(row, "ok")`` or ``(None, reason)``."""
    labels = [str(x).lower() for x in as_list(market.get("outcomes"))]
    tokens = [str(t) for t in as_list(market.get("clobTokenIds"))]
    if labels not in BINARY_LABELS or len(tokens) != 2:
        return None, "not_binary_yes_no"
    outcome = outcome_from_prices(market)
    if outcome is None:
        return None, "unresolved_or_ambiguous"
    close_ts = (parse_time(market.get("closedTime")) or parse_time(market.get("umaEndDate"))
                or parse_time(market.get("endDate")))
    start_ts = (parse_time(market.get("acceptingOrdersTimestamp")) or parse_time(market.get("startDate"))
                or parse_time(market.get("createdAt")))
    if not close_ts or not start_ts or close_ts <= start_ts:
        return None, "bad_dates"
    events = market.get("events") if isinstance(market.get("events"), list) else []
    group = market.get("negRiskMarketID") or (events[0].get("id") if events else None) or market.get("id")
    question = str(market.get("question") or "")
    row = {
        "market_id": str(market["id"]),
        "condition_id": str(market.get("conditionId", "")).lower(),
        "question": question,
        "category": categorise(question),
        "group_id": str(group),
        "yes_token": tokens[0],
        "no_token": tokens[1],
        "start_ts": start_ts,
        "end_ts": parse_time(market.get("endDate")) or close_ts,
        "close_ts": close_ts,
        "outcome_yes": outcome,
        "volume_usd": float(market.get("volumeNum") or market.get("volume") or 0),
        "resolution_source": "gamma_outcome_prices",
    }
    return row, "ok"
