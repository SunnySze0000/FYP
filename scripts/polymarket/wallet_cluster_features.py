"""Past-only behavioural features and frozen, exploratory wallet clustering.

Trade rows retain their participant-record multiplicity. Neither their net flow
nor the clustering describes holdings, profitability, or private probabilities.
"""
from __future__ import annotations

from itertools import combinations
from math import ceil
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_samples, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, RobustScaler


CLUSTER_FEATURES = [
    "active_days", "transactions_per_active_day", "median_trade_notional_usd",
    "events_traded", "median_event_top_market_fraction", "two_sided_token_fraction",
    "busiest_day_transaction_fraction", "median_transaction_gap_hours",
]
FEATURE_NAMES = CLUSTER_FEATURES + [
    "participant_rows", "unique_transactions", "gross_shares",
    "gross_participant_notional_usd", "max_daily_transaction_count",
    "p90_trade_notional_usd", "median_trade_shares", "markets_traded",
    "event_participation_fraction", "top_event_notional_fraction",
    "median_event_outcome_entropy", "buy_share_fraction", "yes_token_share_fraction",
    "buy_yes_shares", "sell_yes_shares", "buy_no_shares", "sell_no_shares",
    "absolute_market_netting_ratio", "p90_transaction_gap_hours",
    "days_since_last_trade", "observed_span_days", "active_week_fraction",
]
LOG_FEATURES = {
    "active_days", "transactions_per_active_day", "median_trade_notional_usd",
    "events_traded", "median_transaction_gap_hours",
}


def _bool(value):
    return value is True or str(value).lower() in {"true", "1"}


def _utc(value):
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("Feature timestamps must include a timezone")
    return parsed.tz_convert("UTC")


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator > 0 else np.nan


def _empty_features():
    values = {name: np.nan for name in FEATURE_NAMES}
    for name in ["active_days", "events_traded", "participant_rows", "unique_transactions",
                 "gross_shares", "gross_participant_notional_usd", "max_daily_transaction_count",
                 "markets_traded", "event_participation_fraction", "buy_yes_shares",
                 "sell_yes_shares", "buy_no_shares", "sell_no_shares", "active_week_fraction"]:
        values[name] = 0
    return values


def build_features(cohort, trades, coverage, market_map, config):
    """Return all cohort wallets, including incomplete and ineligible histories.

    Duplicate diagnostics are recomputed inside each filtered observation
    window; a duplicate occurring after the feature cutoff cannot affect it.
    """
    cutoff = _utc(config["selection_cutoff_utc"])
    start = _utc(config["observation_start_utc"])
    if start >= cutoff:
        raise ValueError("Observation start must precede snapshot cutoff")
    events = set(map(str, config["history_event_ids"]))
    if not events:
        raise ValueError("Historical event universe is empty")
    addresses = [str(row["wallet_address"]).lower() for row in cohort]
    if len(set(addresses)) != len(addresses):
        raise ValueError("Cohort addresses must be unique")
    meta = {}
    for row in market_map:
        if str(row["event_id"]) not in events:
            continue
        key = str(row["market_id"])
        end = _utc(row["decision_cutoff_utc"])
        item = (str(row["event_id"]), min(end, cutoff))
        if key in meta and meta[key] != item:
            raise ValueError("Inconsistent historical market cutoffs")
        meta[key] = item
    if set(event for event, _ in meta.values()) != events:
        raise ValueError("Market map does not cover every requested historical event")
    event_market_count = {}
    for event, _ in meta.values():
        event_market_count[event] = event_market_count.get(event, 0) + 1

    cov = {}
    for row in coverage:
        key = (str(row["wallet_address"]).lower(), str(row["event_id"]))
        if key in cov:
            raise ValueError("Duplicate wallet/event coverage row")
        cov[key] = row

    # Explicit source allowlist ensures outcome/performance labels cannot enter
    # the feature matrix if a collector carries them as separate audit metadata.
    keep = ["wallet_address", "event_id", "market_id", "token_id", "token_outcome",
            "timestamp_utc", "transaction_hash", "side", "shares", "price", "notional_usd",
            "record_fingerprint", "chain_verification"]
    frame = pd.DataFrame(trades).reindex(columns=keep)
    if len(frame):
        frame["wallet_address"] = frame.wallet_address.str.lower()
        frame["event_id"] = frame.event_id.astype(str)
        frame["market_id"] = frame.market_id.astype(str)
        frame = frame.loc[frame.wallet_address.isin(addresses) & frame.event_id.isin(events)].copy()
        frame["timestamp"] = pd.to_datetime(frame.timestamp_utc, utc=True, errors="raise")
        if not frame.market_id.isin(meta).all():
            raise ValueError("Historical trade lacks a declared market cutoff")
        if any(meta[market][0] != event for market, event in zip(frame.market_id, frame.event_id)):
            raise ValueError("Historical trade event/market mapping disagrees")
        limits = pd.to_datetime(frame.market_id.map(lambda market: meta[market][1]), utc=True)
        frame = frame.loc[(frame.timestamp >= start) & (frame.timestamp < limits)].copy()
        for column in ["shares", "price", "notional_usd"]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        if (not np.isfinite(frame[["shares", "price", "notional_usd"]].to_numpy()).all()
                or (frame.shares <= 0).any() or (frame.notional_usd < 0).any()
                or (~frame.price.between(0, 1)).any()
                or not frame.side.isin(["BUY", "SELL"]).all()
                or not frame.token_outcome.isin(["YES", "NO"]).all()):
            raise ValueError("Invalid accepted historical trade values")
        frame["day"] = frame.timestamp.dt.floor("D")
        frame["signed_flow"] = np.where(
            (frame.side == "BUY") == (frame.token_outcome == "YES"), frame.shares, -frame.shares)

    all_weeks = len(pd.date_range(start.normalize(), (cutoff - pd.Timedelta(nanoseconds=1)).normalize(),
                                  freq="D").tz_localize(None).to_period("W-SUN").unique())
    output = []
    for wallet in addresses:
        observed = frame.loc[frame.wallet_address.eq(wallet)].copy() if len(frame) else frame.copy()
        complete_events = sum(_bool(cov.get((wallet, event), {}).get("complete", False)) for event in events)
        values = _empty_features()
        duplicate_fraction = 0.0
        duplicate_check_available = True
        chain_issue_rows = 0
        first = last = None
        if len(observed):
            values["participant_rows"] = len(observed)
            transactions = observed.groupby("transaction_hash", sort=True).timestamp.min().sort_values()
            days = transactions.dt.floor("D").value_counts()
            gaps = transactions.diff().dropna().dt.total_seconds() / 3600
            gross_shares = observed.shares.sum()
            gross_notional = observed.notional_usd.sum()
            event_notional = observed.groupby("event_id").notional_usd.sum()
            market_notional = observed.groupby(["event_id", "market_id"]).notional_usd.sum()
            top_fractions, entropies = [], []
            for event, total in event_notional.items():
                amounts = market_notional.loc[event]
                if total > 0:
                    proportions = amounts.loc[amounts > 0] / total
                    top_fractions.append(float(amounts.max() / total))
                    denominator = np.log(event_market_count[event])
                    entropies.append(float(-(proportions * np.log(proportions)).sum() / denominator)
                                     if denominator > 0 else 0.0)
            token_directions = observed.groupby(["market_id", "token_id"]).side.nunique()
            first, last = observed.timestamp.min(), observed.timestamp.max()
            values.update({
                "active_days": int(len(days)),
                "transactions_per_active_day": len(transactions) / len(days),
                "median_trade_notional_usd": float(observed.notional_usd.median()),
                "events_traded": int(observed.event_id.nunique()),
                "median_event_top_market_fraction": float(np.median(top_fractions)) if top_fractions else np.nan,
                "two_sided_token_fraction": float((token_directions == 2).mean()),
                "busiest_day_transaction_fraction": float(days.max() / len(transactions)),
                "median_transaction_gap_hours": float(gaps.median()) if len(gaps) else np.nan,
                "unique_transactions": int(len(transactions)),
                "gross_shares": float(gross_shares),
                "gross_participant_notional_usd": float(gross_notional),
                "max_daily_transaction_count": int(days.max()),
                "p90_trade_notional_usd": float(observed.notional_usd.quantile(.9)),
                "median_trade_shares": float(observed.shares.median()),
                "markets_traded": int(observed.market_id.nunique()),
                "event_participation_fraction": observed.event_id.nunique() / len(events),
                "top_event_notional_fraction": _ratio(event_notional.max(), gross_notional),
                "median_event_outcome_entropy": float(np.median(entropies)) if entropies else np.nan,
                "buy_share_fraction": _ratio(observed.loc[observed.side.eq("BUY"), "shares"].sum(), gross_shares),
                "yes_token_share_fraction": _ratio(observed.loc[observed.token_outcome.eq("YES"), "shares"].sum(), gross_shares),
                "absolute_market_netting_ratio": _ratio(
                    observed.groupby(["event_id", "market_id"]).signed_flow.sum().abs().sum(), gross_shares),
                "p90_transaction_gap_hours": float(gaps.quantile(.9)) if len(gaps) else np.nan,
                "days_since_last_trade": (cutoff - last).total_seconds() / 86400,
                "observed_span_days": (last - first).total_seconds() / 86400,
                "active_week_fraction": observed.timestamp.dt.tz_localize(None).dt.to_period("W-SUN").nunique() / all_weeks,
            })
            for side in ["BUY", "SELL"]:
                for token in ["YES", "NO"]:
                    values[f"{side.lower()}_{token.lower()}_shares"] = float(
                        observed.loc[observed.side.eq(side) & observed.token_outcome.eq(token), "shares"].sum())
            duplicate_check_available = observed.record_fingerprint.notna().all() and observed.record_fingerprint.ne("").all()
            if duplicate_check_available:
                duplicate_fraction = float(observed.record_fingerprint.duplicated(keep=False).mean())
            else:
                duplicate_fraction = np.nan
            chain_issue_rows = int((~observed.chain_verification.fillna("not_checked").isin(
                ["not_checked", "matched_unique"])).sum())
        reasons = []
        if complete_events != len(events):
            reasons.append("incomplete_collection")
        if values["events_traded"] < 2:
            reasons.append("fewer_than_2_historical_meetings")
        if values["active_days"] < 5:
            reasons.append("fewer_than_5_active_days")
        if values["unique_transactions"] < 10:
            reasons.append("fewer_than_10_transactions")
        if not duplicate_check_available:
            reasons.append("duplicate_check_unavailable")
        elif duplicate_fraction > .05:
            reasons.append("duplicate_candidate_fraction_above_5_percent")
        if chain_issue_rows:
            reasons.append("observed_chain_reconciliation_issue")
        if not np.isfinite([values[name] for name in CLUSTER_FEATURES]).all():
            reasons.append("undefined_clustering_feature")
        # A partially served history is not an observed zero or a complete
        # behavioural profile. Preserve its retrieved-row count as audit
        # metadata, but withhold model features until collection is complete.
        retrieved_rows = int(values["participant_rows"])
        feature_values_complete = complete_events == len(events)
        if not feature_values_complete:
            values = {name: np.nan for name in FEATURE_NAMES}
        output.append({
            "snapshot_id": config["snapshot_id"], "wallet_address": wallet,
            "selection_cutoff_utc": cutoff.isoformat(), "observation_start_utc": start.isoformat(),
            "observation_end_utc": cutoff.isoformat(),
            "first_feature_trade_utc": first.isoformat() if first is not None else "",
            "last_feature_trade_utc": last.isoformat() if last is not None else "",
            "queried_events": len(events), "complete_events": complete_events,
            "coverage_complete": complete_events == len(events),
            "feature_values_complete": feature_values_complete,
            "observed_participant_rows": retrieved_rows,
            "duplicate_candidate_fraction": duplicate_fraction,
            "duplicate_check_available": bool(duplicate_check_available),
            "chain_issue_rows": chain_issue_rows, "eligible": not reasons,
            "eligibility_status": "eligible" if not reasons else ";".join(reasons), **values,
        })
    return pd.DataFrame(output)


def _transform_selected(frame, columns):
    result = frame.loc[:, columns].copy()
    for name in columns:
        if name in LOG_FEATURES:
            result[name] = np.log1p(result[name])
    return result


def _plots(out, transformed, labels, feature_names, model, diagnostics):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_dir = out / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, max(3.5, model.n_clusters * .7)))
    image = ax.imshow(model.cluster_centers_, aspect="auto", cmap="RdBu_r")
    ax.set_xticks(range(len(feature_names)), [name.replace("_", " ") for name in feature_names],
                  rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(model.n_clusters), [f"C{i} (n={(labels == i).sum()})" for i in range(model.n_clusters)])
    ax.set_title("Frozen wallet clusters: transformed feature centres")
    fig.colorbar(image, ax=ax, label="Robust-scaled feature value")
    fig.tight_layout()
    fig.savefig(chart_dir / "cluster_feature_profiles.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    grouped = diagnostics.groupby("k").silhouette.agg(["mean", "min", "max"])
    ax.errorbar(grouped.index, grouped["mean"],
                yerr=[grouped["mean"] - grouped["min"], grouped["max"] - grouped["mean"]], fmt="o-")
    ax.set(xlabel="Number of clusters", ylabel="Silhouette score",
           title="Cluster separation across five initialisation seeds")
    ax.set_xticks(grouped.index)
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(chart_dir / "cluster_selection.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    sample_scores = silhouette_samples(transformed, labels)
    offset = 0
    for cluster in range(model.n_clusters):
        values = np.sort(sample_scores[labels == cluster])
        positions = np.arange(offset, offset + len(values))
        ax.fill_betweenx(positions, 0, values, alpha=.75, label=f"C{cluster}")
        offset += len(values) + 3
    ax.axvline(sample_scores.mean(), color="black", linestyle="--", linewidth=1)
    ax.set(xlabel="Silhouette coefficient", ylabel="Wallets grouped by cluster",
           title="Selected clustering: within-cluster separation")
    ax.legend()
    fig.tight_layout()
    fig.savefig(chart_dir / "silhouette.png", dpi=160)
    plt.close(fig)

    components = min(2, transformed.shape[1])
    pca = PCA(n_components=components)
    projection = pca.fit_transform(transformed)
    if components == 1:
        projection = np.column_stack([projection[:, 0], np.zeros(len(projection))])
    fig, ax = plt.subplots(figsize=(7, 5))
    for cluster in range(model.n_clusters):
        points = projection[labels == cluster]
        ax.scatter(points[:, 0], points[:, 1], s=24, alpha=.75, label=f"C{cluster} (n={len(points)})")
    ax.set(xlabel=f"PC1 ({pca.explained_variance_ratio_[0]:.1%} variance)",
           ylabel=(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} variance)" if components == 2 else "Display axis"),
           title="Wallet feature projection — clustering uses the full selected space")
    ax.legend()
    ax.grid(alpha=.15)
    fig.tight_layout()
    fig.savefig(chart_dir / "wallet_pca.png", dpi=160)
    plt.close(fig)


def fit_clusters(features, config, out):
    """Fit a frozen pipeline; return memberships, profiles, diagnostics, report.

    Empty/low-coverage inputs return explicit unassigned memberships. Failed
    separation/size/stability checks produce a provisional result, not a claim
    that natural or useful behavioural groups have been established.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    eligible = features.loc[features.eligible.map(_bool)].copy()
    model_version = str(config["snapshot_id"]) + "_unfitted"
    memberships = features[["snapshot_id", "wallet_address", "eligibility_status"]].copy()
    memberships["model_version"] = model_version
    memberships["cluster_id"] = ""
    memberships["assignment_status"] = "ineligible_history"
    memberships["centroid_distance"] = np.nan
    memberships["representative_rank"] = np.nan
    memberships["valid_from_utc"] = _utc(config["selection_cutoff_utc"]).isoformat()
    report = {
        "model_version": model_version, "status": "not_fitted", "selected_k": None,
        "cohort_wallets": len(features), "eligible_wallets": len(eligible), "clustered_wallets": 0,
        "candidate_features": list(CLUSTER_FEATURES), "retained_features": [], "removed_features": [],
        "predictive_value_validated": False, "cluster_explanations": [],
    }
    profile_columns = ["model_version", "cluster_id", "wallet_count", "feature", "median", "q25", "q75",
                       "overall_median", "overall_q25", "overall_q75", "explanation"]
    diagnostic_columns = ["k", "seed", "silhouette", "min_cluster_size", "size_valid", "median_pairwise_ari"]
    def no_fit(reason):
        # A rerun can lose usable history or feature variation. Do not expose a
        # previous run's model or charts beside the current unfitted report.
        for artifact in [out / "pipeline.joblib", *[
            out / "charts" / name for name in (
                "cluster_feature_profiles.png", "cluster_selection.png",
                "silhouette.png", "wallet_pca.png")
        ]]:
            artifact.unlink(missing_ok=True)
        report["reason"] = reason
        memberships.loc[memberships.wallet_address.isin(eligible.wallet_address), "assignment_status"] = "eligible_but_unfitted"
        return {"memberships": memberships, "profiles": pd.DataFrame(columns=profile_columns),
                "diagnostics": pd.DataFrame(columns=diagnostic_columns), "report": report}

    if len(eligible) < 3:
        return no_fit("Fewer than three wallets have eligible complete histories")
    finite = np.isfinite(eligible[CLUSTER_FEATURES].to_numpy(dtype=float)).all()
    if not finite:
        raise ValueError("Eligible clustering inputs must be finite")
    retained = []
    for name in CLUSTER_FEATURES:
        iqr = eligible[name].quantile(.75) - eligible[name].quantile(.25)
        if iqr <= 0 or eligible[name].nunique() < 2:
            report["removed_features"].append({"feature": name, "reason": "constant_or_zero_interquartile_range"})
        else:
            retained.append(name)
    report["retained_features"] = retained
    if not retained:
        return no_fit("All candidate clustering features have zero interquartile range")

    # Library-native transformers keep the saved artifact loadable without
    # importing this script's helper functions into the consuming process.
    selector = ColumnTransformer([
        (f"feature_{index}", FunctionTransformer(np.log1p, validate=False)
         if name in LOG_FEATURES else "passthrough", [name])
        for index, name in enumerate(retained)
    ], remainder="drop", verbose_feature_names_out=False)
    scaler = RobustScaler()
    transformed = scaler.fit_transform(selector.fit_transform(eligible))
    seeds = [int(config.get("seed", 42)) + offset for offset in range(5)]
    minimum_size = max(5, ceil(.05 * len(eligible)))
    diagnostics, candidates = [], []
    max_k = min(6, len(eligible) - 1, len(np.unique(transformed, axis=0)))
    for k in range(2, max_k + 1):
        runs = []
        for seed in seeds:
            model = KMeans(n_clusters=k, init="k-means++", n_init=20, max_iter=300, random_state=seed)
            labels = model.fit_predict(transformed)
            if len(set(labels)) < 2:
                continue
            score = float(silhouette_score(transformed, labels))
            min_size = int(np.bincount(labels, minlength=k).min())
            runs.append({"k": k, "seed": seed, "silhouette": score,
                         "min_cluster_size": min_size, "size_valid": min_size >= minimum_size,
                         "model": model, "labels": labels})
        if not runs:
            continue
        stability = float(np.median([adjusted_rand_score(a["labels"], b["labels"])
                                    for a, b in combinations(runs, 2)])) if len(runs) > 1 else 1.0
        for run in runs:
            diagnostics.append({key: run[key] for key in diagnostic_columns if key != "median_pairwise_ari"}
                               | {"median_pairwise_ari": stability})
        candidates.append({"k": k, "runs": runs, "stability": stability,
                           "mean_silhouette": float(np.mean([r["silhouette"] for r in runs])),
                           "size_valid": all(r["size_valid"] for r in runs)})
    if not candidates:
        return no_fit("Fewer than two distinct feature profiles after preprocessing")
    valid = [candidate for candidate in candidates if candidate["size_valid"]]
    pool = valid or candidates
    best_score = max(candidate["mean_silhouette"] for candidate in pool)
    near_best = [candidate for candidate in pool if candidate["mean_silhouette"] >= best_score - .02]
    chosen = sorted(near_best, key=lambda candidate: (-candidate["stability"], candidate["k"]))[0]
    winner = sorted(chosen["runs"], key=lambda run: (-run["silhouette"], run["seed"]))[0]
    model, labels = winner["model"], winner["labels"]
    model_version = f"{config['snapshot_id']}_k{chosen['k']}_s{winner['seed']}"
    pipeline = Pipeline([("select_and_log", selector), ("scale", scaler), ("cluster", model)])
    joblib.dump(pipeline, out / "pipeline.joblib")
    distances = model.transform(transformed)[np.arange(len(eligible)), labels]
    membership_index = dict(zip(memberships.wallet_address, memberships.index))
    for index, (wallet, label, distance) in enumerate(zip(eligible.wallet_address, labels, distances)):
        row = membership_index[wallet]
        memberships.loc[row, ["cluster_id", "assignment_status", "centroid_distance"]] = [f"C{label}", "assigned", float(distance)]
    memberships["model_version"] = model_version

    profile_rows, descriptions = [], []
    for cluster in range(model.n_clusters):
        cluster_wallets = eligible.loc[labels == cluster]
        contrasts = []
        for name in retained:
            population_iqr = eligible[name].quantile(.75) - eligible[name].quantile(.25)
            contrasts.append((name, float((cluster_wallets[name].median() - eligible[name].median()) / population_iqr)))
        strongest = sorted(contrasts, key=lambda item: (-abs(item[1]), item[0]))[:3]
        explanation = "; ".join(f"{'higher' if value > 0 else 'lower'} {name.replace('_', ' ')}"
                                for name, value in strongest if abs(value) > .05)
        explanation = (explanation + " relative to the eligible cohort") if explanation else "Similar median profile to the eligible cohort"
        representatives = sorted(
            [(wallet, float(distance)) for wallet, label, distance in zip(eligible.wallet_address, labels, distances) if label == cluster],
            key=lambda item: (item[1], item[0]))[:3]
        for rank, (wallet, _) in enumerate(representatives, 1):
            memberships.loc[membership_index[wallet], "representative_rank"] = rank
        descriptions.append({"cluster_id": f"C{cluster}", "wallet_count": len(cluster_wallets),
                             "explanation": explanation, "representative_wallets": [wallet for wallet, _ in representatives]})
        for name in FEATURE_NAMES:
            data, overall = cluster_wallets[name], eligible[name]
            profile_rows.append({"model_version": model_version, "cluster_id": f"C{cluster}",
                                 "wallet_count": len(cluster_wallets), "feature": name,
                                 "median": data.median(), "q25": data.quantile(.25), "q75": data.quantile(.75),
                                 "overall_median": overall.median(), "overall_q25": overall.quantile(.25),
                                 "overall_q75": overall.quantile(.75), "explanation": explanation})
    provisional_reasons = []
    if len(eligible) < 50:
        provisional_reasons.append("fewer_than_50_eligible_wallets")
    if not chosen["size_valid"]:
        provisional_reasons.append("minimum_cluster_size_constraint_failed")
    if chosen["stability"] < .8:
        provisional_reasons.append("seed_stability_below_0.8_pilot_threshold")
    if chosen["mean_silhouette"] <= 0:
        provisional_reasons.append("nonpositive_mean_silhouette")
    report.update({"model_version": model_version, "selected_k": chosen["k"], "selected_seed": winner["seed"],
                   "clustered_wallets": len(eligible), "status": "provisional" if provisional_reasons else "exploratory",
                   "provisional_reasons": provisional_reasons, "mean_silhouette": chosen["mean_silhouette"],
                   "selected_run_silhouette": winner["silhouette"], "median_pairwise_ari": chosen["stability"],
                   "minimum_cluster_size_required": minimum_size, "minimum_cluster_size_observed": winner["min_cluster_size"],
                   "cluster_explanations": descriptions, "log_features": sorted(set(retained) & LOG_FEATURES),
                   "seed_list": seeds, "n_init": 20, "max_iter": 300})
    diagnostic_frame = pd.DataFrame(diagnostics, columns=diagnostic_columns)
    _plots(out, transformed, labels, retained, model, diagnostic_frame)
    return {"memberships": memberships, "profiles": pd.DataFrame(profile_rows, columns=profile_columns),
            "diagnostics": diagnostic_frame, "report": report}
