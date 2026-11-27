"""T1 dataset: ``data/processed/crypto/`` = markets.csv, trades.pkl.gz, spot.pkl.gz, manifest.json."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from walletlens import io, logs
from walletlens.config import Settings
from walletlens.data.schema import MARKET_COLUMNS, compact_trades, validate_trades
from walletlens.topics.crypto.collect import DTYPES, SYMBOLS

log = logs.get("build.crypto")
EXTRA = ["asset", "kind", "window_start", "window_end", "window_source"]


def build_crypto(settings: Settings, name: str = "crypto") -> None:
    interim = settings.paths.interim
    sample = pd.read_csv(interim / "crypto" / "sample.csv", dtype=DTYPES)
    done = [m for m in sample["market_id"] if (interim / "crypto_trades" / f"{m}.csv.gz").exists()]
    markets = sample[sample["market_id"].isin(done)][MARKET_COLUMNS + EXTRA].copy()
    trades = pd.concat([pd.read_csv(interim / "crypto_trades" / f"{m}.csv.gz", dtype={"market_id": str, "wallet": str})
                        for m in done], ignore_index=True) if done else pd.DataFrame()
    spot_parts = []
    for asset in markets["asset"].unique():
        for path in sorted((settings.paths.raw / "spot" / SYMBOLS[asset]).glob("*.csv.gz")):
            spot_parts.append(pd.read_csv(path).assign(asset=asset))
    spot = pd.concat(spot_parts, ignore_index=True) if spot_parts else pd.DataFrame(
        columns=["ts", "open", "high", "low", "close", "volume", "asset"])
    spot = spot.drop_duplicates(["asset", "ts"]).sort_values(["asset", "ts"]).reset_index(drop=True)

    folder = settings.paths.dataset(name)
    io.write_csv(folder / "markets.csv", markets)
    io.write_table(folder / "trades.pkl.gz", compact_trades(trades) if len(trades) else trades)
    io.write_table(folder / "spot.pkl.gz", spot)
    manifest = {
        "dataset": name, "built_at": datetime.now(timezone.utc).isoformat(),
        "markets": int(len(markets)), "sampled": int(len(sample)), "trades": int(len(trades)),
        "wallets": int(trades["wallet"].nunique()) if len(trades) else 0,
        "by_asset_kind": {f"{a}-{k}": int(n) for (a, k), n in markets.groupby(["asset", "kind"]).size().items()},
        "spot_minutes": {a: int(n) for a, n in spot.groupby("asset").size().items()},
        "validation_problems": validate_trades(trades) if len(trades) else ["no trades"],
        "config": settings.crypto.__dict__,
    }
    io.write_json(folder / "manifest.json", manifest)
    log.info("crypto dataset: %d markets, %d trades, spot %s", manifest["markets"], manifest["trades"],
             manifest["spot_minutes"])


def load_crypto(settings: Settings, name: str = "crypto") -> dict:
    folder = settings.paths.dataset(name)
    markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)
    return {"markets": markets, "trades": io.read_table(folder / "trades.pkl.gz"),
            "spot": io.read_table(folder / "spot.pkl.gz"), "manifest": io.read_json(folder / "manifest.json")}
