#!/usr/bin/env python3
"""Run sniper grouping -> hard rules -> behaviour clustering for one meeting.

Uses only participant trades strictly before ``--cutoff`` from the committed
market exports, so the resulting memberships can drive post-cutoff signals.

    python scripts/polymarket/wallet_pipeline/run.py
    python scripts/polymarket/wallet_pipeline/run.py --min-jaccard 0.3 --output tmp/wallet_pipeline_test
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

from wallet_pipeline.behaviour import DESCRIPTIONS, FEATURES, ClusterConfig, entity_features, fit, prepare_matrix, profiles  # noqa: E402
from wallet_pipeline.owners import OwnerConfig, assign_entities, co_trading_pairs, linked_pairs  # noqa: E402
from wallet_pipeline.rules import RuleConfig, apply_rules, rule_counts  # noqa: E402
from wallet_pipeline.trades import load_market_exports  # noqa: E402

DEFAULT_MARKETS = ["906972", "906973", "906974", "906975", "906976"]
GZIP = {"method": "gzip", "mtime": 0}  # byte-reproducible outputs
SENSITIVITY = [(3, 2, 0.1), (5, 3, 0.1), (5, 3, 0.2), (5, 3, 0.3), (10, 3, 0.2), (5, 5, 0.2)]


def owner_sensitivity(pairs, wallets):
    rows = []
    for co, days, jac in SENSITIVITY:
        cfg = OwnerConfig(min_co_moments=co, min_co_days=days, min_jaccard=jac, max_component_size=10**9)
        table = assign_entities(wallets, linked_pairs(pairs, cfg), cfg)
        merged = table.loc[table["entity_size"] > 1]
        sizes = merged.groupby("entity_id").size()
        rows.append(dict(min_co_moments=co, min_co_days=days, min_jaccard=jac,
                         links=len(linked_pairs(pairs, cfg)), merged_wallets=len(merged),
                         entities=len(sizes), largest_entity=int(sizes.max()) if len(sizes) else 0))
    return pd.DataFrame(rows)


def run(args):
    out = args.output
    (out).mkdir(parents=True, exist_ok=True)
    owner_cfg = OwnerConfig(min_co_moments=args.min_co_moments, min_co_days=args.min_co_days,
                            min_jaccard=args.min_jaccard)
    rule_cfg = RuleConfig()
    cluster_cfg = ClusterConfig()
    trades = load_market_exports(ROOT, args.markets, args.cutoff)
    wallets = trades["wallet_address"].unique()

    # Stage 1: same-owner entities.
    pairs = co_trading_pairs(trades, owner_cfg)
    links = linked_pairs(pairs, owner_cfg)
    entities = assign_entities(wallets, links, owner_cfg)
    sensitivity = owner_sensitivity(pairs, wallets)

    # Stage 2: features per entity and hard rules.
    features = apply_rules(entity_features(trades, entities, args.cutoff), rule_cfg)
    eligible = features.loc[features["eligible"]].reset_index(drop=True)

    # Stage 3: behaviour clustering of eligible entities.
    frame, retained, removed = prepare_matrix(eligible)
    pipeline, labels, distances, diagnostics, summary = fit(frame, retained, cluster_cfg)
    snapshot = args.output.name
    model_version = f"{snapshot}_k{summary['selected_k']}_s{summary['selected_seed']}"
    assigned = pd.DataFrame({"entity_id": eligible["entity_id"], "cluster_id": [f"C{x}" for x in labels],
                             "centroid_distance": distances})
    memberships = entities.merge(features[["entity_id", "eligible", "rule_failures"]], on="entity_id", how="left")
    memberships = memberships.merge(assigned, on="entity_id", how="left")
    memberships["assignment_status"] = np.where(memberships["cluster_id"].notna(), "assigned", "failed_rules")
    memberships["model_version"] = model_version
    memberships["valid_from_utc"] = pd.Timestamp(args.cutoff).isoformat()
    cluster_profiles = profiles(frame, labels, retained)
    cluster_profiles.insert(0, "model_version", model_version)

    # Outputs.
    config = dict(snapshot_id=snapshot, cutoff_utc=pd.Timestamp(args.cutoff).isoformat(), markets=list(args.markets),
                  owner=asdict(owner_cfg), rules=asdict(rule_cfg),
                  clustering={k: list(v) if isinstance(v, tuple) else v for k, v in asdict(cluster_cfg).items()},
                  features=FEATURES)
    (out / "config.json").write_text(json.dumps(config, indent=2))
    links.round(6).to_csv(out / "owner_links.csv", index=False)
    sensitivity.to_csv(out / "owner_sensitivity.csv", index=False)
    memberships.to_csv(out / "memberships.csv.gz", index=False, float_format="%.8g", compression=GZIP)
    features.drop(columns=["first_trade_utc"]).to_csv(out / "entity_features.csv.gz", index=False, float_format="%.8g", compression=GZIP)
    cluster_profiles.to_csv(out / "cluster_profiles.csv", index=False, float_format="%.6g")
    diagnostics.to_csv(out / "selection_diagnostics.csv", index=False, float_format="%.6g")
    joblib.dump(pipeline, out / "pipeline.joblib")
    owner_counts = entities["owner_status"].value_counts().to_dict()
    merged_sizes = entities.loc[entities["owner_status"].eq("merged")].groupby("entity_id").size()
    report = dict(
        snapshot_id=snapshot, model_version=model_version, trades=len(trades), wallets=len(wallets),
        owner=dict(candidate_pairs=len(pairs), links=len(links), statuses=owner_counts,
                   merged_entities=len(merged_sizes), largest_entity=int(merged_sizes.max()) if len(merged_sizes) else 0),
        rules=rule_counts(features), clustering=summary | dict(retained_features=retained, removed_features=removed,
                                                               imputed_taker_fraction=int(eligible["taker_fraction_imputed"].sum()),
                                                               cluster_sizes=pd.Series(labels).value_counts().sort_index().rename(lambda x: f"C{x}").to_dict()),
        source_hashes={m: hashlib.sha256((ROOT / f"datasets/polymarket/market_{m}/wallet_trades.csv.gz").read_bytes()).hexdigest()
                       for m in args.markets})
    (out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    write_readme(out, report, sensitivity, cluster_profiles)
    print(json.dumps({k: report[k] for k in ("model_version", "owner", "rules", "clustering")}, indent=2, default=str))
    return report


def write_readme(out, report, sensitivity, cluster_profiles):
    c = report["clustering"]
    explain = cluster_profiles.drop_duplicates("cluster_id")[["cluster_id", "entity_count", "explanation"]]
    medians = cluster_profiles.pivot(index="feature", columns="cluster_id", values="median")
    text = f"""# Wallet pipeline snapshot `{report['snapshot_id']}`

Generated by `scripts/polymarket/wallet_pipeline/run.py` from the five June 2026
market exports, using only trades **strictly before {out.joinpath('config.json').exists() and json.loads(out.joinpath('config.json').read_text())['cutoff_utc']}**.

| Stage | Result |
|---|---|
| Input | {report['trades']:,} participant records, {report['wallets']:,} wallets |
| 1. Same-owner (sniper) grouping | {report['owner']['links']} links -> {report['owner']['merged_entities']} multi-wallet entities ({report['owner']['statuses'].get('merged', 0)} wallets, largest {report['owner']['largest_entity']}) |
| 2. Hard rules | {report['rules']['eligible']:,} of {report['rules']['entities']:,} entities eligible |
| 3. Behaviour clustering | K = {c['selected_k']}, mean silhouette {c['mean_silhouette']:.3f}, seed stability ARI {c['seed_stability_ari']:.3f}, status **{c['status']}** |

## Clusters

{explain.to_markdown(index=False)}

Median feature values per cluster:

{medians.round(3).to_markdown()}

Feature definitions: {'; '.join(f'`{k}`: {v}' for k, v in DESCRIPTIONS.items())}.

## Stage notes

**Same-owner grouping.** Wallets link when they trade the same market in the
same YES-equivalent direction within 1 second, in *different* transactions
(same-transaction wallets are counterparties or co-filled makers), on at least
5 such moments over at least 3 days, with Jaccard similarity >= 0.2. Seconds
with more than 10 transactions on a market/direction are skipped as crowds.
This is a heuristic from served trades; funding-source evidence would be
stronger. Sensitivity of the grouping to its thresholds:

{sensitivity.to_markdown(index=False)}

**Hard rules** (entity counts failing each rule, non-exclusive):
{json.dumps({k: v for k, v in report['rules'].items() if k not in ('entities', 'eligible')})}

**Clustering.** log1p on skewed counts/sizes/gaps; RobustScaler on the 5-95%
range with clipping at +/-3 (the pilot's 25-75% scaling let near-binary
fractions dominate); KMeans K=2-8 x 5 seeds; size-valid solutions ranked by
silhouette, then seed stability within 0.02, then smaller K. Removed constant
features: {c['removed_features']}. `taker_fraction` was imputed with the cohort
median for {c['imputed_taker_fraction']} entities with fewer than 5 role-identified records.

## Files

| File | Content |
|---|---|
| `memberships.csv.gz` | Every wallet: `entity_id`, owner status, rule failures, `cluster_id`, centroid distance. Feed to `models/cluster_regression.py --memberships` |
| `entity_features.csv.gz` | Every entity's features and rule outcome |
| `owner_links.csv`, `owner_sensitivity.csv` | Linked wallet pairs and threshold sensitivity |
| `cluster_profiles.csv`, `selection_diagnostics.csv` | Cluster medians/quartiles and every K/seed candidate |
| `pipeline.joblib`, `config.json`, `report.json` | Fitted transform + KMeans, parameters, counts and source hashes |

## Limits

Features come from the same meeting's pre-cutoff trading, so clusters describe
behaviour in this meeting rather than a multi-meeting history. Wallets were not
selected using post-cutoff information. Cluster quality (silhouette ~0.3) says
the groups are moderately separated, not that any group is skilled.
"""
    (out / "README.md").write_text(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cutoff", default="2026-05-31T00:00:00+00:00")
    parser.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/polymarket/wallet_pipeline/fed_20260531_v2")
    parser.add_argument("--min-co-moments", type=int, default=5)
    parser.add_argument("--min-co-days", type=int, default=3)
    parser.add_argument("--min-jaccard", type=float, default=0.2)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    main()
