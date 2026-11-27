"""Hourly and daily asset prices from Yahoo Finance's public chart endpoint (standard library only)."""

from __future__ import annotations

from walletlens.polymarket.http import ApiError, get_json

HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")


def chart(symbol: str, interval: str, range_: str, fetch=get_json) -> dict:
    """Raw chart payload; tries both Yahoo hosts."""
    last = None
    for host in HOSTS:
        try:
            return fetch(f"{host}/v8/finance/chart/{symbol}", {"interval": interval, "range": range_,
                                                              "includePrePost": "false"})
        except ApiError as error:
            last = error
    raise last


def bars(payload: dict, interval_seconds: int) -> list[tuple[int, int, float]]:
    """``(bar_start, bar_end, close)`` rows; bars without a close are dropped."""
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    item = result[0]
    stamps = item.get("timestamp") or []
    closes = ((item.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = []
    for stamp, close in zip(stamps, closes):
        if close is not None:
            out.append((int(stamp), int(stamp) + interval_seconds, float(close)))
    return out
