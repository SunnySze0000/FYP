"""Daily adjusted prices for ETFs from Yahoo Finance's public chart endpoint."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from eventlens.collectors.http import get_json

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
DEFAULT_TICKERS = ("SPY", "QQQ", "IWM", "TLT", "DIA")


def parse_chart(ticker: str, payload: dict) -> list[dict]:
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", quote["close"])
    rows = []
    for stamp, close, adj_close in zip(result["timestamp"], quote["close"], adjusted):
        if close is None or adj_close is None:
            continue
        day = datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
        rows.append({"date": day, "ticker": ticker, "close": close, "adj_close": adj_close})
    return rows


def collect(directory: Path, since: str, tickers: tuple[str, ...] = DEFAULT_TICKERS) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    start = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp())
    end = int(datetime.now(tz=timezone.utc).timestamp())
    for ticker in tickers:
        payload = get_json(CHART_URL.format(ticker=ticker),
                           {"period1": start, "period2": end, "interval": "1d", "events": "div,split"})
        rows = parse_chart(ticker, payload)
        with (directory / f"{ticker}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date", "ticker", "close", "adj_close"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"{ticker}: {len(rows)} days", flush=True)
