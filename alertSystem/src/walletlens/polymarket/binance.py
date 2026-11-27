"""BTC/ETH 1-minute spot candles from Binance's public data dump (data.binance.vision).

Monthly zip files are used for finished months and daily files for the current month;
the REST API is the last resort. Standard library only.
"""

from __future__ import annotations

import csv
import http.client
import io as _io
import time
import zipfile
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from walletlens.polymarket.http import USER_AGENT, get_json

COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades",
           "taker_buy_base", "taker_buy_quote", "ignore"]


def fetch_bytes(url: str, retries: int = 6) -> bytes | None:
    """Bytes of ``url``; None when the file does not exist (HTTP 404)."""
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    return None


def parse_zip(content: bytes) -> list[tuple[int, float, float, float, float, float]]:
    """Rows ``(open_time_seconds, open, high, low, close, volume)`` from one kline zip."""
    rows = []
    with zipfile.ZipFile(_io.BytesIO(content)) as archive:
        for name in archive.namelist():
            with archive.open(name) as handle:
                for record in csv.reader(_io.TextIOWrapper(handle, encoding="utf-8")):
                    if not record or not record[0].isdigit():
                        continue                      # header line in some files
                    stamp = int(record[0])
                    seconds = stamp // 1_000_000 if stamp > 10 ** 14 else stamp // 1000   # µs since 2025, ms before
                    rows.append((seconds, float(record[1]), float(record[2]), float(record[3]), float(record[4]),
                                 float(record[5])))
    return rows


def monthly_url(base: str, symbol: str, year: int, month: int) -> str:
    return f"{base}/data/spot/monthly/klines/{symbol}/1m/{symbol}-1m-{year}-{month:02d}.zip"


def daily_url(base: str, symbol: str, day: date) -> str:
    return f"{base}/data/spot/daily/klines/{symbol}/1m/{symbol}-1m-{day:%Y-%m-%d}.zip"


def rest_klines(api_base: str, symbol: str, start_s: int, end_s: int, fetch=get_json) -> list[tuple]:
    rows, cursor = [], start_s * 1000
    while cursor < end_s * 1000:
        batch = fetch(f"{api_base}/api/v3/klines", {"symbol": symbol, "interval": "1m", "startTime": cursor,
                                                    "endTime": end_s * 1000, "limit": 1000})
        if not batch:
            break
        rows += [(int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in batch]
        cursor = int(batch[-1][0]) + 60_000
    return rows


def month_range(first: date, last: date) -> list[tuple[int, int]]:
    out, year, month = [], first.year, first.month
    while (year, month) <= (last.year, last.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def days_of_month(year: int, month: int, last: date) -> list[date]:
    day, out = date(year, month, 1), []
    while day.month == month and day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out
