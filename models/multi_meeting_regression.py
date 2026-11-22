"""Multi-meeting wallet-cluster regression (rolling, past-only).

For every Fed meeting with collected trades, in time order:

1. Behaviour window: trades strictly before the meeting's clustering cutoff
   (decision cutoff minus ``--signal-days``). Run same-owner grouping and hard
   rules on that window only.
2. Clustering: fit **once** on the first ``--fit-meetings`` meetings (pooled
   eligible entities), then freeze. Every meeting's entities are assigned to
   the frozen centroids, so C0..C(K-1) mean the same thing everywhere.
3. Signals: for each day from the clustering cutoff to the decision cutoff,
   cluster-implied probabilities from member trades in the trailing window.
4. N x M features per day -> join SPY targets -> event-level walk-forward
   (earlier meetings train, each later meeting is a test block).

Trades are found in ``datasets/polymarket/market_<id>/`` or the collector's
``tmp/polymarket/history_market_<id>/``. Meetings with missing markets are
skipped and listed in the report.

    python models/multi_meeting_regression.py
    python models/multi_meeting_regression.py --cluster-features expected_move_gap kl_from_market
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts" / "polymarket"))

from cluster_implied_probability import ImpliedProbabilityConfig, implied_probabilities  # noqa: E402
from cluster_regression import SUMMARY_FEATURES, build_dataset, cluster_features, correlations, evaluate  # noqa: E402
from outcomes import normalize_outcomes, outcome_move  # noqa: E402
from wallet_pipeline.behaviour import ClusterConfig, FrozenClustering, entity_features, profiles  # noqa: E402
from wallet_pipeline.meetings import registry  # noqa: E402
from wallet_pipeline.owners import OwnerConfig, assign_entities, co_trading_pairs, linked_pairs  # noqa: E402
from wallet_pipeline.rules import RuleConfig, apply_rules, rule_counts  # noqa: E402
from wallet_pipeline.trades import load_trade_files  # noqa: E402

DEFAULT_OUTPUT = ROOT / "models" / "multi_meeting"


def load_probability() -> pd.DataFrame:
    probability = pd.read_csv(ROOT / "datasets" / "forward_probabilities.csv")
    probability["market_id"] = probability["market_id"].astype(str)
    probability["event_id"] = probability["event_id"].astype(str)
    probability["outcome"] = normalize_outcomes(probability["outcome"])
    return probability


def meeting_entities(trades: pd.DataFrame, cutoff, owner_cfg: OwnerConfig, rule_cfg: RuleConfig):
    """Stages 1-2 on the behaviour window (trades strictly before ``cutoff``)."""
    window = trades.loc[trades["timestamp_utc"].lt(cutoff)]
    wallets = window["wallet_address"].unique()
    entities = assign_entities(wallets, linked_pairs(co_trading_pairs(window, owner_cfg), owner_cfg), owner_cfg)
    features = apply_rules(entity_features(window, entities, cutoff), rule_cfg)
    return entities, features


def meeting_signals(trades, memberships, probability, meeting, config: ImpliedProbabilityConfig):
    asof = pd.to_datetime(probability["date"], utc=True)
    probs = probability.loc[probability["market_id"].isin(meeting.markets)
                            & asof.ge(meeting.cluster_cutoff_utc) & asof.le(meeting.decision_cutoff_utc)].copy()
    probs["asof_utc"] = pd.to_datetime(probs["date"], utc=True)
    cutoffs = {m: meeting.decision_cutoff_utc.isoformat() for m in meeting.markets}
    panel = implied_probabilities(trades, memberships,
                                  probs[["asof_utc", "event_id", "market_id", "outcome", "market_probability"]],
                                  config, decision_cutoffs=cutoffs)
    panel["move"] = outcome_move(panel["outcome"])
    return panel


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    probability = load_probability()
    meetings = registry(ROOT, probability, args.signal_days)
    available = meetings.loc[meetings["trades_available"]].reset_index(drop=True)
    if len(available) <= args.fit_meetings:
        raise SystemExit(f"Need more than {args.fit_meetings} meetings with trades; found {len(available)}: "
                         f"{available['meeting_month'].tolist()}")
    owner_cfg, rule_cfg, cluster_cfg = OwnerConfig(), RuleConfig(), ClusterConfig()
    imp_cfg = ImpliedProbabilityConfig(window=pd.Timedelta(days=args.window_days),
                                       shrinkage_k=args.shrinkage_k, beta=args.beta)

    # Stages 1-2 per meeting (behaviour window only).
    per_meeting = {}
    for meeting in available.itertuples():
        files = [ROOT / f for f in meeting.trade_files.values()]
        trades = load_trade_files(files, cutoff=meeting.decision_cutoff_utc)
        entities, features = meeting_entities(trades, meeting.cluster_cutoff_utc, owner_cfg, rule_cfg)
        per_meeting[meeting.event_id] = dict(trades=trades, entities=entities, features=features)
        print(f"{meeting.meeting_month}: {len(trades):,} trades, {int(features['eligible'].sum()):,} eligible entities", flush=True)

    # Meetings with too few eligible entities cannot be fitted or assigned.
    skipped = {e: f"only {int(v['features']['eligible'].sum())} eligible entities"
               for e, v in per_meeting.items() if v["features"]["eligible"].sum() < args.min_eligible}
    available = available.loc[~available["event_id"].isin(skipped)].reset_index(drop=True)
    if len(available) <= args.fit_meetings:
        raise SystemExit(f"Too few usable meetings after skipping {skipped}")

    # Stage 3: fit once on the earliest meetings, then freeze.
    fit_ids = available["event_id"].iloc[:args.fit_meetings].tolist()
    fit_pool = pd.concat([per_meeting[e]["features"].loc[lambda f: f["eligible"]].assign(event_id=e)
                          for e in fit_ids], ignore_index=True)
    fit_pool["entity_id"] = fit_pool["event_id"] + ":" + fit_pool["entity_id"]
    version = f"multi_{'_'.join(available['meeting_month'].iloc[:args.fit_meetings])}"
    frozen, frame, labels, diagnostics = FrozenClustering.fit(fit_pool, version, cluster_cfg)
    frozen.model_version = f"{version}_k{frozen.summary['selected_k']}"
    joblib.dump(frozen, out / "frozen_clustering.joblib")
    profiles(frame, labels, frozen.retained).to_csv(out / "cluster_profiles.csv", index=False, float_format="%.6g")
    diagnostics.to_csv(out / "selection_diagnostics.csv", index=False, float_format="%.6g")

    # Assign every meeting and build signals.
    panels, summary_rows, membership_frames = [], [], []
    for meeting in available.itertuples():
        state = per_meeting[meeting.event_id]
        eligible = state["features"].loc[state["features"]["eligible"]]
        assigned = frozen.assign(eligible)
        members = state["entities"].merge(assigned, on="entity_id", how="inner")
        members["event_id"] = meeting.event_id
        membership_frames.append(members)
        panel = meeting_signals(state["trades"], members, probability, meeting, imp_cfg)
        panels.append(panel)
        summary_rows.append(dict(
            meeting=meeting.meeting_month, event_id=meeting.event_id, role="fit" if meeting.event_id in fit_ids else "assign",
            decision_cutoff=meeting.decision_cutoff_utc.date(), cutoff_source=meeting.cutoff_source,
            collection_complete=meeting.collection_complete, trades=len(state["trades"]),
            eligible_entities=int(state["features"]["eligible"].sum()),
            multi_wallet_entities=int(state["entities"].loc[state["entities"]["owner_status"].eq("merged"), "entity_id"].nunique()),
            signal_days=panel["asof_utc"].nunique(),
            **{f"n_{c}": int((assigned["cluster_id"] == c).sum()) for c in sorted(frozen.summary["cluster_sizes"])}))
    panel = pd.concat(panels, ignore_index=True)
    memberships = pd.concat(membership_frames, ignore_index=True)
    features = cluster_features(panel, args.feature_mode, args.cluster_features)
    data = build_dataset(features)
    cluster_columns = [c for c in features.columns if "__" in c]
    results, status = evaluate(data, cluster_columns)
    corr = correlations(data, [c for c in cluster_columns if not c.endswith("__active_entities")])

    gz = {"method": "gzip", "mtime": 0}
    panel.to_csv(out / "cluster_implied_probabilities.csv.gz", index=False, float_format="%.10g", compression=gz)
    memberships.to_csv(out / "memberships.csv.gz", index=False, float_format="%.8g", compression=gz)
    features.to_csv(out / "cluster_features.csv", index=False, float_format="%.10g")
    pd.DataFrame(summary_rows).to_csv(out / "meetings.csv", index=False)
    if not results.empty:
        results.to_csv(out / "walk_forward_results.csv", index=False)
    write_report(out, args, meetings, pd.DataFrame(summary_rows), frozen, data, status, results, corr,
                 cluster_columns, skipped)
    print(status)
    return dict(meetings=summary_rows, status=status, results=results)


def write_report(out, args, meetings, used, frozen, data, status, results, corr, cluster_columns, skipped):
    model_columns = [c for c in cluster_columns if not c.endswith("__active_entities")]
    missing = meetings.loc[~meetings["trades_available"] & meetings["decision_cutoff_utc"].ge(pd.Timestamp("2025-12-01", tz="UTC")),
                           ["meeting_month", "markets_with_trades", "markets"]]
    lines = [
        "# Multi-meeting wallet-cluster regression", "",
        f"- Frozen clustering `{frozen.model_version}`: fit on {args.fit_meetings} earliest meeting(s), "
        f"{frozen.summary['fit_entities']:,} entities, K = {frozen.summary['selected_k']}, "
        f"silhouette {frozen.summary['mean_silhouette']:.3f}, seed ARI {frozen.summary['seed_stability_ari']:.3f}",
        f"- Signals: {args.signal_days:g} days before each decision cutoff; window {args.window_days:g} d, "
        f"k = {args.shrinkage_k:g}, beta = {args.beta:g}; feature mode `{args.feature_mode}` "
        f"({', '.join(args.cluster_features) if args.feature_mode == 'summary' else 'all'})",
        f"- N x M = {len(model_columns)} cluster inputs; {len(data)} SPY trading-day rows across "
        f"{data['event_id'].nunique()} meeting(s)",
        f"- Status: **{status}**", "",
        "## Meetings used", "", used.to_markdown(index=False), "",
    ]
    if skipped:
        lines += ["## Meetings skipped for too few eligible entities", "",
                  *[f"- {meetings.set_index('event_id').loc[e, 'meeting_month']}: {why}" for e, why in skipped.items()], ""]
    if not missing.empty:
        lines += ["## Meetings since Dec 2025 without complete trades (skipped)", "",
                  missing.to_markdown(index=False), ""]
    if not results.empty:
        grouped = results.groupby(["target", "horizon", "feature_set", "model"], as_index=False).agg(
            folds=("test_event_id", "nunique"), test_rows=("test_rows", "sum"),
            mean_rmse=("rmse", "mean"), pooled_rmse=("rmse", lambda v: float(np.sqrt(np.mean(v ** 2)))),
            mean_r2=("r2", "mean"))
        lines += ["## Walk-forward results (each later meeting held out)", "",
                  "Cluster features help only if `history_plus_event_plus_cluster` beats "
                  "`history_plus_event` for the same target, horizon and model.", ""]
        for (target, horizon), group in grouped.groupby(["target", "horizon"]):
            lines += [f"### {target}, {horizon} trading day(s)", "",
                      group.sort_values("pooled_rmse").round(6).to_markdown(index=False), ""]
    if not corr.empty:
        top = corr.reindex(corr["spearman"].abs().sort_values(ascending=False).index).head(20)
        lines += ["## Largest exploratory Spearman correlations (descriptive only)", "",
                  top.round(4).to_markdown(index=False), ""]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fit-meetings", type=int, default=2)
    parser.add_argument("--min-eligible", type=int, default=30, help="skip meetings with fewer eligible entities")
    parser.add_argument("--signal-days", type=float, default=16.0)
    parser.add_argument("--window-days", type=float, default=7.0)
    parser.add_argument("--shrinkage-k", type=float, default=3.0)
    parser.add_argument("--beta", type=float, default=2.0)
    parser.add_argument("--feature-mode", choices=("summary", "levels", "per_outcome"), default="summary")
    parser.add_argument("--cluster-features", nargs="+", default=["expected_move_gap", "kl_from_market"],
                        choices=SUMMARY_FEATURES, help="summary features per cluster (M); default M = 2")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    main()
