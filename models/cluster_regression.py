"""N clusters x M distribution features -> SPY return / variance regression.

Pipeline (each stage is a function, so stages can be swapped independently):

1. ``load_inputs``        trades, cluster memberships, market probabilities,
                           decision cutoffs from a wallet-cluster snapshot.
2. ``apply_skill``         optional: filter or weight members by past-only skill.
3. ``implied_probabilities`` (scripts/polymarket/cluster_implied_probability.py)
                           each cluster's probability for each outcome market.
4. ``cluster_features``    M features per cluster distribution, pivoted to N x M.
5. ``build_dataset``       join to SPY history/targets and market event features.
6. ``evaluate``            event-level walk-forward (event_walk_forward.run)
                           with a ``history_plus_event_plus_cluster`` feature set.

Feature modes for step 4 (``--feature-mode``):

* ``summary`` (default): M = relative features of the cluster distribution
  versus the market (``distribution_features.RELATIVE_FEATURES`` subset). These
  carry what the cluster adds beyond the market, which the event features
  already describe.
* ``levels``: M = the same level features used for the market (expected move,
  move std, entropy, max probability, ...). Collinear with market features.
* ``per_outcome``: M = one probability gap per outcome (the literal N x outcomes).

Run from the repository root:

    python models/cluster_regression.py
    python models/cluster_regression.py --skill weight --beta 1.0
    python models/cluster_regression.py \
        --memberships datasets/polymarket/wallet_pipeline/fed_20260531_v2/memberships.csv.gz
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts" / "polymarket"))

from cluster_implied_probability import ImpliedProbabilityConfig, implied_probabilities  # noqa: E402
from distribution_features import LEVEL_FEATURES, RELATIVE_FEATURES, compare, summarize  # noqa: E402
from event_walk_forward import default_feature_sets, run as walk_forward  # noqa: E402
from forecast_models import (  # noqa: E402
    ALL_FEATURES, HORIZONS, add_market_features, build_model_data, load_data,
)
from outcomes import normalize_outcomes, outcome_move  # noqa: E402
from wallet_skill import filter_by_skill, meeting_alignment, skill_scores, skill_weights  # noqa: E402

DEFAULT_PILOT = ROOT / "datasets" / "polymarket" / "wallet_cluster_pilot" / "fed_20260531_v1"
DEFAULT_OUTPUT = ROOT / "models" / "cluster_regression"
SUMMARY_FEATURES = ["expected_move_gap", "move_std_gap", "tail_probability_gap", "kl_from_market"]
LEVEL_SUBSET = ["expected_move", "move_std", "entropy_normalized", "max_probability"]
MIN_EVENTS_FOR_WALK_FORWARD = 3


# ---------------------------------------------------------------------------
# 1-2. Inputs and optional skill
# ---------------------------------------------------------------------------

def load_inputs(pilot: Path, memberships_path: Path | None = None) -> dict:
    """Pilot snapshot supplies config, market map and history trades.

    Signal-period trades come from the full market exports, so memberships
    from any clustering (not only the pilot's 150 wallets) are covered.
    ``memberships_path`` overrides the pilot's cluster_membership.csv.
    """
    config = json.loads((pilot / "config.json").read_text())
    market_map = pd.read_csv(pilot / "market_map.csv", dtype=str).drop_duplicates("market_id")
    memberships = pd.read_csv(memberships_path or pilot / "cluster_membership.csv", dtype=str)
    trades = pd.read_csv(pilot / "trades.csv.gz", dtype=str)
    target = str(config["target_event_id"])
    target_markets = market_map.loc[market_map["event_id"].eq(target), "market_id"]
    target_trades = pd.concat([
        pd.read_csv(ROOT / "datasets" / "polymarket" / f"market_{mid}" / "wallet_trades.csv.gz", dtype=str)
        for mid in sorted(target_markets)], ignore_index=True)
    probability = pd.read_csv(ROOT / "datasets" / "forward_probabilities.csv")
    probability["market_id"] = probability["market_id"].astype(str)
    probability["event_id"] = probability["event_id"].astype(str)
    probability["outcome"] = normalize_outcomes(probability["outcome"])
    probability["asof_utc"] = pd.to_datetime(probability["date"], utc=True)
    return dict(config=config, market_map=market_map, memberships=memberships,
                trades=trades, target_trades=target_trades, probability=probability)


def outcome_table(market_map: pd.DataFrame, probability: pd.DataFrame) -> pd.DataFrame:
    """Per market: decision cutoff, last quote at/before it, realized outcome."""
    rows = []
    for market in market_map.itertuples():
        cutoff = pd.Timestamp(market.decision_cutoff_utc)
        quotes = probability.loc[probability["market_id"].eq(market.market_id)
                                 & probability["asof_utc"].le(cutoff)].sort_values("asof_utc")
        if quotes.empty:
            continue
        rows.append(dict(event_id=market.event_id, market_id=market.market_id,
                         decision_cutoff_utc=market.decision_cutoff_utc,
                         cutoff_probability=quotes["market_probability"].iloc[-1],
                         final_outcome=quotes["final_outcome"].iloc[-1]))
    return pd.DataFrame(rows)


def apply_skill(inputs: dict, mode: str) -> pd.DataFrame:
    """Return memberships, optionally skill-filtered or skill-weighted.

    Skill uses only meetings resolved before the cluster model's fit cutoff.
    """
    members = inputs["memberships"].loc[inputs["memberships"]["cluster_id"].notna()].copy()
    if mode == "off":
        return members
    history = inputs["trades"].loc[inputs["trades"]["event_id"].isin(inputs["config"]["history_event_ids"])]
    outcomes = outcome_table(inputs["market_map"], inputs["probability"])
    scores = skill_scores(meeting_alignment(history, outcomes), inputs["config"]["selection_cutoff_utc"])
    if mode == "filter":
        return filter_by_skill(members, scores)
    members["weight"] = skill_weights(members, scores)
    return members


# ---------------------------------------------------------------------------
# 3-4. Cluster probabilities and N x M features
# ---------------------------------------------------------------------------

def cluster_probabilities(inputs: dict, members: pd.DataFrame,
                          config: ImpliedProbabilityConfig) -> pd.DataFrame:
    target = str(inputs["config"]["target_event_id"])
    fit_cutoff = pd.Timestamp(inputs["config"]["selection_cutoff_utc"])
    markets = inputs["market_map"].loc[inputs["market_map"]["event_id"].eq(target)]
    probs = inputs["probability"].loc[inputs["probability"]["market_id"].isin(markets["market_id"])
                                      & inputs["probability"]["asof_utc"].ge(fit_cutoff)]
    trades = inputs["target_trades"]
    cutoffs = markets.set_index("market_id")["decision_cutoff_utc"].to_dict()
    panel = implied_probabilities(
        trades, members,
        probs[["asof_utc", "event_id", "market_id", "outcome", "market_probability"]],
        config, decision_cutoffs=cutoffs)
    panel["move"] = outcome_move(panel["outcome"])
    return panel


def cluster_features(panel: pd.DataFrame, mode: str = "summary") -> pd.DataFrame:
    """Wide frame: one row per (asof_utc, event_id); columns ``<cluster>__<feature>``."""
    keys = ["asof_utc", "event_id", "cluster_id"]
    if mode == "summary":
        long = compare(panel, keys, reference="market_probability",
                       probability="cluster_probability")[keys + SUMMARY_FEATURES]
    elif mode == "levels":
        long = summarize(panel, keys, probability="cluster_probability")[keys + LEVEL_SUBSET]
    elif mode == "per_outcome":
        data = panel.copy()
        total_c = data.groupby(keys)["cluster_probability"].transform("sum")
        total_m = data.groupby(keys)["market_probability"].transform("sum")
        data["gap"] = data["cluster_probability"] / total_c - data["market_probability"] / total_m
        data["feature"] = "p_gap_" + data["outcome"].str.replace(r"[^0-9a-z]+", "_", regex=True).str.strip("_")
        long = data.pivot_table(index=keys, columns="feature", values="gap").reset_index()
    else:
        raise ValueError(f"Unknown feature mode {mode!r}")
    activity = panel.groupby(keys, as_index=False)["active_entities"].sum()
    long = long.merge(activity.rename(columns={"active_entities": "active_entities"}), on=keys)
    wide = long.pivot(index=["asof_utc", "event_id"], columns="cluster_id")
    wide.columns = [f"{cluster}__{feature}" for feature, cluster in wide.columns]
    return wide.reset_index().sort_values("asof_utc")


# ---------------------------------------------------------------------------
# 5-6. Join to SPY and evaluate
# ---------------------------------------------------------------------------

def build_dataset(features: pd.DataFrame) -> pd.DataFrame:
    market, probability = load_data()
    data = build_model_data(market, probability)
    features = features.copy()
    features["date"] = features["asof_utc"].dt.tz_localize(None).dt.normalize()
    features = features.drop(columns=["asof_utc"]).rename(columns={"event_id": "cluster_event_id"})
    # Exact date match: a cluster row as-of 00:00 UTC on day d only uses trades
    # before d, and the model's target starts after day d's close.
    return data.merge(features, on="date", how="inner")


def evaluate(data: pd.DataFrame, cluster_columns: list[str]) -> tuple[pd.DataFrame, str]:
    model_columns = [c for c in cluster_columns if not c.endswith("__active_entities")]
    events = data["event_id"].nunique()
    if events < MIN_EVENTS_FOR_WALK_FORWARD:
        return pd.DataFrame(), (
            f"insufficient_events: {events} event(s) with cluster features; "
            f"walk-forward needs at least {MIN_EVENTS_FOR_WALK_FORWARD}")

    def sets(target_name):
        base = default_feature_sets(target_name)
        base["history_plus_event_plus_cluster"] = ALL_FEATURES + model_columns
        return base

    results = walk_forward(data, feature_sets=sets,
                           min_train_events=MIN_EVENTS_FOR_WALK_FORWARD - 1, min_train_rows=10)
    return results, "evaluated"


def correlations(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    targets = [f"target_{kind}_{h}d" for kind in ("return", "variance") for h in HORIZONS]
    rows = []
    for column in columns:
        for target in targets:
            pair = data[[column, target]].dropna()
            if len(pair) >= 3 and pair[column].nunique() > 1:
                rows.append(dict(feature=column, target=target, n=len(pair),
                                 spearman=pair[column].corr(pair[target], method="spearman")))
    return pd.DataFrame(rows)


def write_report(path: Path, args, panel, features, data, status, results, corr):
    cluster_columns = [c for c in features.columns if "__" in c]
    model_columns = [c for c in cluster_columns if not c.endswith("__active_entities")]
    clusters = sorted(panel["cluster_id"].unique())
    activity = panel.groupby("cluster_id")["active_entities"].apply(lambda s: (s > 0).mean())
    lines = [
        "# Cluster-implied probability regression", "",
        f"- Snapshot: `{args.pilot.name}`; memberships "
        f"`{args.memberships.as_posix() if args.memberships else 'pilot cluster_membership.csv'}`; "
        f"feature mode `{args.feature_mode}`; skill `{args.skill}`",
        f"- Implied-probability config: window {args.window_days} d, k = {args.shrinkage_k}, beta = {args.beta}",
        f"- Clusters N = {len(clusters)} ({', '.join(clusters)}); features per cluster M = "
        f"{len(model_columns) // max(len(clusters), 1)}; model inputs N x M = {len(model_columns)}",
        f"- Cluster panel: {panel['asof_utc'].nunique()} as-of days x {panel['market_id'].nunique()} markets",
        f"- Rows joined to SPY trading days: {len(data)} across {data['event_id'].nunique()} event(s)",
        f"- Share of cluster-market-days with any member activity: "
        + ", ".join(f"{c} {v:.0%}" for c, v in activity.items()),
        f"- Status: **{status}**", "",
    ]
    if results.empty:
        lines += [
            "No model was scored. With one meeting and roughly a dozen trading days,",
            f"{len(model_columns)} cluster inputs cannot be fitted and tested out of sample; any",
            "in-sample fit would be overfitting. The pipeline below is verified end to end",
            "so that a rolling-cutoff panel covering several meetings can be dropped in.", "",
        ]
    else:
        grouped = results.groupby(["target", "horizon", "feature_set", "model"], as_index=False).agg(
            folds=("test_event_id", "nunique"), test_rows=("test_rows", "sum"),
            mean_rmse=("rmse", "mean"), mean_r2=("r2", "mean"))
        lines += ["## Walk-forward results", "", grouped.round(6).to_markdown(index=False), ""]
    if not corr.empty:
        lines += ["## Exploratory Spearman correlations (descriptive only)", "",
                  f"Each uses n <= {int(corr['n'].max())} overlapping daily rows from one meeting.",
                  "", corr.round(4).to_markdown(index=False), ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--memberships", type=Path,
                        help="membership CSV (wallet_address, cluster_id[, entity_id, weight]); default: pilot")
    parser.add_argument("--feature-mode", choices=("summary", "levels", "per_outcome"), default="summary")
    parser.add_argument("--skill", choices=("off", "filter", "weight"), default="off")
    parser.add_argument("--window-days", type=float, default=7.0)
    parser.add_argument("--shrinkage-k", type=float, default=3.0)
    parser.add_argument("--beta", type=float, default=2.0)
    args = parser.parse_args(argv)

    inputs = load_inputs(args.pilot, args.memberships)
    members = apply_skill(inputs, args.skill)
    config = ImpliedProbabilityConfig(window=pd.Timedelta(days=args.window_days),
                                      shrinkage_k=args.shrinkage_k, beta=args.beta)
    panel = cluster_probabilities(inputs, members, config)
    features = cluster_features(panel, args.feature_mode)
    data = build_dataset(features)
    cluster_columns = [c for c in features.columns if "__" in c]
    results, status = evaluate(data, cluster_columns)
    corr = correlations(data, [c for c in cluster_columns if not c.endswith("__active_entities")])

    args.output.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.output / "cluster_implied_probabilities.csv", index=False, float_format="%.10g")
    features.to_csv(args.output / "cluster_features.csv", index=False, float_format="%.10g")
    if not results.empty:
        results.to_csv(args.output / "walk_forward_results.csv", index=False)
    write_report(args.output / "README.md", args, panel, features, data, status, results, corr)
    print(f"{status}; wrote {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")
    return panel, features, data, results


if __name__ == "__main__":
    main()
