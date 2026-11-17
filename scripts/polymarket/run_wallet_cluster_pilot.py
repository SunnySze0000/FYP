#!/usr/bin/env python3
"""Reproduce the frozen Fed-wallet pilot without changing the source exports."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "tmp/wallet_cluster_matplotlib"))
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "tmp/wallet_cluster_cache"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from collect_history import atomic_json
from wallet_cluster_collect import collect_history, select_cohort


def write_rows(path, rows, fields=None):
    """Deterministic CSV/gzip output: fixed gzip timestamp, ordered field union."""
    fields = fields or list(dict.fromkeys(key for row in rows for key in row))
    if not fields:
        fields = ["source_snapshot_id", "wallet_address", "timestamp_utc"]
    if path.suffix == ".gz":
        import io
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
    else:
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def read_rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def source_hashes(root):
    paths = [root / "datasets/forward_probabilities.csv",
             root / "datasets/polymarket/event_101772/wallet_discovery/wallet_summary_pre_cutoff.csv",
             root / "datasets/polymarket/event_101772/prior_history/prior_market_tokens.csv",
             root / "datasets/polymarket/event_101772/market_inventory.csv",
             root / "datasets/polymarket/event_101772/market_tokens.csv"]
    for market in range(906972, 906977):
        paths.extend(root / f"datasets/polymarket/market_{market}" / name
                     for name in ("wallet_trades.csv.gz", "manifest.json"))
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def validate(features, memberships, daily, config, history_trades, market_map):
    import numpy as np
    import pandas as pd
    from wallet_cluster_features import FEATURE_NAMES
    tests = {}
    tests["one_feature_row_per_selected_wallet"] = len(features) == config["target_wallets"] and not features.wallet_address.duplicated().any()
    tests["thirty_documented_features"] = len(FEATURE_NAMES) == 30 and set(FEATURE_NAMES).issubset(features.columns)
    tests["one_membership_row_per_selected_wallet"] = len(memberships) == len(features) and not memberships.wallet_address.duplicated().any()
    tests["historical_rows_are_descriptive_only"] = daily["historical"].empty or not daily["historical"].forecast_input_allowed.any()
    signal = daily["signals"]
    tests["unique_signal_keys"] = not signal.duplicated(["asof_utc", "event_id", "market_id", "cluster_id", "model_version"]).any()
    tests["signal_cutoffs"] = signal.empty or (pd.to_datetime(signal.asof_utc, utc=True).ge(pd.Timestamp(config["selection_cutoff_utc"])) & pd.to_datetime(signal.asof_utc, utc=True).le(pd.to_datetime(signal.decision_cutoff_utc, utc=True))).all()
    tests["daily_midnight_utc"] = signal.empty or (pd.to_datetime(signal.asof_utc, utc=True).dt.hour.eq(0) & pd.to_datetime(signal.asof_utc, utc=True).dt.minute.eq(0)).all()
    maps = {str(row["market_id"]): row for row in market_map}
    assigned = set(memberships.loc[memberships.cluster_id.notna() & memberships.cluster_id.ne(""), "wallet_address"])
    # Independently reconcile raw source records with exported daily totals.
    # Do not sum unique-transaction counts across markets/clusters: they overlap.
    tests["raw_to_daily_reconciliation"] = True
    tests["raw_to_feature_reconciliation"] = True
    history = pd.DataFrame(history_trades)
    if not history.empty:
        history["_time"] = pd.to_datetime(history.timestamp_utc, utc=True)
        history["_limit"] = pd.to_datetime(history.market_id.map(lambda mid: maps[str(mid)]["decision_cutoff_utc"]), utc=True)
        filtered = history.loc[history._time.ge(pd.Timestamp(config["observation_start_utc"]))
                               & history._time.lt(pd.Timestamp(config["selection_cutoff_utc"]))
                               & history._time.lt(history._limit)]
        for row in features.loc[features.coverage_complete].itertuples():
            raw = filtered.loc[filtered.wallet_address.eq(row.wallet_address)]
            tests["raw_to_feature_reconciliation"] &= len(raw) == row.participant_rows and np.isclose(pd.to_numeric(raw.shares).sum(), row.gross_shares)
    for panel, raw_source in ((signal, daily["target_trades"]), (daily["historical"], history)):
        if panel.empty:
            continue
        for mid, part in panel.groupby("market_id"):
            if not part.coverage_complete.all():
                continue
            raw = raw_source.loc[raw_source.market_id.astype(str).eq(str(mid)) & raw_source.wallet_address.isin(assigned)].copy()
            times = pd.to_datetime(raw.timestamp_utc, utc=True)
            raw = raw.loc[times.ge(pd.to_datetime(part.interval_start_utc, utc=True).min()) & times.lt(pd.to_datetime(part.asof_utc, utc=True).max())]
            tests["raw_to_daily_reconciliation"] &= len(raw) == part.participant_rows.sum()
            tests["raw_to_daily_reconciliation"] &= np.isclose(pd.to_numeric(raw.shares).sum(), part.gross_shares.sum())
            tests["raw_to_daily_reconciliation"] &= np.isclose(pd.to_numeric(raw.notional_usd).sum(), part.gross_participant_notional_usd.sum())
    tests["four_direction_reconciliation"] = True
    tests["bounded_imbalances"] = True
    tests["missing_coverage_is_not_zero_activity"] = True
    for panel in (signal, daily["historical"]):
        if panel.empty:
            continue
        complete = panel.loc[panel.coverage_complete]
        expected = complete.buy_yes_shares - complete.sell_yes_shares - complete.buy_no_shares + complete.sell_no_shares
        tests["four_direction_reconciliation"] &= bool(np.allclose(complete.signed_yes_flow_shares, expected))
        for column in ("aggregate_directional_imbalance", "equal_weight_directional_imbalance"):
            tests["bounded_imbalances"] &= bool(panel[column].dropna().between(-1 - 1e-12, 1 + 1e-12).all())
        tests["missing_coverage_is_not_zero_activity"] &= bool(panel.loc[~panel.coverage_complete, "gross_shares"].isna().all())
    tests = {key: bool(value) for key, value in tests.items()}
    if not all(tests.values()):
        raise AssertionError(f"Pilot validation failed: {tests}")
    return tests


def write_readme(output, report):
    """Create a self-contained teammate handoff with the actual coverage."""
    c, d = report["clustering"], report["daily"]
    cluster_lines = "\n".join(f"- **{row['cluster_id']} ({row['wallet_count']} wallets):** {row['explanation']}." for row in c["cluster_explanations"])
    guide = f'''# Frozen Fed-wallet clustering pilot

## Result

Selected **{report['collection']['wallets_requested']} wallets**; completed all their four-meeting API queries; accepted **{report['collection']['participant_rows']:,} historical participant records** with **{report['collection']['rejected_rows']} rejected**.
**{c['clustered_wallets']} wallets were clustered**, not 150. The other wallets retain explicit unassigned statuses and eligibility reasons. Final status: **{c['status']}**. This is a reduced-cohort integration pilot, not evidence of predictive value or wallet skill.

{cluster_lines}

The export contains **30 behavioural features for every selected wallet**, memberships, feature distributions, representative wallets, and four diagnostic charts. Undefined features are missing. Incomplete history never becomes zero activity.

Daily prediction-input panel: **{d['forecast_signal_rows']} rows**, from **{d['forecast_start_utc']}** through **{d['forecast_end_utc']}**, across five June policy-outcome markets. Only assigned wallets contribute to cluster signals; **{d['unassigned_wallets_excluded_from_cluster_signals']} selected wallets are excluded**. Earlier descriptive panel: **{d['historical_descriptive_rows']} rows**.

## Start here

| File | Meaning |
|---|---|
| `wallet_features.csv` | All 150 selected wallets, 30 features, cutoff/coverage and eligibility explanations |
| `cluster_membership.csv` | All 150 wallets; assigned C0/C1 or empty cluster ID, model version, centroid distance, representative rank |
| `cluster_profiles.csv` | Every cluster/feature median and quartiles, cohort comparison and explanation |
| `daily_cluster_signals.csv` | Post-snapshot, midnight-UTC June cluster/market activity |
| `historical_cluster_activity.csv` | Earlier descriptive activity; **never a historical forecast input** |
| `trades.csv.gz` | Historical and June participant records for the selected cohort, with source provenance |
| `historical_trades.csv.gz` | Frozen four-meeting collection used to build features |
| `cohort.csv` | Deterministic proportional sample and stratum allocations |
| `history_coverage.csv` | 150 wallets × 4 historical meetings, including complete empty queries |
| `target_coverage.csv` | 150 wallets × 5 June markets and source-export checks |
| `market_map.csv` | Event/market/condition/token mappings and approximate decision cutoffs |
| `feature_dictionary.json`, `schema.json` | Exact feature definitions, units, transformations and table fields |
| `config.json`, `report.json`, `clustering_diagnostics.csv` | Parameters, coverage, model selection and validations |
| `source_hashes.json`, `implementation_hashes.json`, `SHA256SUMS` | Frozen-input, implementation and output integrity |
| `pipeline.joblib`, `requirements.lock.txt` | Saved preprocessing/clustering and exact installed packages |

## Dates and provenance

- Wallet discovery uses June-event activity strictly before **2026-05-31T00:00:00Z**, starting from the existing 1,596-eligible-wallet cohort.
- Sample 150 proportionally from broad/focused June participation crossed with within-group transaction-count thirds. Rank each stratum with SHA256(seed|address), seed 42. This is not a random sample of all Polymarket traders.
- Feature window starts **2025-12-01T00:00:00Z**. Events: December 2025 (`35090`), January 2026 (`45883`), March 2026 (`67284`), April 2026 (`75478`). Each stops strictly before its recorded Gamma endDate minus 24 hours, or the snapshot cutoff if earlier.
- June is the target event (`101772`); June records do not enter the clustering feature matrix. June activity before the snapshot is used for discovery, which makes the earlier descriptive sample retrospectively selected.
- The cluster model is frozen at the May 31 information cutoff. For daily timestamp `t`, include only trades in `[t−24 hours,t)`. The first May 31 row therefore describes May 30. A trade exactly at midnight belongs to the following day's row.
- June's approximate decision cutoff is **2026-06-16T00:00:00Z**, verified consistently from current Gamma endDate metadata. No signal row uses later trading. This is a conservative convention, **not the exact FOMC announcement time**.
- Historical daily panels use memberships fitted later and always set `forecast_input_allowed=false`.
- `forecast_input_allowed=true` in the June panel means structurally timestamp-eligible for this retrospective experiment. Actual contemporaneous API availability is **unverified**, as recorded in `availability_basis`.
- API size floor: 0.01 shares. Cursor exhaustion covers served queries, not all chain history. Source addresses can represent linked participants and are not guaranteed independent people.

## Eligibility and clustering

Cluster fitting requires complete coverage of all four queried meetings, participation in at least 2 meetings, 5 active UTC days, 10 distinct transactions, duplicate-candidate row fraction ≤5%, no observed reconciliation issue, and finite clustering inputs.

Eight candidates: active days; transactions per active day; median participant-record notional; events participated; median within-event largest-market notional fraction; two-sided token fraction; busiest-day transaction fraction; median transaction gap. Exact definitions and the 22 additional fields are in `feature_dictionary.json`.

Apply saved log1p transformations to skewed counts/rates/sizes/gaps; remove zero-IQR/constant candidates with a report; fit RobustScaler on eligible histories only. Fit KMeans for K=2–6, five seeds 42–46, 20 initialisations, 300 iterations. Minimum cluster size=max(5,ceil(0.05N)). Prefer valid solutions by mean silhouette; within 0.02 prefer seed stability then smaller K. If none satisfies size constraints, any fallback is explicitly provisional. Fewer than 50 eligible wallets also makes this pilot provisional. PCA is display-only.

Do not interpret seed agreement as temporal stability or predictive skill. Centroid distance is not a probability or calibrated confidence. Cluster IDs are specific to this saved model version.

## Signal definitions

For each event/outcome market/cluster/day:

`D = BUY_YES − SELL_YES + SELL_NO − BUY_NO`, in shares.

`aggregate_directional_imbalance = sum(D) / sum(gross_shares)`.

The equal-wallet version averages each active wallet's `D/gross_shares`. No activity produces zero counts/sums but missing imbalance and concentration ratios. Missing coverage produces missing activity, not zeros. Four share components and the denominator are exported.

Positive flow supports **that particular market's YES outcome**. Never add flows for “no change” and “25 bps decrease” as though YES had the same policy meaning. Participant notional is not market-wide volume. Flows are not holdings, private beliefs, probabilities or PnL. Shared transaction hashes can span multiple records/markets/wallets and are not fill IDs.

## Teammate loading example

```python
from pathlib import Path
import pandas as pd

pilot = Path("datasets/polymarket/wallet_cluster_pilot/fed_20260531_v1")
signals = pd.read_csv(pilot / "daily_cluster_signals.csv",
    dtype={{"event_id": "string", "market_id": "string", "cluster_id": "string"}},
    parse_dates=["asof_utc"])
signals = signals.loc[signals["forecast_input_allowed"] & signals["coverage_complete"]]
wide = signals.pivot(index=["asof_utc", "event_id", "market_id"],
    columns="cluster_id", values=["aggregate_directional_imbalance",
                                 "equal_weight_directional_imbalance",
                                 "active_wallet_count"])
# Keep undefined ratios missing; do not blanket-fill the table with zeros.
```

The probability-adjustment team combines these signals with matching market probability observations. The direct stock-prediction team aggregates/pivots the same signals while retaining outcome and event identity. Both need their own past-only training and later tests. No model has been trained here to adjust probabilities or forecast SPY. The current 17 daily timestamps and one target meeting support integration, not a robust performance study. Confirm quote availability and the stock forecast time before joining to stock targets; a date label alone does not prove intraday alignment.

## Reproduce from the repository root

```sh
/opt/homebrew/bin/python3.13 -m venv .venv-wallet-pilot
.venv-wallet-pilot/bin/python -m pip install -r datasets/polymarket/wallet_cluster_pilot/fed_20260531_v1/requirements.lock.txt
.venv-wallet-pilot/bin/python scripts/polymarket/run_wallet_cluster_pilot.py --stage build
.venv-wallet-pilot/bin/python -m unittest discover -s tests -p 'test_wallet_cluster_*.py' -v
```

Use a compatible Python3.13 installation on your own machine; the absolute setup path above is this machine's interpreter. `--stage build` is offline and uses the frozen trade exports plus unchanged original June files, checked against hashes. The saved pipeline can be loaded with joblib and its compatible dependencies. Load the 30-feature table, retain eligible rows, and call pipeline.predict; numeric labels 0/1 correspond to C0/C1.

`--stage collect` resumes raw pages from the ignored `tmp/polymarket/wallet_cluster_pilot/fed_20260531_v1/` cache and rewrites collected outputs. `--stage all` collects then builds. A fresh raw cache can produce revised retrospective API records; use a new output/cache directory for an independent acquisition. Default budget: 1 hour, 4 workers. Saved pages are reused; failed/truncated queries stay incomplete. Existing source exports are never overwritten.

Build reproducibility applies to the selected cohort, features, memberships and daily CSVs given frozen inputs. Acquisition times and binary/chart metadata are not claims of byte-identical fresh network runs. Output SHA256 hashes support integrity checks.

## Validation and next step

`report.json` records strict cutoff checks, midnight timestamps, unique panel keys, independent raw-to-feature and raw-to-daily count/share/notional reconciliation, four-direction identities and bounded imbalances. Focused tests cover inclusive/exclusive boundaries, query pagination/resume, incomplete coverage, zero denominators, label exclusion, duplicate diagnostics and saved-model round trips.

Expand historical wallet coverage or recruit a larger predefined sample to obtain more eligible multi-meeting histories. Preserve this pilot and its rules. A later rolling-cutoff dataset is needed for historical backtests; do not use the earlier descriptive panel as out-of-sample evidence.
'''
    (output / "README.md").write_text(guide)


def run(args):
    root = args.root.resolve()
    output = (args.output or root / "datasets/polymarket/wallet_cluster_pilot/fed_20260531_v1").resolve()
    cache = (args.cache or root / "tmp/polymarket/wallet_cluster_pilot/fed_20260531_v1").resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text())
    if args.stage in {"collect", "all"}:
        cohort = select_cohort(root, config)
        if (output / "config.json").exists() and json.loads((output / "config.json").read_text()) != config:
            raise ValueError("Output configuration differs; use another output directory")
        atomic_json(output / "config.json", config)
        atomic_json(output / "source_hashes.json", source_hashes(root))
        write_rows(output / "cohort.csv", cohort)
        print(f"Selected {len(cohort)} wallets; collecting bounded history", flush=True)
        trades, coverage, mapping = collect_history(root, config, cohort, output, cache)
        write_rows(output / "historical_trades.csv.gz", trades)
        write_rows(output / "history_coverage.csv", coverage)
        write_rows(output / "market_map.csv", mapping)
        print((output / "collection_report.json").read_text(), flush=True)
    if args.stage == "collect":
        return
    frozen = json.loads((output / "config.json").read_text())
    if frozen != config:
        raise ValueError("Build config differs from frozen collection config")
    if json.loads((output / "source_hashes.json").read_text()) != source_hashes(root):
        raise ValueError("Source exports changed since collection")
    cohort = read_rows(output / "cohort.csv")
    trades = read_rows(output / "historical_trades.csv.gz")
    coverage = read_rows(output / "history_coverage.csv")
    mapping = read_rows(output / "market_map.csv")
    import pandas as pd
    from wallet_cluster_features import build_features, fit_clusters
    from wallet_cluster_daily import build_daily
    features = build_features(cohort, trades, coverage, mapping, config)
    cluster = fit_clusters(features, config, output)
    features.to_csv(output / "wallet_features.csv", index=False, float_format="%.12g")
    cluster["memberships"].to_csv(output / "cluster_membership.csv", index=False, float_format="%.12g")
    cluster["profiles"].to_csv(output / "cluster_profiles.csv", index=False, float_format="%.12g")
    cluster["diagnostics"].to_csv(output / "clustering_diagnostics.csv", index=False, float_format="%.12g")
    daily = build_daily(cohort, cluster["memberships"], trades, mapping, root, config)
    for key, filename in (("signals", "daily_cluster_signals.csv"), ("historical", "historical_cluster_activity.csv"), ("coverage", "target_coverage.csv")):
        daily[key].to_csv(output / filename, index=False, float_format="%.12g")
    target = daily["target_trades"].to_dict("records")
    # Source prefixes distinguish local June exports from new historical queries.
    write_rows(output / "trades.csv.gz", trades + target)
    checks = validate(features, cluster["memberships"], daily, config, trades, mapping)
    dependencies = {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scikit-learn", "scipy", "matplotlib", "joblib")}
    lock = subprocess.check_output([sys.executable, "-m", "pip", "--disable-pip-version-check", "--no-cache-dir", "freeze"], text=True)
    (output / "requirements.lock.txt").write_text(lock)
    fields = {name: [dict(name=column, dtype=str(dtype)) for column, dtype in frame.dtypes.items()]
              for name, frame in (("cohort.csv", pd.DataFrame(cohort)), ("wallet_features.csv", features), ("cluster_membership.csv", cluster["memberships"]),
                                  ("cluster_profiles.csv", cluster["profiles"]), ("daily_cluster_signals.csv", daily["signals"]),
                                  ("historical_cluster_activity.csv", daily["historical"]), ("history_coverage.csv", pd.DataFrame(coverage)),
                                  ("target_coverage.csv", daily["coverage"]), ("market_map.csv", pd.DataFrame(mapping)),
                                  ("clustering_diagnostics.csv", cluster["diagnostics"]), ("trades.csv.gz", pd.DataFrame(trades + target))) }
    atomic_json(output / "schema.json", {
        "identifiers": "Read wallet, token, market, condition, transaction, event and cluster IDs as strings; never parse token IDs as floating point",
        "timestamps": "ISO8601 UTC; all interval end bounds are exclusive",
        "nulls": "Empty CSV fields represent missing values; complete empty activity has zero counts and sums, but undefined ratios remain missing",
        "numerics": "Trade shares, price, notional and signed share fields retain source decimal strings. Derived features and signals use floating point. dtype describes the in-memory build frame, not enforced CSV typing.",
        "primary_keys": {"cohort.csv": ["snapshot_id", "wallet_address"], "wallet_features.csv": ["snapshot_id", "wallet_address"],
                         "cluster_membership.csv": ["model_version", "wallet_address"],
                         "daily_cluster_signals.csv": ["asof_utc", "event_id", "market_id", "cluster_id", "model_version"],
                         "historical_cluster_activity.csv": ["asof_utc", "event_id", "market_id", "cluster_id", "model_version"],
                         "market_map.csv": ["event_id", "market_id", "token_id"],
                         "trades.csv.gz": ["source_snapshot_id", "source_query", "source_page", "source_row"]},
        "daily_field_notes": {
            "asof_utc": "Signal information cutoff; the 24-hour interval ends immediately before this instant",
            "cluster_member_count": "Assigned wallets in the frozen cluster, including those with no activity that day",
            "active_wallet_count": "Assigned wallets with at least one served participant record in this market/interval",
            "unique_transactions": "Distinct settlement hashes within this market/cluster/interval; not additive across markets or clusters",
            "gross_shares": "Sum of shares across all participant records",
            "gross_participant_notional_usd": "Sum of shares times price, excluding fees; not market-wide volume",
            "aggregate_directional_imbalance": "Signed YES-directed flow / gross shares; missing when gross shares are zero",
            "equal_weight_directional_imbalance": "Mean of each active wallet's signed YES-directed flow / gross shares",
            "largest_wallet_notional_fraction": "Largest wallet participant notional / cluster participant notional; undefined at zero notional",
            "coverage_complete": "All assigned wallets covered by the served source export for this market, not full-chain completeness",
            "forecast_input_allowed": "Structural retrospective eligibility only; contemporaneous source availability remains unverified"},
        "tables": fields})
    report = {"snapshot_id": config["snapshot_id"], "configuration": config,
              "collection": json.loads((output / "collection_report.json").read_text()),
              "features": {"wallet_rows": len(features), "behavioural_feature_count": 30,
                           "pre_decision_participant_rows": int(features.participant_rows.sum()),
                           "wallets_with_zero_observed_history": int(features.events_traded.eq(0).sum()),
                           "events_traded_distribution": {str(key): int(value) for key, value in features.events_traded.value_counts().sort_index().items()},
                           "ineligibility_reason_counts_nonexclusive": dict(Counter(reason for status in features.eligibility_status
                                                                                  for reason in status.split(";") if reason != "eligible"))},
              "clustering": cluster["report"], "daily": daily["report"], "checks": checks,
              "runtime": {"python": platform.python_version(), "dependencies": dependencies},
              "limitations": ["Retrospective timestamp-filtered pilot; contemporaneous API availability unverified.",
                              "June-discovered cohort; earlier panels are descriptive, not historical out-of-sample forecasts.",
                              "Pre-decision cutoff approximates Gamma endDate minus 24 hours.",
                              "Participant trade flow is not holdings, profit, a private belief or market-wide volume.",
                              "API completion is not full-chain completeness; 0.01-share size floor applies.",
                              "No predictive-value or smart-wallet claim is established."]}
    atomic_json(output / "report.json", report)
    shutil.copyfile(Path(__file__).with_name("wallet_cluster_feature_dictionary.json"), output / "feature_dictionary.json")
    implementation = [Path(__file__), *Path(__file__).parent.glob("wallet_cluster_*.py"),
                      Path(__file__).with_name("wallet_cluster_config.json"), Path(__file__).with_name("wallet_cluster_feature_dictionary.json"),
                      Path(__file__).with_name("collect_pilot.py"), Path(__file__).with_name("collect_history.py")]
    atomic_json(output / "implementation_hashes.json", {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                                       for path in sorted(set(implementation))})
    write_readme(output, report)
    checksums = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output)}"
                 for path in sorted(output.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"]
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("wallet_cluster_config.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--stage", choices=("collect", "build", "all"), default="all")
    run(parser.parse_args())
