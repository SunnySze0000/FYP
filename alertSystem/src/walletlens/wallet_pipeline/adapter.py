"""Canonical WalletLens trades -> the column layout of the team's wallet pipeline, and the full run."""

from __future__ import annotations

import pandas as pd

from walletlens import logs

log = logs.get("wallet_pipeline")


def to_pipeline_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Columns: wallet_address, market_id, direction, second, transaction_hash, timestamp_utc, shares, price,
    notional_usd, side, token_outcome, same_fingerprint_count, taker_role."""
    from walletlens.wallet_pipeline.trades import infer_taker  # the team's taker inference
    data = pd.DataFrame({
        "wallet_address": trades["wallet"].astype(str).to_numpy(),
        "market_id": trades["market_id"].astype(str).to_numpy(),
        "direction": trades["yes_dir"].astype(int).to_numpy(),
        "second": trades["ts"].astype("int64").to_numpy(),
        "transaction_hash": trades["tx"].astype("int64").to_numpy(),
        "timestamp_utc": pd.to_datetime(trades["ts"].to_numpy(), unit="s", utc=True),
        "shares": trades["shares"].to_numpy(), "price": trades["price"].to_numpy(),
        "notional_usd": trades["notional"].to_numpy(), "side": trades["side"].astype(str).to_numpy(),
        "token_outcome": trades["token"].astype(str).to_numpy(), "same_fingerprint_count": 1,
    })
    data["taker_role"] = infer_taker(data)
    return data


def run_pipeline(trades: pd.DataFrame, cutoff_ts: int) -> tuple[pd.DataFrame, dict]:
    """Stages 1-3 on trades before ``cutoff_ts``; returns one row per wallet:
    entity_id, entity_size, eligible, cluster_id (frozen clusters; 'unclustered' if not eligible or unseen)."""
    from walletlens.wallet_pipeline import behaviour, owners, rules
    fit_trades = trades[trades["ts"] < cutoff_ts]
    data = to_pipeline_trades(fit_trades)
    pairs = owners.co_trading_pairs(data)
    links = owners.linked_pairs(pairs)
    entities = owners.assign_entities(sorted(data["wallet_address"].unique()), links)
    features = behaviour.entity_features(data, entities, pd.Timestamp(cutoff_ts, unit="s", tz="UTC"))
    filtered = rules.apply_rules(features)
    eligible = filtered[filtered["eligible"]]
    summary = {"wallets": int(entities.shape[0]), "linked_pairs": int(len(links)),
               "merged_entities": int(entities.loc[entities["owner_status"] == "merged", "entity_id"].nunique()),
               "rule_counts": rules.rule_counts(filtered)}
    clusters = pd.DataFrame(columns=["entity_id", "cluster_id"])
    if len(eligible) >= 50:
        frozen, frame, labels, _ = behaviour.FrozenClustering.fit(eligible.reset_index(drop=True), "events-wallets")
        clusters = pd.DataFrame({"entity_id": frame["entity_id"].to_numpy(), "cluster_id": [f"C{x}" for x in labels]})
        profiles = behaviour.profiles(frame, labels, frozen.retained)
        summary["clustering"] = frozen.summary
        summary["cluster_explanations"] = profiles.drop_duplicates("cluster_id").set_index("cluster_id")["explanation"].to_dict()
    table = entities.merge(filtered[["entity_id", "eligible"]], on="entity_id", how="left") \
        .merge(clusters, on="entity_id", how="left")
    table["eligible"] = table["eligible"].fillna(False).astype(bool)
    table["cluster_id"] = table["cluster_id"].fillna("unclustered")
    log.info("wallet pipeline: %s", {k: v for k, v in summary.items() if k != "cluster_explanations"})
    return table.rename(columns={"wallet_address": "wallet"}), summary
