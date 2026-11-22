# Baseline forecasting models

The main notebook is [`forecast_models.ipynb`](./forecast_models.ipynb). The
standalone version is [`forecast_models.py`](./forecast_models.py). Both follow
five clearly annotated stages:

1. get data;
2. extract features;
3. analyze correlations;
4. fit models;
5. compare models.

The notebook is
the preferred place for the team's annotated experiments and compares five
models for SPY at 1-, 5-, and 20-trading-day horizons:

1. SPY history -> cumulative future return;
2. event features only -> cumulative future return;
3. SPY history + event features -> cumulative future return;
4. SPY history -> future realized variance;
5. SPY history + event features -> future realized variance.

The notebook also reports exploratory Spearman correlations between event
features and future returns. Correlation is not treated as proof of predictive
value; the chronological held-out results are the main comparison.

Both event models use point-in-time prediction-market information. They do not
use `final_outcome`, which is only known after a meeting resolves. The event
features include:

- expected rate move and expected absolute move;
- probability-weighted uncertainty of the rate move;
- entropy and maximum outcome probability;
- separate probability of an increase, decrease, and no change;
- changes in expected move and probability concentration;
- meeting horizon and number of available outcomes.

The first estimator is a standardized Ridge regression. It is intentionally
simple and interpretable, while shrinking correlated coefficients in the small
sample. More complex models should only be introduced after the time alignment
and event-grouped validation are stable.

Run the standalone version from the repository root:

```text
python models\forecast_models.py
```

It prints the feature/return correlations and held-out metrics, and writes
`models/forecast_model_results.csv` and
`models/feature_return_correlations.csv`.

## Model weaknesses

- **History-only return:** ignores events and other news; recent returns may
  not persist. It is still the essential benchmark.
- **Event-only return:** event probabilities do not describe all daily market
  drivers, and the number of independent rate events is small. It may also
  produce unstable return predictions when event features are correlated.
- **History-plus-event return:** adds potentially useful information, but
  increases the feature-to-sample ratio and can overfit repeated snapshots of
  the same event.
- **History-only variance:** variance is noisy and always non-negative, while
  ordinary linear regression can predict negative values. Log-target or
  non-negative models are possible follow-ups.
- **History-plus-event variance:** has all history-only variance weaknesses plus
  collinearity and the risk that event probabilities are related to volatility
  without improving an out-of-sample forecast.

All models share the small-data limitation. Daily rows around one event are not
fully independent, and one chronological holdout is uncertain. Results should
not be treated as causal evidence or as investment advice.

## Metrics and implications

The comparison uses only the later chronological holdout:

- **MAE:** average absolute prediction error; lower is better.
- **RMSE:** error metric that penalizes very large mistakes more than MAE;
  lower is better.
- **R2:** comparison with a constant-average prediction. Zero means no
  improvement over that reference; negative means the model is worse.
- **QLIKE:** variance-specific loss that strongly penalizes underestimating
  variance; lower is better. It is not used for return models.
- **Negative prediction rate:** acceptable for returns, but a warning for
  variance because variance cannot be negative.
- **Rows:** the number of held-out cases. The 20-day test has only 15 rows, so
  its result is especially uncertain.

Current implication (rerun after the outcome-label and stale-snapshot fixes
described below): history-only is best for 1-day and 5-day return RMSE and for
all variance horizons. History-plus-event is slightly best for 20-day return
RMSE, but on only 14 test cases. These results do not prove that event
features are useless; they show that this first feature set and small,
event-clustered sample have not yet demonstrated reliable incremental value.
More independent events, walk-forward testing, and wallet-cluster features
are needed (see [`cluster_regression.py`](./cluster_regression.py)).

### Data-handling fixes (feature/cluster-implied-probabilities)

- **`25+ bps increase` now maps to +25 bp**, the lower bound of the bucket,
  instead of +50 bp. All labels pass through [`outcomes.py`](./outcomes.py),
  which also normalises capitalization (`No change` vs `no change`).
- **Event snapshots are no longer carried forward indefinitely.** Features are
  joined with a 7-day tolerance (`EVENT_MERGE_TOLERANCE`). Previously, for
  example, the 2025-01-29 meeting-day snapshot was reused for 29 trading days
  up to 2025-03-19; 46 such stale rows are now dropped.
- Result CSVs and `event_walk_forward_report.md` were regenerated. The two
  notebooks still show outputs from before the fix until they are rerun.

## Script baseline

`baseline_model.py` remains a lightweight, dependency-minimal volatility-only
reference. It forecasts SPY realized variance over 1, 5, and 20 trading days:

- **Recent-return baseline:** OLS using the mean squared return over the
  previous 20 trading days.
- **Event-augmented model:** the same input plus the nearest available
  prediction-market meeting's expected rate move, maximum normalized outcome
  probability, and probability entropy.

The target uses the next `H` trading-day returns (starting on the trading day
after the forecast date). Forecast origins are sampled every `H` days
so multi-day targets do not overlap. The first 70% of each chronological
series is used for fitting and the remaining 30% is held out.

Predictions are evaluated after applying the fixed positive floor
`1e-8` required by QLIKE; the negative-prediction rate is also reported so an
invalid unconstrained OLS forecast is visible rather than silently hidden.

Run from the repository root:

```text
python models/baseline_model.py
```

The script writes `models/baseline_results.csv` and reports MSE and QLIKE.
This is a baseline, not evidence that prediction-market features improve
forecasting; the small sample, repeated daily market snapshots, and event
clustering require stronger walk-forward and event-grouped tests later.

## Broad experiment playground

[`model_experiments_playground.ipynb`](./model_experiments_playground.ipynb) and
[`playground_experiments.py`](./playground_experiments.py) try several
regularized linear, kernel, tree, and boosting models:

- Ridge with three penalty strengths;
- Elastic Net;
- RBF SVR;
- Random Forest;
- Extra Trees;
- Gradient Boosting;
- Histogram Gradient Boosting.

They test history-only, event-only return, and history-plus-event feature sets.
Variance is tested on both the original and log-transformed target scales.
Every attempted configuration is recorded in
`playground_experiment_results.csv`; diagnostics are in
`playground_diagnostics.csv`; and the written interpretation is in
`playground_experiment_report.md`.

## Wallet-cluster probability features (N x M)

[`cluster_regression.py`](./cluster_regression.py) adds wallet-cluster inputs to
the SPY return/variance models. It is split into replaceable stages:

| Stage | Module | Responsibility |
|---|---|---|
| Cluster probability | [`scripts/polymarket/cluster_implied_probability.py`](../scripts/polymarket/cluster_implied_probability.py) | Turn member trading flow into each cluster's probability per outcome and day |
| M features | [`distribution_features.py`](./distribution_features.py) | Summarize a distribution, or compare it with the market; shared with `extract_event_features` |
| Skill (optional) | [`scripts/polymarket/wallet_skill.py`](../scripts/polymarket/wallet_skill.py) | Past-only flow-alignment scores, used as a member filter or weight |
| Regression | `cluster_regression.py` | Pivot to N x M, join SPY targets, event walk-forward |

**Why a centroid needs a definition.** A KMeans centroid is a point in
behaviour space and does not trade. A cluster's probability is built from its
members' trades in a trailing window (default 7 days, strictly before the as-of
time and the decision cutoff): per-owner YES imbalance, averaged across owners,
applied as a log-odds shift to the market probability and shrunk toward the
market when few owners are active. A silent cluster equals the market rather
than NaN.

**Membership input is method-agnostic.** Any table with `wallet_address` and
`cluster_id` works. Add `entity_id` for same-owner (sniper) groups, so one owner
counts once, and `weight` for skill or centroid closeness. Hard-rule filtering
is applied by simply dropping rows before this step.

**M features per cluster** (`--feature-mode`):

- `summary` (default, M = 4): `expected_move_gap`, `move_std_gap`,
  `tail_probability_gap`, `kl_from_market`. These measure the cluster's
  *disagreement* with the market. Raw levels would mostly duplicate the market
  event features already in the model.
- `levels` (M = 4): expected move, move std, normalized entropy, max probability.
- `per_outcome`: one probability gap per outcome.

Memberships from the wallet pipeline
(`scripts/polymarket/wallet_pipeline/run.py`) plug in directly; their
`entity_id` column nets same-owner wallets:

```text
python models/cluster_regression.py --memberships datasets/polymarket/wallet_pipeline/fed_20260531_v2/memberships.csv.gz --output models/cluster_regression_v2
python models/cluster_regression.py                     # pilot clusters, summary, no skill
python models/cluster_regression.py --skill weight      # or --skill filter
python models/cluster_regression.py --feature-mode per_outcome --beta 1
```

Outputs go to [`cluster_regression/`](./cluster_regression/README.md) (pilot,
N = 2) and [`cluster_regression_v2/`](./cluster_regression_v2/README.md)
(wallet pipeline, N = 6, so N x M = 24: prefer a smaller M or fewer clusters
once a multi-meeting panel exists). With the current pilot (one meeting, 12 SPY trading days, N x M = 8) the walk-forward is
deliberately **not** run: it needs at least three meetings with cluster
features. The next data step is a rolling-cutoff panel: refit clusters at each
past meeting's cutoff using only earlier meetings, then rerun this script.
Choose `window`, `k`, `beta` and the feature mode on training meetings only.
