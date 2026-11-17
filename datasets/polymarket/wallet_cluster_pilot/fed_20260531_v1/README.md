# Frozen Fed-wallet clustering pilot

## Result

Selected **150 wallets**; completed all their four-meeting API queries; accepted **27,618 historical participant records** with **0 rejected**.
**37 wallets were clustered**, not 150. The other wallets retain explicit unassigned statuses and eligibility reasons. Final status: **provisional**. This is a reduced-cohort integration pilot, not evidence of predictive value or wallet skill.

- **C0 (30 wallets):** lower median event top market fraction; lower busiest day transaction fraction; higher active days relative to the eligible cohort.
- **C1 (7 wallets):** higher busiest day transaction fraction; lower two sided token fraction; higher median event top market fraction relative to the eligible cohort.

The export contains **30 behavioural features for every selected wallet**, memberships, feature distributions, representative wallets, and four diagnostic charts. Undefined features are missing. Incomplete history never becomes zero activity.

Daily prediction-input panel: **170 rows**, from **2026-05-31T00:00:00+00:00** through **2026-06-16T00:00:00+00:00**, across five June policy-outcome markets. Only assigned wallets contribute to cluster signals; **113 selected wallets are excluded**. Earlier descriptive panel: **2552 rows**.

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
    dtype={"event_id": "string", "market_id": "string", "cluster_id": "string"},
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
