"""Topic F collector: a random sample of *contested* resolved markets with all their trades.

Stages (each one caches raw responses under ``data/raw`` and can be re-run safely):

1. ``universe``  resolved binary markets from Gamma, in date windows (offset-cap safe)
2. ``screen``    12-hour price path of each candidate -> was it ever contested?
3. ``sample``    contested markets in a fixed random order (seeded)
4. ``download``  hourly prices + all trades >= $X for sampled markets, in sample order
5. ``build``     analysis tables in ``data/processed/universe``

Because ``download`` follows the random order, stopping early still leaves a random subset.
The ``screen`` output is also the market list for topic T2 (event shocks -> assets).
"""

from __future__ import annotations

import random
import time

import pandas as pd

from walletlens import io, logs
from walletlens.collect.common import (cached_history, choose_trade_filter, download_trades, run_parallel,
                                       scan_closed_markets)
from walletlens.config import Settings
from walletlens.data.markets import market_row
from walletlens.polymarket.http import ApiError, get_json

log = logs.get("collect.universe")
MARKET_DTYPES = {"market_id": str, "yes_token": str, "no_token": str, "group_id": str, "condition_id": str}


def stage_universe(settings: Settings, fetch=get_json) -> pd.DataFrame:
    cfg = settings.collect
    raw = scan_closed_markets(settings.paths.raw / "gamma", cfg.closed_from, cfg.closed_to,
                              {"volume_num_min": cfg.min_volume_usd}, fetch, label="universe")
    rows, reasons = [], {}
    for market in raw:
        row, reason = market_row(market)
        if row and (row["close_ts"] - row["start_ts"]) < cfg.min_duration_days * 86_400:
            row, reason = None, "too_short"
        reasons[reason] = reasons.get(reason, 0) + 1
        if row:
            rows.append(row)
    frame = pd.DataFrame(rows).sort_values("market_id").reset_index(drop=True)
    out = settings.paths.interim / "universe"
    io.write_csv(out / "candidates.csv", frame)
    io.write_json(out / "candidates_report.json", {"markets_seen": len(raw), "kept": len(rows),
                                                   "reasons": reasons, "config": cfg.__dict__})
    log.info("universe done: %d candidates of %d markets (%s)", len(frame), len(raw), reasons)
    return frame


def stage_screen(settings: Settings, fetch=get_json) -> pd.DataFrame:
    """12-hour price path of candidates, in a fixed random order, until enough contested markets are found."""
    cfg = settings.collect
    candidates = pd.read_csv(settings.paths.interim / "universe" / "candidates.csv", dtype=MARKET_DTYPES)
    order = sorted(candidates["market_id"])
    random.Random(cfg.seed).shuffle(order)
    candidates = candidates.set_index("market_id").loc[order].reset_index()
    target = int(cfg.sample_size * 1.2)
    rows, started, contested = [], time.time(), 0
    for index, market in enumerate(candidates.itertuples(index=False), 1):
        path = settings.paths.raw / "prices_12h" / f"{market.market_id}.json"
        try:
            record = cached_history(path, market.yes_token, cfg.screen_bucket_seconds, fetch)
        except ApiError as error:
            log.warning("screen %s failed: %s", market.market_id, error)
            continue
        prices = [p["p"] for p in record["points"] if market.start_ts <= p["t"] <= market.close_ts]
        inside = sum(cfg.contested_low <= p <= cfg.contested_high for p in prices)
        is_contested = inside >= cfg.min_contested_points
        contested += is_contested
        rows.append({"market_id": market.market_id, "points": len(prices), "contested_points": inside,
                     "min_price": min(prices) if prices else None, "max_price": max(prices) if prices else None,
                     "contested": is_contested})
        if index % 100 == 0:
            log.info("screen %d screened, %d contested (target %d, %.0f s)", index, contested, target,
                     time.time() - started)
        if contested >= target:
            break
    screen = pd.DataFrame(rows)
    io.write_csv(settings.paths.interim / "universe" / "screen.csv", screen)
    log.info("screen done: %d contested of %d screened (%d candidates in total)", contested, len(screen), len(candidates))
    return screen


def stage_sample(settings: Settings) -> pd.DataFrame:
    cfg = settings.collect
    folder = settings.paths.interim / "universe"
    candidates = pd.read_csv(folder / "candidates.csv", dtype=MARKET_DTYPES)
    screen = pd.read_csv(folder / "screen.csv", dtype={"market_id": str})
    contested = candidates.merge(screen[screen["contested"]], on="market_id")
    ids = sorted(contested["market_id"])
    random.Random(cfg.seed).shuffle(ids)
    order = {market_id: rank for rank, market_id in enumerate(ids)}
    sample = contested.assign(sample_rank=contested["market_id"].map(order)).sort_values("sample_rank")
    sample = sample.head(cfg.sample_size).reset_index(drop=True)
    io.write_csv(folder / "sample.csv", sample)
    log.info("sample: %d of %d contested markets (%s)", len(sample), len(contested),
             sample["category"].value_counts().to_dict())
    return sample


def download_market(settings: Settings, market: dict, fetch=get_json) -> dict:
    cfg = settings.collect
    market_id = market["market_id"]
    cached_history(settings.paths.raw / "prices_1h" / f"{market_id}.json", market["yes_token"],
                   cfg.price_bucket_seconds, fetch, int(market["start_ts"]), int(market["close_ts"]))
    filter_type, amount = choose_trade_filter(settings.paths.raw / "trades" / "_filter.json", market["condition_id"],
                                              cfg.trade_filter_type, cfg.trade_filter_amount, fetch)
    return download_trades(settings.paths.raw / "trades" / market_id,
                           settings.paths.interim / "trades" / f"{market_id}.csv.gz", market, filter_type, amount,
                           cfg.trade_page_size, cfg.max_trade_pages, fetch)


def stage_download(settings: Settings, max_markets: int | None = None, fetch=get_json, workers: int = 4) -> pd.DataFrame:
    sample = pd.read_csv(settings.paths.interim / "universe" / "sample.csv", dtype=MARKET_DTYPES)
    if max_markets:
        sample = sample.head(max_markets)
    markets = sample.to_dict("records")
    if markets:
        cfg = settings.collect
        choose_trade_filter(settings.paths.raw / "trades" / "_filter.json", markets[0]["condition_id"],
                            cfg.trade_filter_type, cfg.trade_filter_amount, fetch)
    statuses = run_parallel(markets, lambda m: download_market(settings, m, fetch), workers, "universe download", every=10)
    frame = pd.DataFrame(statuses)
    io.write_csv(settings.paths.interim / "download_status.csv", frame)
    return frame


STAGES = ("universe", "screen", "sample", "download", "build")


def run(settings: Settings, stages=STAGES, max_markets: int | None = None, fetch=get_json) -> None:
    from walletlens.data.build import build_universe  # local import keeps the collector light

    for stage in stages:
        log.info("=== universe stage %s ===", stage)
        if stage == "universe":
            stage_universe(settings, fetch)
        elif stage == "screen":
            stage_screen(settings, fetch)
        elif stage == "sample":
            stage_sample(settings)
        elif stage == "download":
            stage_download(settings, max_markets, fetch)
        elif stage == "build":
            build_universe(settings)
        else:
            raise ValueError(f"unknown stage {stage}")
