"""Build analysis-ready datasets in ``data/processed/<name>/``.

Each dataset folder holds the same four files, whatever the source:

* ``markets.csv``        canonical market table
* ``trades.pkl.gz``      canonical trades (compact dtypes)
* ``prices.pkl.gz``      YES price series (hourly)
* ``manifest.json``      where it came from, row counts, checks

Two sources are supported:

* ``universe``  produced by the collector (``walletlens collect``)
* ``pilot_fed`` the Fed-meeting trade exports already collected for the earlier FYP work
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from walletlens import io, logs
from walletlens.config import Settings
from walletlens.data.markets import market_row
from walletlens.data.schema import (MARKET_COLUMNS, PRICE_COLUMNS, compact_trades, tx_key,
                                    validate_markets, validate_trades)

log = logs.get("build")


def _write_dataset(settings: Settings, name: str, markets: pd.DataFrame, trades: pd.DataFrame,
                   prices: pd.DataFrame, source: dict) -> Path:
    folder = settings.paths.dataset(name)
    problems = validate_markets(markets) + validate_trades(trades)
    trades = trades[trades["market_id"].astype(str).isin(set(markets["market_id"]))]
    io.write_csv(folder / "markets.csv", markets[MARKET_COLUMNS])
    io.write_table(folder / "trades.pkl.gz", compact_trades(trades))
    io.write_table(folder / "prices.pkl.gz", prices[PRICE_COLUMNS].reset_index(drop=True))
    manifest = {
        "dataset": name, "built_at": datetime.now(timezone.utc).isoformat(), "source": source,
        "markets": int(len(markets)), "groups": int(markets["group_id"].nunique()),
        "trades": int(len(trades)), "wallets": int(trades["wallet"].nunique()),
        "price_points": int(len(prices)),
        "first_close": datetime.fromtimestamp(int(markets["close_ts"].min()), timezone.utc).isoformat(),
        "last_close": datetime.fromtimestamp(int(markets["close_ts"].max()), timezone.utc).isoformat(),
        "categories": markets["category"].value_counts().to_dict(),
        "yes_rate": float(markets["outcome_yes"].mean()),
        "validation_problems": problems,
    }
    io.write_json(folder / "manifest.json", manifest)
    log.info("dataset %s: %d markets, %d trades, %d wallets, problems=%s", name, manifest["markets"],
             manifest["trades"], manifest["wallets"], problems or "none")
    return folder


def hourly_prices_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Last traded YES price in each hour (used when no price history was downloaded)."""
    yes_price = np.where(trades["token"].astype(str) == "YES", trades["price"], 1 - trades["price"])
    frame = pd.DataFrame({"market_id": trades["market_id"].astype(str), "hour": trades["ts"] // 3600 * 3600,
                          "ts": trades["ts"], "yes_price": yes_price})
    frame = frame.sort_values(["market_id", "ts"], kind="stable")
    last = frame.groupby(["market_id", "hour"], sort=True, observed=True).tail(1)
    return pd.DataFrame({"market_id": last["market_id"].to_numpy(), "ts": last["hour"].to_numpy() + 3599,
                         "yes_price": last["yes_price"].to_numpy()})


# --------------------------------------------------------------------------- universe

def build_universe(settings: Settings, name: str = "universe") -> Path:
    interim = settings.paths.interim
    sample = pd.read_csv(interim / "universe" / "sample.csv", dtype={"market_id": str, "yes_token": str,
                         "no_token": str, "group_id": str})
    done = [m for m in sample["market_id"] if (interim / "trades" / f"{m}.csv.gz").exists()]
    markets = sample[sample["market_id"].isin(done)].copy()
    trades = pd.concat([pd.read_csv(interim / "trades" / f"{m}.csv.gz", dtype={"market_id": str, "wallet": str})
                        for m in done], ignore_index=True) if done else pd.DataFrame()
    price_rows = []
    for market_id in done:
        path = settings.paths.raw / "prices_1h" / f"{market_id}.json"
        if path.exists():
            price_rows += [(market_id, p["t"], p["p"]) for p in io.read_json(path)["points"]]
    prices = pd.DataFrame(price_rows, columns=PRICE_COLUMNS).astype({"market_id": str, "ts": "int64", "yes_price": float})
    status_path = interim / "download_status.csv"
    truncated = []
    if status_path.exists():
        status = pd.read_csv(status_path, dtype={"market_id": str})
        truncated = status.loc[status["truncated"].astype(bool), "market_id"].tolist()
    source = {"kind": "collector", "sampled": int(len(sample)), "downloaded": len(done),
              "truncated_markets": truncated, "collect_config": settings.collect.__dict__}
    return _write_dataset(settings, name, markets, trades, prices, source)


# --------------------------------------------------------------------------- pilot (existing FYP exports)

def _infer_outcome(trades: pd.DataFrame, close_ts: int) -> int:
    """Outcome from the final hours of trading, for exports without Gamma metadata."""
    tail = trades[trades["ts"] >= close_ts - 6 * 3600]
    yes_price = np.where(tail["token"] == "YES", tail["price"], 1 - tail["price"])
    return int(np.median(yes_price) > 0.5)


def build_pilot(settings: Settings, export_dirs: list[Path], name: str = "pilot_fed") -> Path:
    """Fed trade exports (``wallet_trades.csv.gz`` + optional ``raw/market.json``) -> dataset."""
    markets, frames = [], []
    for folder in export_dirs:
        trades_raw = pd.read_csv(folder / "wallet_trades.csv.gz",
                                 usecols=["timestamp_utc", "market_id", "event_id", "meeting_month",
                                          "rate_outcome", "token_outcome", "wallet_address", "side",
                                          "shares", "price", "transaction_hash"],
                                 dtype={"market_id": str, "event_id": str})
        ts = (pd.to_datetime(trades_raw["timestamp_utc"], utc=True) - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
        trades = pd.DataFrame({"market_id": trades_raw["market_id"], "ts": ts.astype("int64"),
                               "wallet": trades_raw["wallet_address"].str.lower(),
                               "token": trades_raw["token_outcome"].str.upper(),
                               "side": trades_raw["side"].str.upper(), "price": trades_raw["price"],
                               "shares": trades_raw["shares"],
                               "tx": trades_raw["transaction_hash"].map(tx_key)})
        trades = trades[(trades["price"] > 0) & (trades["price"] < 1) & (trades["shares"] > 0)]
        meta_path = folder / "raw" / "market.json"
        first = trades_raw.iloc[0]
        if meta_path.exists():
            row, reason = market_row(json.loads(meta_path.read_text(encoding="utf-8")))
            if row is None:
                log.warning("skip %s: %s", folder.name, reason)
                continue
            row["group_id"] = f"fed-{first['meeting_month']}"
        else:
            close_ts = int(trades["ts"].max())
            row = {"market_id": str(first["market_id"]), "condition_id": "", "category": "economics",
                   "question": f"Fed {first['rate_outcome']} after the {first['meeting_month']} meeting?",
                   "group_id": f"fed-{first['meeting_month']}", "yes_token": "", "no_token": "",
                   "start_ts": int(trades["ts"].min()), "end_ts": close_ts, "close_ts": close_ts,
                   "outcome_yes": _infer_outcome(trades, close_ts), "volume_usd": float((trades["shares"] * trades["price"]).sum() / 2),
                   "resolution_source": "inferred_final_trades"}
        markets.append(row)
        frames.append(trades)
        log.info("pilot market %s (%s): %d trades, outcome_yes=%s", row["market_id"], row["group_id"],
                 len(trades), row["outcome_yes"])
    markets_frame = pd.DataFrame(markets)
    trades = pd.concat(frames, ignore_index=True)
    prices = hourly_prices_from_trades(trades)
    source = {"kind": "fyp_fed_exports", "folders": [str(p) for p in export_dirs],
              "note": "Full trade tape (0.01-share floor); prices are hourly last trades."}
    return _write_dataset(settings, name, markets_frame, trades, prices, source)


def load_dataset(settings: Settings, name: str) -> dict:
    folder = settings.paths.dataset(name)
    markets = pd.read_csv(folder / "markets.csv", dtype={"market_id": str, "group_id": str,
                          "yes_token": str, "no_token": str, "condition_id": str})
    trades = io.read_table(folder / "trades.pkl.gz")
    prices = io.read_table(folder / "prices.pkl.gz").astype({"market_id": str, "ts": "int64", "yes_price": float})
    return {"name": name, "markets": markets, "trades": trades, "prices": prices,
            "manifest": io.read_json(folder / "manifest.json")}
