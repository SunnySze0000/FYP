"""T1 collector: crypto up/down markets with their trades, and BTC/ETH 1-minute spot.

Stages:  discover -> sample -> download -> spot -> build   (all resumable)

Markets are found by their predictable slugs (e.g. ``btc-updown-15m-<start unix>``,
``bitcoin-up-or-down-september-1-2026-1am-et``) for a random sample of candle windows;
``scan`` (every closed market) is kept as a slow fallback.

    python -m walletlens crypto collect [--stages ...] [--max-markets N]
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from walletlens import io, logs
from walletlens.collect.common import (choose_trade_filter, download_trades, run_parallel, scan_closed_markets,
                                       slim)
from walletlens.config import Settings
from walletlens.data.markets import market_row, parse_time
from walletlens.polymarket import binance
from walletlens.polymarket.api import GAMMA
from walletlens.polymarket.http import ApiError, get_json

log = logs.get("collect.crypto")

ASSET_WORDS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "xrp": "XRP"}
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}
KIND_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14_400, "1d": 86_400}
SLUG_TICKER = {"BTC": "btc", "ETH": "eth", "SOL": "sol", "XRP": "xrp"}
SLUG_NAME = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp"}
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
DTYPES = {"market_id": str, "yes_token": str, "no_token": str, "group_id": str, "condition_id": str}

_RANGE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*-\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*et", re.I)
_SINGLE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*et\b", re.I)
_DAILY = re.compile(r"\bon\s+[a-z]+\s+\d{1,2}\b", re.I)


def _minutes(hour: str, minute: str | None, half: str) -> int:
    value = int(hour) % 12 + (12 if half.lower() == "pm" else 0)
    return value * 60 + int(minute or 0)


def classify(market: dict) -> dict | None:
    """Asset, window kind and candle window of an 'X Up or Down' market, or None."""
    question = str(market.get("question") or "").strip()
    lower = question.lower()
    if " up or down" not in lower:
        return None
    asset = next((code for word, code in ASSET_WORDS.items() if lower.startswith(word)), None)
    if asset is None:
        return None
    match = _RANGE.search(question)
    if match:
        start = _minutes(match.group(1), match.group(2), match.group(3))
        end = _minutes(match.group(4), match.group(5), match.group(6))
        length = (end - start) % (24 * 60) * 60
        kind = {300: "5m", 900: "15m", 3600: "1h", 14_400: "4h"}.get(length, f"{length // 60}m")
    elif _SINGLE.search(question):
        kind, length = "1h", 3600
    elif _DAILY.search(question):
        kind, length = "1d", 86_400
    else:
        return None
    end_ts = parse_time(market.get("endDate"))
    start_ts = parse_time(market.get("eventStartTime")) or (end_ts - length if end_ts else None)
    if not end_ts or not start_ts:
        return None
    return {"asset": asset, "kind": kind, "window_start": start_ts, "window_end": end_ts,
            "window_source": "eventStartTime" if market.get("eventStartTime") else "endDate_minus_length"}


def _us_eastern_offset(ts: int) -> int:
    """UTC offset (seconds) of New York at ``ts``: EDT from the 2nd Sunday of March 02:00 to the 1st Sunday
    of November 02:00 local time, EST otherwise (no tz database needed, so it works on any Windows Python)."""
    year = datetime.fromtimestamp(ts, timezone.utc).year

    def nth_sunday(month: int, n: int) -> datetime:
        first = datetime(year, month, 1, tzinfo=timezone.utc)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))

    start = nth_sunday(3, 2) + timedelta(hours=7)        # 02:00 EST = 07:00 UTC
    end = nth_sunday(11, 1) + timedelta(hours=6)         # 02:00 EDT = 06:00 UTC
    return -4 * 3600 if start.timestamp() <= ts < end.timestamp() else -5 * 3600


def slug_for(asset: str, kind: str, start_ts: int) -> str:
    """Polymarket's slug for an up/down market whose candle window starts at ``start_ts``."""
    if kind in ("5m", "15m", "4h"):
        return f"{SLUG_TICKER[asset]}-updown-{kind}-{start_ts}"
    if kind == "1h":
        local = datetime.fromtimestamp(start_ts + _us_eastern_offset(start_ts), timezone.utc)
        hour = local.hour % 12 or 12
        return (f"{SLUG_NAME[asset]}-up-or-down-{MONTHS[local.month - 1]}-{local.day}-{local.year}-"
                f"{hour}{'am' if local.hour < 12 else 'pm'}-et")
    raise ValueError(kind)


def candidate_windows(asset: str, kind: str, start: str, end: str) -> list[int]:
    """Every window start of one kind between two dates (4-hour windows are aligned to New York time)."""
    first = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    last = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())
    step = KIND_SECONDS[kind]
    if kind == "4h":
        out, t = [], first - first % 3600
        while t < last:
            local_hour = ((t + _us_eastern_offset(t)) // 3600) % 24
            if local_hour % 4 == 0:
                out.append(t)
            t += 3600
        return out
    return list(range(first - first % step + step, last, step))


def stage_discover(settings: Settings, fetch=get_json, batch: int = 25) -> pd.DataFrame:
    """Find sampled up/down markets directly by their slugs (much faster than scanning every market)."""
    cfg = settings.crypto
    rng = random.Random(cfg.seed)
    wanted = []
    for asset in cfg.assets:
        for kind, count in cfg.per_kind.items():
            if kind not in ("5m", "15m", "1h", "4h") or count <= 0:
                continue
            starts = candidate_windows(asset, kind, cfg.closed_from, cfg.closed_to)
            rng.shuffle(starts)
            wanted += [slug_for(asset, kind, t) for t in starts[: int(count * 1.3)]]   # a few windows have no market
    folder = settings.paths.raw / "gamma_crypto_slugs"
    found, started = [], time.time()
    for index in range(0, len(wanted), batch):
        chunk = wanted[index: index + batch]
        path = folder / f"batch_{index // batch:05d}.json"
        cached = io.read_json(path) if path.exists() else None
        if cached:                                   # an empty cached batch is fetched again
            page = cached
        else:
            try:
                page = fetch(f"{GAMMA}/markets", {"slug": chunk, "closed": "true", "limit": batch})
            except ApiError as error:
                log.warning("slug batch %d failed (retry next run): %s", index // batch, error)
                continue
            page = [slim(m) for m in page] if isinstance(page, list) else []
            io.write_json(path, page, indent=None)
        found += page
        if (index // batch) % 20 == 0:
            log.info("crypto discover %d/%d slugs, %d markets found (%.0f s)", index + len(chunk), len(wanted),
                     len(found), time.time() - started)
    return _keep_crypto(settings, found, len(wanted))


def _keep_crypto(settings: Settings, raw: list[dict], requested: int) -> pd.DataFrame:
    cfg = settings.crypto
    rows, reasons = [], {}
    for market in {str(m.get("id")): m for m in raw}.values():
        info = classify(market)
        volume = float(market.get("volumeNum") or market.get("volume") or 0)
        if info is None or info["asset"] not in cfg.assets:
            reasons["not_crypto_up_down"] = reasons.get("not_crypto_up_down", 0) + 1
            continue
        if volume < cfg.min_volume_usd:
            reasons["low_volume"] = reasons.get("low_volume", 0) + 1
            continue
        row, reason = market_row(market)
        reasons[reason] = reasons.get(reason, 0) + 1
        if row:
            row.update(info)
            row["group_id"] = f"{info['asset']}-{info['kind']}-{datetime.fromtimestamp(info['window_end'], timezone.utc):%Y-%m-%d}"
            rows.append(row)
    frame = pd.DataFrame(rows)
    folder = settings.paths.interim / "crypto"
    io.write_csv(folder / "candidates.csv", frame)
    counts = frame.groupby(["asset", "kind"]).size().to_dict() if len(frame) else {}
    io.write_json(folder / "candidates_report.json", {"requested": requested, "returned": len(raw), "kept": len(frame),
                                                      "reasons": reasons, "by_asset_kind": {str(k): v for k, v in counts.items()}})
    log.info("crypto markets: %d kept of %d returned (%s); %s", len(frame), len(raw), reasons, counts)
    return frame


def stage_scan(settings: Settings, fetch=get_json) -> pd.DataFrame:
    """Slow fallback: scan every closed market and keep the up/down ones."""
    cfg = settings.crypto
    raw = scan_closed_markets(settings.paths.raw / "gamma_crypto", cfg.closed_from, cfg.closed_to,
                              {"volume_num_min": cfg.min_volume_usd}, fetch, window_days=3, label="crypto scan")
    return _keep_crypto(settings, raw, len(raw))


def stage_sample(settings: Settings) -> pd.DataFrame:
    cfg = settings.crypto
    folder = settings.paths.interim / "crypto"
    candidates = pd.read_csv(folder / "candidates.csv", dtype=DTYPES)
    rng = random.Random(cfg.seed)
    picked = []
    for (asset, kind), part in candidates.groupby(["asset", "kind"]):
        ids = sorted(part["market_id"])
        rng.shuffle(ids)
        picked += ids[: cfg.per_kind.get(kind, 0)]
    rng.shuffle(picked)                                      # interleave kinds: a partial download stays balanced
    order = {market_id: rank for rank, market_id in enumerate(picked)}
    sample = candidates[candidates["market_id"].isin(order)].copy()
    sample["sample_rank"] = sample["market_id"].map(order)
    sample = sample.sort_values("sample_rank").reset_index(drop=True)
    io.write_csv(folder / "sample.csv", sample)
    log.info("crypto sample: %d markets (%s)", len(sample), sample.groupby(["asset", "kind"]).size().to_dict())
    return sample


def stage_download(settings: Settings, max_markets: int | None = None, fetch=get_json, workers: int = 6) -> pd.DataFrame:
    cfg = settings.crypto
    sample = pd.read_csv(settings.paths.interim / "crypto" / "sample.csv", dtype=DTYPES)
    if max_markets:
        sample = sample.head(max_markets)
    markets = sample.to_dict("records")
    if markets:                                      # decide the trade filter once, before the threads start
        choose_trade_filter(settings.paths.raw / "crypto_trades" / "_filter.json", markets[0]["condition_id"],
                            cfg.trade_filter_type, cfg.trade_filter_amount, fetch)

    def work(market):
        filter_type, amount = choose_trade_filter(settings.paths.raw / "crypto_trades" / "_filter.json",
                                                  market["condition_id"], cfg.trade_filter_type,
                                                  cfg.trade_filter_amount, fetch)
        return download_trades(settings.paths.raw / "crypto_trades" / market["market_id"],
                               settings.paths.interim / "crypto_trades" / f"{market['market_id']}.csv.gz",
                               market, filter_type, amount, cfg.trade_page_size, cfg.max_trade_pages, fetch)

    statuses = run_parallel(markets, work, workers, "crypto download")
    frame = pd.DataFrame(statuses)
    io.write_csv(settings.paths.interim / "crypto" / "download_status.csv", frame)
    return frame


def stage_spot(settings: Settings, fetch=get_json, fetch_bytes=binance.fetch_bytes) -> None:
    """1-minute candles for every asset, covering every sampled market's window (plus a margin)."""
    cfg = settings.crypto
    sample = pd.read_csv(settings.paths.interim / "crypto" / "sample.csv", dtype=DTYPES)
    first = datetime.fromtimestamp(int(sample["window_start"].min()) - 3 * 86_400, timezone.utc).date()
    last = min(datetime.fromtimestamp(int(sample["window_end"].max()) + 86_400, timezone.utc).date(),
               datetime.now(timezone.utc).date() - timedelta(days=1))
    for asset in sorted(sample["asset"].unique()):
        symbol = SYMBOLS[asset]
        for year, month in binance.month_range(first, last):
            target = settings.paths.raw / "spot" / symbol / f"{year}-{month:02d}.csv.gz"
            if target.exists():
                continue
            rows = []
            content = fetch_bytes(binance.monthly_url(cfg.binance_data, symbol, year, month))
            if content is not None:
                rows = binance.parse_zip(content)
            else:                                           # month not published yet: daily files, then the API
                for day in binance.days_of_month(year, month, last):
                    daily = fetch_bytes(binance.daily_url(cfg.binance_data, symbol, day))
                    if daily is not None:
                        rows += binance.parse_zip(daily)
                    else:
                        start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
                        try:
                            rows += binance.rest_klines(cfg.binance_api, symbol, start, start + 86_400, fetch)
                        except ApiError as error:
                            log.warning("no spot data for %s %s: %s", symbol, day, error)
            if not rows:
                log.warning("no spot data for %s %d-%02d", symbol, year, month)
                continue
            frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
            complete_month = (year, month) < (last.year, last.month) or content is not None
            if complete_month:
                io.write_csv(target, frame.sort_values("ts"))
            else:                                           # partial month: keep under another name, refresh next run
                io.write_csv(target.with_name(f"{year}-{month:02d}.partial.csv.gz"), frame.sort_values("ts"))
            log.info("spot %s %d-%02d: %d minutes", symbol, year, month, len(frame))


def stage_build(settings: Settings) -> None:
    from walletlens.topics.crypto.build import build_crypto
    build_crypto(settings)


STAGES = ("discover", "sample", "download", "spot", "build")


def run(settings: Settings, stages=STAGES, max_markets: int | None = None, fetch=get_json,
        fetch_bytes=binance.fetch_bytes) -> None:
    for stage in stages:
        log.info("=== crypto stage %s ===", stage)
        if stage == "discover":
            stage_discover(settings, fetch)
        elif stage == "scan":
            stage_scan(settings, fetch)
        elif stage == "sample":
            stage_sample(settings)
        elif stage == "download":
            stage_download(settings, max_markets, fetch)
        elif stage == "spot":
            stage_spot(settings, fetch, fetch_bytes)
        elif stage == "build":
            stage_build(settings)
        else:
            raise ValueError(f"unknown stage {stage}")
