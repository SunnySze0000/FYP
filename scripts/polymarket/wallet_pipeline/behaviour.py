"""Stage 3 inputs and model: entity behaviour features and KMeans selection.

Features use only trades before the cutoff and are computed per *entity*
(stage 1), so a same-owner group is one row. Model selection follows the
frozen pilot: log1p on skewed features, RobustScaler, KMeans over K with five
seeds; prefer size-valid solutions by mean silhouette, and within 0.02 of the
best prefer seed stability (median pairwise ARI), then smaller K.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import ceil

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, RobustScaler

FEATURES = [
    "active_days", "trades_per_active_day", "median_trade_notional", "markets_traded",
    "top_market_notional_fraction", "two_sided_token_fraction", "busiest_day_trade_fraction",
    "median_gap_hours", "taker_fraction", "net_direction_consistency", "mean_token_price",
    "late_activity_fraction", "sell_fraction",
]
LOG_FEATURES = {"active_days", "trades_per_active_day", "median_trade_notional", "median_gap_hours"}
DESCRIPTIONS = {
    "active_days": "distinct UTC days with a trade",
    "trades_per_active_day": "participant records per active day",
    "median_trade_notional": "median shares x price per record (USD)",
    "markets_traded": "distinct outcome markets of the meeting traded",
    "top_market_notional_fraction": "largest single-market share of notional",
    "two_sided_token_fraction": "share of traded markets where both YES and NO tokens were traded",
    "busiest_day_trade_fraction": "share of records on the busiest day",
    "median_gap_hours": "median hours between consecutive records",
    "taker_fraction": "taker share of records whose role is identifiable (cohort median if < 5)",
    "net_direction_consistency": "|net YES-equivalent shares| / gross shares, per market, notional-weighted",
    "mean_token_price": "notional-weighted price of the tokens traded (low = long shots)",
    "late_activity_fraction": "share of records in the final 14 days before the cutoff",
    "sell_fraction": "share of records that are SELLs",
}


def entity_features(trades: pd.DataFrame, entities: pd.DataFrame, cutoff) -> pd.DataFrame:
    cutoff = pd.Timestamp(cutoff)
    data = trades.merge(entities[["wallet_address", "entity_id"]], on="wallet_address", how="left")
    data["entity_id"] = data["entity_id"].fillna(data["wallet_address"])
    data["day"] = data["timestamp_utc"].dt.floor("D")
    data["signed"] = data["direction"] * data["shares"]
    data["is_sell"] = data["side"].str.upper().eq("SELL")
    data["late"] = data["timestamp_utc"].ge(cutoff - pd.Timedelta(days=14))
    g = data.groupby("entity_id")
    out = pd.DataFrame({
        "wallets": g["wallet_address"].nunique(),
        "trades": g.size(),
        "total_notional_usd": g["notional_usd"].sum(),
        "active_days": g["day"].nunique(),
        "median_trade_notional": g["notional_usd"].median(),
        "markets_traded": g["market_id"].nunique(),
        "sell_fraction": g["is_sell"].mean(),
        "late_activity_fraction": g["late"].mean(),
        "duplicate_fraction": g["same_fingerprint_count"].apply(lambda s: pd.to_numeric(s).gt(1).mean()),
        "first_trade_utc": g["timestamp_utc"].min(),
    })
    out["trades_per_active_day"] = out["trades"] / out["active_days"]
    market = data.groupby(["entity_id", "market_id"]).agg(
        notional=("notional_usd", "sum"), signed=("signed", "sum"), gross=("shares", "sum"),
        tokens=("token_outcome", "nunique"))
    out["top_market_notional_fraction"] = (market["notional"].groupby(level=0).max()
                                           / market["notional"].groupby(level=0).sum().replace(0, np.nan))
    out["two_sided_token_fraction"] = market["tokens"].gt(1).groupby(level=0).mean()
    consistency = (market["signed"].abs() / market["gross"]) * market["notional"]
    out["net_direction_consistency"] = consistency.groupby(level=0).sum() / market["notional"].groupby(level=0).sum().replace(0, np.nan)
    out["busiest_day_trade_fraction"] = data.groupby(["entity_id", "day"]).size().groupby(level=0).max() / out["trades"]
    gaps = data.sort_values("timestamp_utc").groupby("entity_id")["timestamp_utc"].diff().dt.total_seconds() / 3600
    out["median_gap_hours"] = gaps.groupby(data["entity_id"]).median()
    # Price of the token traded, notional-weighted over all records (defined for
    # sell-only entities too). Low values = trading long-shot tokens.
    weighted = (data["price"] * data["notional_usd"]).groupby(data["entity_id"]).sum()
    out["mean_token_price"] = weighted / g["notional_usd"].sum().replace(0, np.nan)
    roles = data.dropna(subset=["taker_role"]).groupby("entity_id")["taker_role"].agg(["mean", "size"])
    out["taker_fraction"] = roles["mean"].where(roles["size"] >= 5)
    out["taker_fraction_imputed"] = out["taker_fraction"].isna()
    return out.reset_index()


@dataclass(frozen=True)
class ClusterConfig:
    k_values: tuple = (2, 3, 4, 5, 6, 7, 8)
    seeds: tuple = (42, 43, 44, 45, 46)
    n_init: int = 20
    min_cluster_fraction: float = 0.05
    min_cluster_size: int = 5
    silhouette_tolerance: float = 0.02
    silhouette_sample: int = 5000
    # The pilot's default 25-75% RobustScaler inflates near-binary fractions
    # whose IQR is ~0 (up to 17x here), so one feature decides the clusters.
    # Scale on the 5-95% range and clip at +/-clip instead.
    quantile_range: tuple = (5.0, 95.0)
    clip: float = 3.0


def prepare_matrix(eligible: pd.DataFrame, features=FEATURES) -> tuple[pd.DataFrame, list, list]:
    """Impute only taker_fraction (role unknown is common); drop constant features."""
    frame = eligible.copy()
    if "taker_fraction" in features:
        frame["taker_fraction"] = frame["taker_fraction"].fillna(frame["taker_fraction"].median())
    retained, removed = [], []
    for name in features:
        column = frame[name]
        iqr = column.quantile(.75) - column.quantile(.25)
        if not np.isfinite(column).all():
            raise ValueError(f"Non-finite clustering input: {name}")
        (retained if iqr > 0 and column.nunique() > 1 else removed).append(name)
    return frame, retained, removed


def fit(frame: pd.DataFrame, retained: list, config: ClusterConfig = ClusterConfig()):
    selector = ColumnTransformer([(f"f{i}", FunctionTransformer(np.log1p) if name in LOG_FEATURES else "passthrough", [name])
                                  for i, name in enumerate(retained)], remainder="drop", verbose_feature_names_out=False)
    scaler = Pipeline([("robust", RobustScaler(quantile_range=config.quantile_range)),
                       ("clip", FunctionTransformer(np.clip, kw_args={"a_min": -config.clip, "a_max": config.clip}))])
    x = scaler.fit_transform(selector.fit_transform(frame))
    minimum = max(config.min_cluster_size, ceil(config.min_cluster_fraction * len(frame)))
    rng = np.random.default_rng(0)
    sample = rng.choice(len(x), size=min(len(x), config.silhouette_sample), replace=False)
    diagnostics, candidates = [], []
    for k in config.k_values:
        if k >= len(frame):
            break
        runs = []
        for seed in config.seeds:
            model = KMeans(n_clusters=k, n_init=config.n_init, max_iter=300, random_state=seed).fit(x)
            labels = model.labels_
            if len(set(labels)) < 2:
                continue
            runs.append(dict(k=k, seed=seed, model=model, labels=labels,
                             silhouette=float(silhouette_score(x[sample], labels[sample])),
                             min_cluster_size=int(np.bincount(labels, minlength=k).min())))
        if not runs:
            continue
        stability = float(np.median([adjusted_rand_score(a["labels"], b["labels"]) for a, b in combinations(runs, 2)]))
        size_valid = all(r["min_cluster_size"] >= minimum for r in runs)
        for r in runs:
            diagnostics.append(dict(k=k, seed=r["seed"], silhouette=r["silhouette"], min_cluster_size=r["min_cluster_size"],
                                    size_valid=r["min_cluster_size"] >= minimum, median_pairwise_ari=stability))
        candidates.append(dict(k=k, runs=runs, stability=stability, size_valid=size_valid,
                               mean_silhouette=float(np.mean([r["silhouette"] for r in runs]))))
    if not candidates:
        raise ValueError("No clustering candidates")
    pool = [c for c in candidates if c["size_valid"]] or candidates
    best = max(c["mean_silhouette"] for c in pool)
    chosen = sorted([c for c in pool if c["mean_silhouette"] >= best - config.silhouette_tolerance],
                    key=lambda c: (-c["stability"], c["k"]))[0]
    winner = sorted(chosen["runs"], key=lambda r: (-r["silhouette"], r["seed"]))[0]
    pipeline = Pipeline([("select_and_log", selector), ("scale", scaler), ("cluster", winner["model"])])
    distances = winner["model"].transform(x)[np.arange(len(x)), winner["labels"]]
    summary = dict(selected_k=chosen["k"], selected_seed=winner["seed"], mean_silhouette=chosen["mean_silhouette"],
                   seed_stability_ari=chosen["stability"], size_valid=chosen["size_valid"], minimum_cluster_size=minimum,
                   status="provisional" if not chosen["size_valid"] else "fitted")
    return pipeline, winner["labels"], distances, pd.DataFrame(diagnostics), summary


def profiles(frame: pd.DataFrame, labels, retained: list) -> pd.DataFrame:
    """Median / quartiles per cluster and feature, with a plain-language contrast."""
    rows = []
    for cluster in sorted(set(labels)):
        part = frame.loc[labels == cluster]
        contrasts = []
        for name in retained:
            iqr = frame[name].quantile(.75) - frame[name].quantile(.25)
            effect = (part[name].median() - frame[name].median()) / iqr
            contrasts.append((name, effect))
            rows.append(dict(cluster_id=f"C{cluster}", entity_count=len(part), feature=name,
                             median=part[name].median(), q25=part[name].quantile(.25), q75=part[name].quantile(.75),
                             overall_median=frame[name].median(), standardized_median_shift=effect))
        top = sorted(contrasts, key=lambda c: -abs(c[1]))[:3]
        text = "; ".join(f"{'higher' if v > 0 else 'lower'} {n.replace('_', ' ')}" for n, v in top)
        for row in rows[-len(retained):]:
            row["explanation"] = text
    return pd.DataFrame(rows)
