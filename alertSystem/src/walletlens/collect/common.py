"""Building blocks shared by every collector: Gamma scans, price histories and trade downloads.

All functions cache raw responses on disk and are safe to call again after an interruption.
"""

from __future__ import annotations

import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from walletlens import io, logs
from walletlens.data.normalize import normalize_trade_records
from walletlens.polymarket import api
from walletlens.polymarket.http import ApiError

log = logs.get("collect")


KEEP_FIELDS = ("id", "question", "slug", "conditionId", "outcomes", "outcomePrices", "clobTokenIds", "startDate",
               "endDate", "closedTime", "umaEndDate", "acceptingOrdersTimestamp", "createdAt", "eventStartTime",
               "volumeNum", "volume", "negRiskMarketID", "category")


def slim(market: dict) -> dict:
    """Only the fields the project uses (Gamma pages are ~10x smaller on disk this way)."""
    out = {k: market[k] for k in KEEP_FIELDS if k in market}
    events = market.get("events")
    if isinstance(events, list) and events:
        out["events"] = [{"id": e.get("id"), "slug": e.get("slug")} for e in events if isinstance(e, dict)]
    return out


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def windows(start: str, end: str, days: float) -> list[tuple[datetime, datetime]]:
    left = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    stop = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    out = []
    while left < stop:
        right = min(left + timedelta(days=days), stop)
        out.append((left, right))
        left = right
    return out


def collect_window(folder_root: Path, base_params: dict, left: datetime, right: datetime, fetch,
                   min_span: timedelta = timedelta(minutes=30)) -> list[dict]:
    """Every closed market whose end date is in [left, right); splits the window at Gamma's offset cap."""
    key = f"{left:%Y%m%d%H%M}_{right:%Y%m%d%H%M}"
    folder = folder_root / key
    done = folder / "_complete.json"
    if done.exists():
        if io.read_json(done).get("split"):
            middle = left + (right - left) / 2
            return (collect_window(folder_root, base_params, left, middle, fetch, min_span)
                    + collect_window(folder_root, base_params, middle, right, fetch, min_span))
        return [m for path in sorted(folder.glob("offset_*.json")) for m in io.read_json(path)]
    params = {**base_params, "end_date_min": iso(left), "end_date_max": iso(right)}
    markets, offset = [], 0
    while True:
        path = folder / f"offset_{offset:05d}.json"
        if path.exists():
            page = io.read_json(path)
        else:
            page = api.gamma_markets_page(params, offset, fetch)
            io.write_json(path, [slim(m) for m in page], indent=None)
        markets += page
        if len(page) < api.GAMMA_PAGE:
            break
        offset += api.GAMMA_PAGE
        if offset > api.GAMMA_MAX_OFFSET:
            if right - left <= min_span:
                log.warning("window %s still over the offset cap; keeping the first %d markets", key, len(markets))
                break
            io.write_json(done, {"split": True})
            middle = left + (right - left) / 2
            return (collect_window(folder_root, base_params, left, middle, fetch, min_span)
                    + collect_window(folder_root, base_params, middle, right, fetch, min_span))
    io.write_json(done, {"markets": len(markets)})
    return markets


def scan_closed_markets(folder_root: Path, start: str, end: str, base_params: dict, fetch,
                        window_days: float = 15, label: str = "scan") -> list[dict]:
    """All closed markets ending between ``start`` and ``end`` (inclusive), de-duplicated by id."""
    seen, out = set(), []
    spans = windows(start, end, window_days)
    for index, (left, right) in enumerate(spans, 1):
        for market in collect_window(folder_root, {"closed": "true", "order": "id", "ascending": "true",
                                                   **base_params}, left, right, fetch):
            market_id = str(market.get("id"))
            if market_id not in seen:
                seen.add(market_id)
                out.append(market)
        if index % 5 == 0 or index == len(spans):
            log.info("%s: window %d/%d (%s), %d markets so far", label, index, len(spans), f"{left:%Y-%m-%d}", len(out))
    return out


def cached_history(path: Path, token: str, bucket: int, fetch, start_ts: int | None = None,
                   end_ts: int | None = None) -> dict:
    """Cached price history; refetched when empty or when it misses the start of the market's life."""
    if path.exists():
        cached = io.read_json(path)
        points = cached.get("points")
        if points and (start_ts is None or points[0]["t"] <= start_ts + 2 * 86_400 or "clob_windows" in cached.get("source", "")):
            return cached
    points, source = api.price_history(token, bucket, fetch, start_ts=start_ts, end_ts=end_ts)
    record = {"token_id": token, "bucket_seconds": bucket, "source": source, "points": points,
              "collected_at": datetime.now(timezone.utc).isoformat()}
    io.write_json(path, record, indent=None)
    return record


def choose_trade_filter(marker: Path, condition_id: str, filter_type: str, amount: float, fetch) -> tuple[str, float]:
    """Use the configured trade filter if the API accepts it, else fall back to a share filter."""
    if marker.exists():
        chosen = io.read_json(marker)
        return chosen["type"], chosen["amount"]
    try:
        fetch(f"{api.DATA}/v2/trades", {"condition": condition_id, "limit": 1, "taker_only": "false",
                                        "filter_type": filter_type, "filter_amount": amount})
        chosen = {"type": filter_type, "amount": amount}
    except ApiError as error:
        log.warning("trade filter %s rejected (%s); using TOKENS >= %s", filter_type, error, amount * 2)
        chosen = {"type": "TOKENS", "amount": amount * 2}
    io.write_json(marker, chosen)
    return chosen["type"], chosen["amount"]


def download_trades(raw_dir: Path, out_csv: Path, market: dict, filter_type: str, amount: float,
                    page_size: int, max_pages: int, fetch) -> dict:
    """All served trade pages of one market (newest first) -> canonical CSV. Returns a status record."""
    status_path = raw_dir / "_status.json"
    if status_path.exists() and io.read_json(status_path).get("complete") and out_csv.exists():
        return io.read_json(status_path)
    pages = sorted(raw_dir.glob("page_*.json"))
    cursor = None
    if pages:
        cursor = (io.read_json(pages[-1])["response"].get("pagination") or {}).get("next_cursor")
    exhausted = bool(pages) and not cursor
    number = len(pages)
    if not exhausted and number < max_pages:
        for request_cursor, response in api.trade_pages(market["condition_id"], filter_type, amount, page_size,
                                                        max_pages - number, fetch, start_cursor=cursor):
            number += 1
            io.write_json(raw_dir / f"page_{number:05d}.json",
                          {"request_cursor": request_cursor, "response": response}, indent=None)
            cursor = (response.get("pagination") or {}).get("next_cursor")
            if not cursor:
                exhausted = True
    records = [r for path in sorted(raw_dir.glob("page_*.json")) for r in io.read_json(path)["response"]["data"]]
    trades, rejected = normalize_trade_records(records, market)
    io.write_csv(out_csv, trades)
    status = {"market_id": market["market_id"], "complete": True, "pages": number, "records": len(records),
              "trades": len(trades), "rejected": rejected, "exhausted": exhausted, "truncated": not exhausted,
              "filter": {"type": filter_type, "amount": amount},
              "finished_at": datetime.now(timezone.utc).isoformat()}
    io.write_json(status_path, status)
    _pack_pages(raw_dir)
    return status


def _pack_pages(raw_dir: Path) -> None:
    """Replace a finished market's page files by one gzip file (about 10x smaller on disk)."""
    pages = sorted(raw_dir.glob("page_*.json"))
    if not pages:
        return
    packed = raw_dir / "pages.jsonl.gz"
    tmp = raw_dir / "pages.jsonl.gz.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as handle:
        for path in pages:
            handle.write(json.dumps(io.read_json(path)) + "\n")
    tmp.replace(packed)
    for path in pages:
        path.unlink()


def run_parallel(items: list, work, workers: int, label: str, every: int = 50) -> list:
    """Apply ``work`` to every item with a few threads (downloads wait on the network, not the CPU).

    Failures are logged and skipped (the next run retries them); results keep no particular order.
    """
    from walletlens.config import project_root
    stop_file = project_root() / "STOP"
    results, started, done = [], time.time(), 0

    def guarded(item):
        if stop_file.exists():                       # a STOP file ends the run cleanly; rerun to resume
            raise KeyboardInterrupt
        return work(item)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(guarded, item): item for item in items}
        for future in as_completed(futures):
            done += 1
            if stop_file.exists():
                for pending in futures:
                    pending.cancel()
                log.warning("%s: STOP file found, stopping (rerun to resume)", label)
                raise SystemExit(3)
            try:
                results.append(future.result())
            except Exception as error:  # noqa: BLE001 - one market must not stop the rest
                log.warning("%s: one item failed (retried next run): %s", label, error)
            if done % every == 0 or done == len(items):
                elapsed = time.time() - started
                log.info("%s %d/%d (~%.0f min left)", label, done, len(items), elapsed / done * (len(items) - done) / 60)
    return results
