"""Daily-use applicability check D1-D6 (pre-registered in docs/05_daily_applicability.md).

Everything here uses the **point-in-time watch rule**: at hour t a market is watched if it has at least 24
hours of price history before t and its probability one hour earlier was between 10% and 90%.

``events_all`` is the T2 dataset rebuilt from **all** candidate markets, without the hindsight "contested"
filter used by the research dataset ``events``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import cached_property

import numpy as np
import pandas as pd

from walletlens import io, logs
from walletlens.config import ASSET_GROUPS, EventsConfig, Settings
from walletlens.topics.events.collect import DTYPES
from walletlens.topics.events.panel import _beta, _logit, _price_at, placebo_assets
from walletlens.topics.events.wallet_context import WalletContext

log = logs.get("events.daily")
WATCH_LOW, WATCH_HIGH, WATCH_AGE = 0.10, 0.90, 24 * 3600
PORTFOLIO = ("SPY", "QQQ", "TLT", "GLD", "USO", "BTC-USD")
BIG_QUANTILE = 0.80


# --------------------------------------------------------------------------- dataset without hindsight
def build_events_all(settings: Settings, name: str = "events_all", source: str = "events") -> None:
    markets = pd.read_csv(settings.paths.interim / "events" / "markets.csv", dtype=DTYPES)
    rows = []
    for market_id in markets["market_id"]:
        path = settings.paths.raw / "prices_1h_events" / f"{market_id}.json"
        if path.exists():
            rows += [(market_id, p["t"], p["p"]) for p in io.read_json(path)["points"]]
    prices = pd.DataFrame(rows, columns=["market_id", "ts", "yes_price"]).astype(
        {"market_id": str, "ts": "int64", "yes_price": float})
    markets = markets[markets["market_id"].isin(set(prices["market_id"]))]
    folder, base = settings.paths.dataset(name), settings.paths.dataset(source)
    io.write_csv(folder / "markets.csv", markets)
    io.write_table(folder / "prices.pkl.gz", prices)
    for table in ("assets_hourly", "assets_daily"):
        io.write_table(folder / f"{table}.pkl.gz", io.read_table(base / f"{table}.pkl.gz"))
    io.write_json(folder / "manifest.json", {"dataset": name, "built_at": datetime.now(timezone.utc).isoformat(),
                                             "markets": int(len(markets)), "price_points": int(len(prices)),
                                             "note": "all candidate markets, no contested filter (D1)"})
    log.info("events_all: %d markets, %d price points", len(markets), len(prices))


# --------------------------------------------------------------------------- watched shock panel
class Book:
    def __init__(self, bars: pd.DataFrame, close_ts: pd.Series):
        bars = bars.assign(close_ts=close_ts).sort_values("close_ts")
        self.series, self.big = {}, {}
        for symbol, g in bars.groupby("symbol"):
            ends, closes = g["close_ts"].to_numpy("int64"), g["close"].to_numpy(float)
            self.series[symbol] = (ends, closes)
            r = np.abs(np.diff(np.log(closes)))
            self.big[symbol] = float(np.nanquantile(r, BIG_QUANTILE)) if len(r) > 20 else np.nan


def hourly_book(hourly: pd.DataFrame) -> Book:
    return Book(hourly, hourly["end_ts"])


def daily_book(daily: pd.DataFrame) -> Book:
    crypto = daily["symbol"].str.endswith("-USD")
    close = np.where(crypto, daily["start_ts"] + 86_400, daily["start_ts"] + 23_400)   # 16:00 ET close for stocks
    return Book(daily, pd.Series(close, index=daily.index))


def watched_panel(markets: pd.DataFrame, prices: pd.DataFrame, book: Book, cfg: EventsConfig,
                  max_gap: int = 3600) -> dict:
    """Like panel.analyse, but only watched hours count (normal and shock), and each shock row carries
    its timestamp, the asset's own big-move threshold and the market's volume."""
    pool = sorted(s for s in book.series if s in {a for m in ASSET_GROUPS.values() for a in m})
    groups_of = {m: (g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float))
                 for m, g in prices.sort_values("ts").groupby("market_id")}
    pairs, shocks = [], []
    for market in markets.itertuples(index=False):
        if market.market_id not in groups_of:
            continue
        p_times, p_values = groups_of[market.market_id]
        groups = [g for g in str(market.groups).split("|") if g]
        mapped = {a for g in groups for a in ASSET_GROUPS.get(g, ())}
        for asset, kind in [(a, "mapped") for a in sorted(mapped)] + \
                           [(a, "placebo") for a in placebo_assets(market.market_id, mapped, pool)]:
            if asset not in book.series:
                continue
            ends, closes = book.series[asset]
            inside = (ends > p_times[0] + WATCH_AGE) & (ends <= min(market.close_ts, p_times[-1] + 3600))
            index = np.nonzero(inside)[0]
            index = index[(index >= 1) & (index < len(ends) - 1)]
            if len(index) < 10:
                continue
            x, x_prev = ends[index], ends[index - 1]
            same = (x - x_prev <= max_gap)
            p_now = _price_at(p_times, p_values, x, 2 * 3600)
            p_before = _price_at(p_times, p_values, x_prev, 2 * 3600)
            watched = (p_before >= WATCH_LOW) & (p_before <= WATCH_HIGH) & (x_prev - p_times[0] >= WATCH_AGE)
            dp = p_now - p_before
            r = np.log(closes[index] / closes[index - 1])
            ok = same & watched & np.isfinite(dp) & np.isfinite(r)
            if ok.sum() < 10:
                continue
            dp, r, x = dp[ok], r[ok], x[ok]
            shock = np.abs(dp) >= cfg.shock_points
            normal = float(np.abs(r[~shock]).mean()) if (~shock).any() else np.nan
            pairs.append({"market_id": market.market_id, "asset": asset, "kind": kind, "groups": market.groups,
                          "volume_usd": market.volume_usd, "hours": int(len(x)), "shocks": int(shock.sum()),
                          "abs_r_normal": normal,
                          "abs_r_shock": float(np.abs(r[shock]).mean()) if shock.any() else np.nan,
                          "big_rate_shock": float((np.abs(r[shock]) >= book.big[asset]).mean()) if shock.any() else np.nan,
                          "big_rate_normal": float((np.abs(r[~shock]) >= book.big[asset]).mean()) if (~shock).any() else np.nan})
            for i in np.nonzero(shock)[0]:
                shocks.append({"market_id": market.market_id, "asset": asset, "kind": kind, "ts": int(x[i]),
                               "dp": float(dp[i]), "r": float(r[i]), "abs_r_normal": normal,
                               "big": bool(abs(r[i]) >= book.big[asset]), "groups": market.groups})
    pairs, shocks = pd.DataFrame(pairs), pd.DataFrame(shocks)
    log.info("watched panel: %d pairs, %d shock rows", len(pairs), len(shocks))
    return {"pairs": pairs, "shocks": shocks}


def alert_hours(markets: pd.DataFrame, prices: pd.DataFrame, shock_points: float) -> pd.DataFrame:
    """Every watched market-hour with |dp| >= shock: what the app would alert on, asset hours or not."""
    rows = []
    for market_id, g in prices.sort_values("ts").groupby("market_id"):
        times, values = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        grid = np.arange(times[0] // 3600 * 3600 + 3600, times[-1] + 1, 3600, dtype="int64")
        p = _price_at(times, values, grid, 2 * 3600)
        prev = _price_at(times, values, grid - 3600, 2 * 3600)
        watched = (prev >= WATCH_LOW) & (prev <= WATCH_HIGH) & (grid - 3600 - times[0] >= WATCH_AGE)
        hit = watched & (np.abs(p - prev) >= shock_points)
        rows.append(pd.DataFrame({"market_id": market_id, "ts": grid[hit]}))
        rows.append(pd.DataFrame({"market_id": market_id, "ts": grid[watched & ~hit], "quiet": True}))
    frame = pd.concat(rows, ignore_index=True)
    frame["quiet"] = frame["quiet"].fillna(False).astype(bool)
    return frame.merge(markets[["market_id", "groups"]], on="market_id", how="left")


# --------------------------------------------------------------------------- context
class DailyContext(WalletContext):
    """Research dataset ``events`` (with wallet trades) plus the hindsight-free ``events_all``."""

    def __init__(self, settings: Settings, dataset: str = "events"):
        super().__init__(settings, dataset)
        folder = settings.paths.dataset("events_all")
        if not (folder / "manifest.json").exists():
            build_events_all(settings)
        from walletlens.topics.events.collect import groups_for
        self.all_markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)
        self.all_markets["groups"] = self.all_markets["question"].map(lambda q: "|".join(groups_for(q)))
        self.all_markets = self.all_markets[self.all_markets["groups"] != ""].reset_index(drop=True)
        self.all_prices = io.read_table(folder / "prices.pkl.gz")
        log.info("events_all: %d markets", len(self.all_markets))

    @cached_property
    def watched(self) -> dict:
        return watched_panel(self.all_markets, self.all_prices, hourly_book(self.hourly), self.cfg)

    @cached_property
    def watched_daily(self) -> dict:
        return watched_panel(self.all_markets, self.all_prices, daily_book(self.daily), self.cfg, max_gap=4 * 86_400)

    @cached_property
    def alerts(self) -> pd.DataFrame:
        return alert_hours(self.all_markets, self.all_prices, self.cfg.shock_points)

    @cached_property
    def watched_hours(self) -> pd.DataFrame:
        """W3/W5 hourly wallet panel restricted to watched hours."""
        hours = self.hours.copy()
        first = self.prices.groupby("market_id")["ts"].min()
        prev = hours["p"] - hours["dp"]
        age = hours["ts"] - 3600 - hours["market_id"].map(first)
        keep = (prev >= WATCH_LOW) & (prev <= WATCH_HIGH) & (age >= WATCH_AGE)
        log.info("watched wallet hours: %d of %d", int(keep.sum()), len(hours))
        return hours[keep].reset_index(drop=True)


def quarter(ts) -> pd.Series:
    return pd.to_datetime(pd.Series(ts), unit="s").dt.to_period("Q").astype(str)


def decide(verdicts: dict) -> str:
    required = ("d1", "d2", "d3", "d4", "d6")
    missing = [k for k in required if verdicts.get(k) is None]
    failed = [k for k in required if verdicts.get(k) not in (None, "pass")]
    if failed:
        return ("Do NOT build yet: " + ", ".join(k.upper() for k in failed) + " failed. Diagnose and test a fix "
                "(docs/05_daily_applicability.md).")
    if missing:
        return "Incomplete: " + ", ".join(k.upper() for k in missing) + " not run yet (D4 needs the laptop live check)."
    digest = "with a daily digest" if verdicts.get("d5") == "pass" else "without a daily digest (D5 failed)"
    return f"All required daily-use gates pass: build prototype v1 {digest}."
