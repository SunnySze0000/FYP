"""T2 dataset: ``data/processed/events/`` = markets.csv, prices.pkl.gz, assets_hourly.pkl.gz,
assets_daily.pkl.gz, manifest.json."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from walletlens import io, logs
from walletlens.config import Settings
from walletlens.polymarket import yahoo
from walletlens.topics.events.collect import DTYPES

log = logs.get("build.events")


def _assets(settings: Settings, interval: str, seconds: int) -> pd.DataFrame:
    rows = []
    for path in sorted((settings.paths.raw / "yahoo" / interval).glob("*.json")):
        symbol = path.stem.replace("_", "^", 1) if path.stem.startswith("_") else path.stem
        rows += [(symbol, start, end, close) for start, end, close in yahoo.bars(io.read_json(path), seconds)]
    return pd.DataFrame(rows, columns=["symbol", "start_ts", "end_ts", "close"]).drop_duplicates(["symbol", "start_ts"])


def build_events(settings: Settings, name: str = "events") -> None:
    markets = pd.read_csv(settings.paths.interim / "events" / "markets.csv", dtype=DTYPES)
    price_rows = []
    for market_id in markets["market_id"]:
        path = settings.paths.raw / "prices_1h_events" / f"{market_id}.json"
        if path.exists():
            price_rows += [(market_id, p["t"], p["p"]) for p in io.read_json(path)["points"]]
    prices = pd.DataFrame(price_rows, columns=["market_id", "ts", "yes_price"]).astype(
        {"market_id": str, "ts": "int64", "yes_price": float})
    # contested = at least a day and a half of hourly prices inside the 15-85% band
    cfg = settings.collect
    inside = prices[(prices["yes_price"] >= cfg.contested_low) & (prices["yes_price"] <= cfg.contested_high)]
    contested = inside.groupby("market_id").size()
    keep = set(contested[contested >= 36].index)
    log.info("events: %d of %d markets with prices are contested", len(keep), prices["market_id"].nunique())
    markets = markets[markets["market_id"].isin(keep)]
    prices = prices[prices["market_id"].isin(keep)]
    hourly, daily = _assets(settings, "60m", 3600), _assets(settings, "1d", 86_400)
    folder = settings.paths.dataset(name)
    io.write_csv(folder / "markets.csv", markets)
    io.write_table(folder / "prices.pkl.gz", prices)
    io.write_table(folder / "assets_hourly.pkl.gz", hourly)
    io.write_table(folder / "assets_daily.pkl.gz", daily)
    manifest = {"dataset": name, "built_at": datetime.now(timezone.utc).isoformat(), "markets": int(len(markets)),
                "price_points": int(len(prices)), "assets_hourly": hourly.groupby("symbol").size().to_dict(),
                "assets_daily": int(daily["symbol"].nunique()),
                "groups": markets["groups"].str.split("|").explode().value_counts().to_dict()}
    io.write_json(folder / "manifest.json", manifest)
    log.info("events dataset: %d markets, %d price points, %d hourly asset series", len(markets), len(prices),
             hourly["symbol"].nunique())


def load_events(settings: Settings, name: str = "events") -> dict:
    from walletlens.topics.events.collect import groups_for

    folder = settings.paths.dataset(name)
    markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)
    markets["groups"] = markets["question"].map(lambda q: "|".join(groups_for(q)))     # D-fix-1 word matching
    markets = markets[markets["groups"] != ""].reset_index(drop=True)
    return {"markets": markets,
            "prices": io.read_table(folder / "prices.pkl.gz"),
            "assets_hourly": io.read_table(folder / "assets_hourly.pkl.gz"),
            "assets_daily": io.read_table(folder / "assets_daily.pkl.gz"),
            "manifest": io.read_json(folder / "manifest.json")}
