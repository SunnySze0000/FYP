"""Cluster-implied outcome probabilities from wallet trading flow.

A KMeans centroid is a point in behaviour-feature space; it does not trade.
"The centroid's event probability" is therefore defined from the trades of
the wallets assigned to it. This module is deliberately agnostic about how
those assignments were made (behaviour clustering, sniper/same-owner
grouping, hard-rule filters, a skill filter, ...). It only needs a membership
table:

    wallet_address  cluster_id  [entity_id]  [weight]

* ``entity_id`` (optional): wallets believed to share one owner, e.g. from
  sniper clustering. Flow is netted per entity first, so one owner with many
  addresses counts once. Defaults to the wallet itself.
* ``weight`` (optional): per-entity weight in the cluster average, e.g. a
  past-only skill score or centroid closeness. Defaults to 1.

Method, for as-of time ``t``, cluster ``c`` and outcome market ``m``:

1. Use member trades in ``[t - window, t)`` that are also before the market's
   decision cutoff.
2. Per entity: ``D = BUY_YES - SELL_YES + SELL_NO - BUY_NO`` and gross shares
   ``G``; imbalance ``s_e = D / G`` in [-1, 1].
3. Cluster tilt ``s = weighted mean of s_e`` over active entities.
4. Shrink by activity: ``lambda = n / (n + k)`` with ``n`` active entities.
5. Shift the market probability ``p`` in log-odds space:
   ``logit(p_c) = logit(p) + lambda * beta * s``. With ``beta = 2`` a cluster
   that only buys YES multiplies the odds by up to e^2 (about 7.4x). A log-odds
   shift keeps cheap "lottery ticket" YES buying on a 1% outcome from implying
   a large probability. An inactive cluster returns exactly the market
   probability, never NaN. Choose ``beta`` and ``k`` on training events only.

Probabilities across a meeting's outcomes are renormalized downstream
(``models/distribution_features.py``). Flow is still not a holding, belief
or PnL: this is a transparent, monotone mapping, not a calibrated estimate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SIGN = {("buy", "yes"): 1.0, ("sell", "yes"): -1.0, ("buy", "no"): -1.0, ("sell", "no"): 1.0}


@dataclass(frozen=True)
class ImpliedProbabilityConfig:
    window: pd.Timedelta = pd.Timedelta(days=7)
    shrinkage_k: float = 3.0
    beta: float = 2.0               # log-odds shift for a fully one-sided cluster
    min_gross_shares: float = 0.0   # ignore entities with negligible flow


def prepare_memberships(memberships: pd.DataFrame) -> pd.DataFrame:
    """Validate and complete a membership table; unassigned rows are dropped."""
    required = {"wallet_address", "cluster_id"}
    missing = required - set(memberships.columns)
    if missing:
        raise ValueError(f"Membership table missing {sorted(missing)}")
    table = memberships.copy()
    table = table.loc[table["cluster_id"].notna() & table["cluster_id"].astype(str).ne("")]
    table["wallet_address"] = table["wallet_address"].str.lower()
    table["cluster_id"] = table["cluster_id"].astype(str)
    if table["wallet_address"].duplicated().any():
        raise ValueError("A wallet is assigned to more than one cluster")
    if "entity_id" not in table:
        table["entity_id"] = table["wallet_address"]
    table["entity_id"] = table["entity_id"].fillna(table["wallet_address"]).astype(str)
    if table.groupby("entity_id")["cluster_id"].nunique().gt(1).any():
        raise ValueError("Wallets of one entity must share a cluster")
    if "weight" not in table:
        table["weight"] = 1.0
    table["weight"] = pd.to_numeric(table["weight"], errors="raise")
    if (table["weight"] < 0).any() or not np.isfinite(table["weight"]).all():
        raise ValueError("Weights must be finite and non-negative")
    return table[["wallet_address", "cluster_id", "entity_id", "weight"]]


def centroid_weights(memberships: pd.DataFrame, distance: str = "centroid_distance") -> pd.Series:
    """Optional weight: closer to the centroid counts more, 1 / (1 + d)."""
    return 1.0 / (1.0 + pd.to_numeric(memberships[distance], errors="coerce").fillna(np.inf))


def signed_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize trades and add YES-equivalent signed shares."""
    need = {"wallet_address", "market_id", "timestamp_utc", "side", "token_outcome", "shares"}
    missing = need - set(trades.columns)
    if missing:
        raise ValueError(f"Trades missing {sorted(missing)}")
    data = trades.copy()
    data["wallet_address"] = data["wallet_address"].str.lower()
    data["market_id"] = data["market_id"].astype(str)
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    data["shares"] = pd.to_numeric(data["shares"], errors="raise")
    if (data["shares"] <= 0).any():
        raise ValueError("Non-positive trade size")
    key = list(zip(data["side"].str.lower(), data["token_outcome"].str.lower()))
    sign = pd.Series([SIGN.get(k, np.nan) for k in key], index=data.index)
    if sign.isna().any():
        raise ValueError("Unsupported side/token_outcome")
    data["signed_shares"] = data["shares"] * sign
    return data


def _window_tilt(trades: pd.DataFrame, members: pd.DataFrame, config: ImpliedProbabilityConfig) -> pd.DataFrame:
    """Per (cluster, market): active entities and weighted imbalance."""
    rows = trades.merge(members, on="wallet_address", how="inner")
    if rows.empty:
        return pd.DataFrame(columns=["cluster_id", "market_id", "active_entities", "gross_shares", "tilt"])
    entity = rows.groupby(["cluster_id", "market_id", "entity_id"], as_index=False).agg(
        signed=("signed_shares", "sum"), gross=("shares", "sum"), weight=("weight", "first"))
    entity = entity.loc[entity["gross"] > config.min_gross_shares]
    entity["imbalance"] = entity["signed"] / entity["gross"]
    entity["_w_imb"] = entity["weight"] * entity["imbalance"]
    out = entity.groupby(["cluster_id", "market_id"], as_index=False).agg(
        active_entities=("entity_id", "size"), gross_shares=("gross", "sum"),
        _w=("weight", "sum"), _wi=("_w_imb", "sum"))
    out["tilt"] = np.where(out["_w"] > 0, out["_wi"] / out["_w"].where(out["_w"] > 0), 0.0)
    return out.drop(columns=["_w", "_wi"])


def tilt_probability(p, tilt, active, k: float, beta: float = 2.0):
    """Steps 4-5 of the module docstring; vectorized, stays inside (0, 1)."""
    raw = np.asarray(p, dtype=float)
    p = np.clip(raw, 1e-4, 1 - 1e-4)
    tilt = np.clip(np.asarray(tilt, dtype=float), -1.0, 1.0)
    shift = shrink_weight(active, k) * beta * tilt
    shifted = 1.0 / (1.0 + np.exp(-(np.log(p / (1.0 - p)) + shift)))
    return np.where(shift == 0, raw, shifted)


def shrink_weight(active, k: float):
    """lambda = n / (n + k); with k = 0, any activity gives full weight."""
    active = np.asarray(active, dtype=float)
    return active / (active + k) if k > 0 else (active > 0).astype(float)


def implied_probabilities(trades: pd.DataFrame, memberships: pd.DataFrame,
                          market_probabilities: pd.DataFrame,
                          config: ImpliedProbabilityConfig = ImpliedProbabilityConfig(),
                          decision_cutoffs: dict[str, str] | None = None) -> pd.DataFrame:
    """Long panel: one row per (asof_utc, market_id, cluster_id).

    ``market_probabilities`` needs ``asof_utc``, ``market_id``, ``outcome``,
    ``market_probability`` (and optionally ``event_id``). Each row is an as-of
    time; only trades strictly before it are used. With ``decision_cutoffs``
    (market_id -> UTC time), as-of times after the cutoff are dropped and later
    trades are never used.
    """
    members = prepare_memberships(memberships)
    data = signed_trades(trades)
    data = data.loc[data["wallet_address"].isin(members["wallet_address"])]
    probs = market_probabilities.copy()
    probs["market_id"] = probs["market_id"].astype(str)
    probs["asof_utc"] = pd.to_datetime(probs["asof_utc"], utc=True)
    if decision_cutoffs:
        cut = probs["market_id"].map({str(k): pd.Timestamp(v) for k, v in decision_cutoffs.items()})
        cut = pd.to_datetime(cut, utc=True)
        probs = probs.loc[cut.isna() | probs["asof_utc"].le(cut)]
        trade_cut = pd.to_datetime(data["market_id"].map({str(k): pd.Timestamp(v) for k, v in decision_cutoffs.items()}), utc=True)
        data = data.loc[trade_cut.isna() | data["timestamp_utc"].lt(trade_cut)]
    clusters = sorted(members["cluster_id"].unique())
    frames = []
    for asof in sorted(probs["asof_utc"].unique()):
        window = data.loc[data["timestamp_utc"].ge(asof - config.window) & data["timestamp_utc"].lt(asof)]
        tilt = _window_tilt(window, members, config)
        base = probs.loc[probs["asof_utc"].eq(asof)]
        grid = base.merge(pd.DataFrame({"cluster_id": clusters}), how="cross")
        frames.append(grid.merge(tilt, on=["cluster_id", "market_id"], how="left"))
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel["active_entities"] = panel["active_entities"].fillna(0).astype(int)
    panel["gross_shares"] = panel["gross_shares"].fillna(0.0)
    panel["tilt"] = panel["tilt"].fillna(0.0)
    panel["cluster_probability"] = tilt_probability(
        panel["market_probability"], panel["tilt"], panel["active_entities"], config.shrinkage_k, config.beta)
    panel["shrink_weight"] = shrink_weight(panel["active_entities"], config.shrinkage_k)
    return panel.sort_values(["asof_utc", "market_id", "cluster_id"]).reset_index(drop=True)
