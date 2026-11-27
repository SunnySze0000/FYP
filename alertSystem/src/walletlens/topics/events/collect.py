"""T2 collector: hourly probability paths of contested event markets + hourly/daily asset prices.

The candidate list comes from topic F's first stage (``data/interim/universe/candidates.csv``),
so this collector waits for that file when both run in parallel. It does its own "contested"
screen from the hourly prices it downloads anyway.

    python -m walletlens events collect [--stages assets,wait,prices,build]
"""

from __future__ import annotations

import re

import time

import pandas as pd

from walletlens import io, logs
from walletlens.collect.common import cached_history, run_parallel
from walletlens.config import ASSET_GROUPS, GROUP_KEYWORDS, Settings
from walletlens.polymarket import yahoo
from walletlens.polymarket.http import ApiError, get_json

log = logs.get("collect.events")
DTYPES = {"market_id": str, "yes_token": str, "no_token": str, "group_id": str, "condition_id": str}


def _pattern(word: str) -> re.Pattern:
    stem = word.endswith("*")
    word = word.rstrip("*")
    return re.compile(r"(?<![a-z0-9])" + re.escape(word) + ("" if stem else r"(?![a-z0-9])"))


PATTERNS = {group: [_pattern(w) for w in words] for group, words in GROUP_KEYWORDS.items()}


def groups_for(question: str) -> list[str]:
    text = str(question).lower().replace("\u2019", "'")
    return [group for group, patterns in PATTERNS.items() if any(p.search(text) for p in patterns)]


def all_assets(settings: Settings) -> list[str]:
    assets = {"SPY"} | set(settings.events.extra_assets)
    for members in ASSET_GROUPS.values():
        assets |= set(members)
    return sorted(assets)


def stage_assets(settings: Settings, fetch=get_json) -> None:
    cfg = settings.events
    for symbol in all_assets(settings):
        for interval, range_, seconds in (("60m", cfg.yahoo_hourly_range, 3600), ("1d", cfg.yahoo_daily_range, 86_400)):
            path = settings.paths.raw / "yahoo" / interval / f"{symbol.replace('^', '_')}.json"
            if path.exists():
                continue
            try:
                payload = yahoo.chart(symbol, interval, range_, fetch)
            except ApiError as error:
                log.warning("yahoo %s %s failed: %s", symbol, interval, error)
                continue
            io.write_json(path, payload, indent=None)
            log.info("yahoo %s %s: %d bars", symbol, interval, len(yahoo.bars(payload, seconds)))


def stage_wait(settings: Settings, poll_s: int = 60, max_hours: float = 6) -> None:
    screen = settings.paths.interim / "universe" / "candidates.csv"
    waited = 0.0
    while not screen.exists():
        if waited == 0:
            log.info("waiting for topic F's market list (%s) ...", screen)
        time.sleep(poll_s)
        waited += poll_s
        if waited > max_hours * 3600:
            raise TimeoutError("topic F market list never appeared; run `walletlens collect --stages universe` first")


def select_markets(settings: Settings) -> pd.DataFrame:
    candidates = pd.read_csv(settings.paths.interim / "universe" / "candidates.csv", dtype=DTYPES)
    candidates["groups"] = candidates["question"].map(lambda q: "|".join(groups_for(q)))
    mapped = candidates[candidates["groups"] != ""].sort_values("volume_usd", ascending=False)
    # balance the groups: at most max_per_group markets from each (by volume), then the overall cap
    mapped = mapped.assign(first_group=mapped["groups"].str.split("|").str[0])
    mapped = mapped.groupby("first_group", group_keys=False).head(settings.events.max_per_group).drop(columns="first_group")
    chosen = mapped.sort_values("volume_usd", ascending=False).head(settings.events.max_markets).reset_index(drop=True)
    io.write_csv(settings.paths.interim / "events" / "markets.csv", chosen)
    log.info("events: %d keyword-mapped markets (of %d candidates); by group %s", len(chosen), len(candidates),
             chosen["groups"].str.split("|").explode().value_counts().to_dict())
    return chosen


def stage_prices(settings: Settings, fetch=get_json, workers: int = 6) -> None:
    markets = select_markets(settings)
    days = settings.events.history_days

    def work(market):
        start = max(int(market["start_ts"]), int(market["close_ts"]) - days * 86_400)
        return cached_history(settings.paths.raw / "prices_1h_events" / f"{market['market_id']}.json",
                              market["yes_token"], settings.events.price_bucket_seconds, fetch, start,
                              int(market["close_ts"]))

    run_parallel(markets.to_dict("records"), work, workers, "event prices")


def stage_trades(settings: Settings, fetch=get_json, workers: int = 10) -> None:
    """Wallet-level trades for the contested event markets (for the wallet directions W1-W5).

    Markets with the most probability jumps come first, so a run stopped early (STOP file) still
    covers the markets that matter most; ``trades_build`` uses whatever has been downloaded.
    """
    from walletlens.collect.common import choose_trade_filter, download_trades
    processed = settings.paths.dataset("events") / "markets.csv"
    frame = pd.read_csv(processed if processed.exists() else settings.paths.interim / "events" / "markets.csv",
                        dtype=DTYPES)
    prices_path = settings.paths.dataset("events") / "prices.pkl.gz"
    if prices_path.exists():
        prices = io.read_table(prices_path).sort_values(["market_id", "ts"])
        jumps = (prices.groupby("market_id")["yes_price"].diff().abs() >= settings.events.shock_points) \
            .groupby(prices["market_id"]).sum()
        frame = frame.assign(jumps=frame["market_id"].map(jumps).fillna(0)).sort_values("jumps", ascending=False)
    markets = frame.to_dict("records")
    if not markets:
        return
    amount_tag = f"events_trades_{int(settings.events.trade_filter_amount)}"      # one folder per trade filter
    marker = settings.paths.raw / amount_tag / "_filter.json"
    choose_trade_filter(marker, markets[0]["condition_id"], "CASH", settings.events.trade_filter_amount, fetch)

    def work(market):
        filter_type, amount = choose_trade_filter(marker, market["condition_id"], "CASH",
                                                  settings.events.trade_filter_amount, fetch)
        return download_trades(settings.paths.raw / amount_tag / market["market_id"],
                               settings.paths.interim / amount_tag / f"{market['market_id']}.csv.gz",
                               market, filter_type, amount, 1000, settings.events.max_trade_pages, fetch)

    statuses = run_parallel(markets, work, workers, "event trades", every=25)
    io.write_csv(settings.paths.interim / "events" / "trades_status.csv", pd.DataFrame(statuses))


def stage_trades_build(settings: Settings) -> None:
    from walletlens.data.schema import compact_trades
    folder = settings.paths.dataset("events")
    markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)
    amount_tag = f"events_trades_{int(settings.events.trade_filter_amount)}"
    parts = [settings.paths.interim / amount_tag / f"{m}.csv.gz" for m in markets["market_id"]]
    frames = [pd.read_csv(p, dtype={"market_id": str, "wallet": str}) for p in parts if p.exists()]
    trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    io.write_table(folder / "trades.pkl.gz", compact_trades(trades) if len(trades) else trades)
    log.info("event trades: %d trades by %d wallets in %d markets", len(trades),
             trades["wallet"].nunique() if len(trades) else 0, len(frames))


def stage_build(settings: Settings) -> None:
    from walletlens.topics.events.build import build_events
    build_events(settings)


STAGES = ("assets", "wait", "prices", "build", "trades", "trades_build")


def run(settings: Settings, stages=STAGES, fetch=get_json) -> None:
    for stage in stages:
        log.info("=== events stage %s ===", stage)
        {"assets": lambda: stage_assets(settings, fetch), "wait": lambda: stage_wait(settings),
         "prices": lambda: stage_prices(settings, fetch), "build": lambda: stage_build(settings),
         "trades": lambda: stage_trades(settings, fetch), "trades_build": lambda: stage_trades_build(settings)}[stage]()
