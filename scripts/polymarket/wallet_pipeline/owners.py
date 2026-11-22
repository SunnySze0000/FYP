"""Stage 1: sniper / same-owner grouping from co-timed trading.

Hypothesis: addresses run by one operator place orders on the same market, in
the same YES-equivalent direction, within ``max_lag_seconds`` of each other,
repeatedly and on several days. Counterparty fills are excluded:

* two wallets in the **same transaction** are taker/maker counterparties or
  makers filled by one sweep, so such co-occurrences never count;
* seconds with more than ``max_crowd_tx`` distinct transactions on one
  market/direction are news bursts and are skipped.

A pair links when ``co_moments >= min_co_moments``, ``co_days >= min_co_days``
and ``jaccard = co / (moments_a + moments_b - co) >= min_jaccard``. Jaccard is
symmetric: a high-volume bot that happens to trade beside many small wallets
has low Jaccard with each of them (the asymmetric overlap score chained 229
unrelated wallets into one component in the June data).
Linked components become entities. This is a heuristic from served trades
only; funding-source (on-chain transfer) evidence would be stronger.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OwnerConfig:
    max_lag_seconds: int = 1
    max_crowd_tx: int = 10
    min_co_moments: int = 5
    min_co_days: int = 3
    min_jaccard: float = 0.2
    max_component_size: int = 25   # larger components are reported, not merged


def _moments(trades: pd.DataFrame) -> pd.DataFrame:
    keys = ["wallet_address", "market_id", "direction", "second", "transaction_hash"]
    return trades[keys].drop_duplicates()


def co_trading_pairs(trades: pd.DataFrame, config: OwnerConfig = OwnerConfig()) -> pd.DataFrame:
    """Per wallet pair: co-timed moments, distinct days and overlap."""
    moments = _moments(trades)
    wallets, uniq = pd.factorize(moments["wallet_address"])
    txs = pd.factorize(moments["transaction_hash"])[0]
    m = pd.DataFrame({"w": wallets, "mk": pd.factorize(moments["market_id"])[0],
                      "d": moments["direction"].to_numpy(), "s": moments["second"].to_numpy(), "tx": txs})
    crowd = m.groupby(["mk", "d", "s"])["tx"].transform("nunique")
    m = m.loc[crowd <= config.max_crowd_tx]
    hits = []
    for lag in range(config.max_lag_seconds + 1):
        later = m.assign(s=m["s"] - lag)     # b traded `lag` seconds after a
        j = m.merge(later, on=["mk", "d", "s"], suffixes=("a", "b"))
        j = j.loc[(j["wa"] != j["wb"]) & (j["txa"] != j["txb"])]
        a_first = j["wa"] < j["wb"]
        hits.append(pd.DataFrame({
            "lo": np.where(a_first, j["wa"], j["wb"]), "hi": np.where(a_first, j["wb"], j["wa"]),
            "mk": j["mk"].to_numpy(), "d": j["d"].to_numpy(),
            "s_lo": np.where(a_first, j["s"], j["s"] + lag), "s_hi": np.where(a_first, j["s"] + lag, j["s"])}))
    pairs = pd.concat(hits, ignore_index=True).drop_duplicates()
    pairs["day"] = pairs["s_lo"] // 86400
    pairs["m_lo"] = list(zip(pairs["mk"], pairs["d"], pairs["s_lo"]))
    pairs["m_hi"] = list(zip(pairs["mk"], pairs["d"], pairs["s_hi"]))
    out = pairs.groupby(["lo", "hi"], as_index=False).agg(
        matched_lo=("m_lo", "nunique"), matched_hi=("m_hi", "nunique"), co_days=("day", "nunique"))
    # Distinct moments matched on the sparser side: each moment counts once.
    out["co_moments"] = np.minimum(out["matched_lo"], out["matched_hi"])
    per_wallet = m.drop_duplicates(["w", "mk", "d", "s"]).groupby("w").size()
    n_lo, n_hi = out["lo"].map(per_wallet), out["hi"].map(per_wallet)
    out["overlap"] = out["co_moments"] / np.minimum(n_lo, n_hi)          # diagnostic only
    out["jaccard"] = out["co_moments"] / (n_lo + n_hi - out["co_moments"])
    out = out.drop(columns=["matched_lo", "matched_hi"])
    out["wallet_a"], out["wallet_b"] = uniq[out["lo"]], uniq[out["hi"]]
    return out.drop(columns=["lo", "hi"])


def linked_pairs(pairs: pd.DataFrame, config: OwnerConfig = OwnerConfig()) -> pd.DataFrame:
    return pairs.loc[pairs["co_moments"].ge(config.min_co_moments) & pairs["co_days"].ge(config.min_co_days)
                     & pairs["jaccard"].ge(config.min_jaccard)]


def assign_entities(wallets, links: pd.DataFrame, config: OwnerConfig = OwnerConfig()) -> pd.DataFrame:
    """Union-find over links. Oversized components stay as separate wallets."""
    parent = {w: w for w in wallets}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in zip(links["wallet_a"], links["wallet_b"]):
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    table = pd.DataFrame({"wallet_address": list(parent)})
    table["root"] = table["wallet_address"].map(find)
    table["entity_size"] = table.groupby("root")["wallet_address"].transform("size")
    oversized = table["entity_size"] > config.max_component_size
    table["entity_id"] = np.where(table["entity_size"].gt(1) & ~oversized,
                                  "E_" + table["root"].str[2:12], table["wallet_address"])
    table["owner_status"] = np.select([oversized, table["entity_size"].gt(1)],
                                      ["oversized_component_not_merged", "merged"], "single")
    table.loc[oversized, "entity_size"] = 1
    return table.drop(columns="root")
