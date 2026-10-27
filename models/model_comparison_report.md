# EventLens model comparison report

## 1. Purpose

This report compares the exploratory SPY forecasting models tested in the
playground experiment. The experiment asks two related questions:

1. Can the available information predict SPY's future cumulative return?
2. Can it predict how much SPY will move, measured as future realized variance?

The experiment is a baseline investigation. It is not investment advice and it
does not yet establish a causal relationship between prediction-market
probabilities and SPY returns.

The complete run is recorded in
[`playground_experiment_results.csv`](./playground_experiment_results.csv).
The experiment code is
[`playground_experiments.py`](./playground_experiments.py), and the annotated
playground is
[`model_experiments_playground.ipynb`](./model_experiments_playground.ipynb).

## 2. Data and prediction setup

The experiment used:

- **SPY market data:** daily close prices and daily returns from
  [`index_daily.csv`](../datasets/index_daily.csv).
- **Prediction-market data:** probabilities for possible Federal Reserve
  interest-rate outcomes from
  [`forward_probabilities.csv`](../datasets/forward_probabilities.csv).

The prediction date is the end of trading day \(t\). Features use information
available on or before \(t\). The target starts on the next trading day.

The tested horizons are:

- **1 day:** the next trading day's cumulative return or squared return;
- **5 days:** cumulative return or sum of five future squared returns;
- **20 days:** cumulative return or sum of twenty future squared returns.

For 5-day and 20-day horizons, forecast origins are spaced by the horizon.
This avoids counting heavily overlapping future windows as separate tests.
The first 70% of the chronological observations are used for training and the
last 30% are used as the holdout test period.

There are many daily snapshots but only about **27 selected Federal Reserve
event IDs**. Therefore, the effective independent sample is much smaller than
the raw row count. The 20-day holdout contains only **15 test cases**.

## 3. Inputs used by the models

### 3.1 History features

The history feature set contains:

| Input | Meaning |
|---|---|
| `history_return_1d` | The previous trading day's SPY return |
| `history_return_5d` | Mean SPY return over the previous five trading days |
| `history_return_20d` | Mean SPY return over the previous twenty trading days |
| `history_variance_5d` | Mean squared SPY return over the previous five days |
| `history_variance_20d` | Mean squared SPY return over the previous twenty days |

These features answer: **what has SPY been doing recently?**

### 3.2 Event features

The event feature set contains:

| Input | Meaning |
|---|---|
| `expected_move` | Probability-weighted signed rate change |
| `expected_abs_move` | Expected size of rate change, ignoring direction |
| `move_variance` | Uncertainty about the possible rate movement |
| `entropy` | Uncertainty across the complete probability distribution |
| `max_probability` | Probability of the most likely outcome |
| `probability_increase` | Total probability assigned to rate increases |
| `probability_decrease` | Total probability assigned to rate decreases |
| `probability_no_change` | Total probability assigned to no change |
| `expected_move_change` | Change in expected rate movement |
| `max_probability_change` | Change in the most likely-outcome probability |
| `horizon_month` | Months until the selected meeting |
| `outcome_count` | Number of available outcomes in the snapshot |

These features answer: **what does the prediction market currently expect, and
how uncertain is it?**

### 3.3 Feature sets compared

| Feature set | Inputs | Purpose |
|---|---|---|
| History-only | History features | Required market-history benchmark |
| Event-only | Event features | Tests whether event information alone has signal |
| History-plus-event | Both sets | Tests whether events add information beyond SPY history |

The event-only model was tested for return prediction. It was not used as the
main variance comparison because a volatility forecast needs at least a market
history reference to be meaningful for this first experiment.

## 4. Model families tested

| Model | What it does | Why it was included | Main weakness |
|---|---|---|---|
| Ridge, alpha 0.01 | Linear regression with light coefficient shrinkage | Transparent linear baseline | Still assumes a linear relationship |
| Ridge, alpha 1 | Linear regression with moderate shrinkage | Main regularized baseline | Can underfit if the relationship is nonlinear |
| Ridge, alpha 100 | Strongly shrunk linear regression | Tests whether aggressive regularization helps small data | May remove useful signal |
| Elastic Net | Linear regression with both shrinkage and feature selection | Can reduce redundant features | Sensitive to tuning and correlated variables |
| RBF SVR | Nonlinear kernel regression | Tests smooth nonlinear relationships | Needs tuning; difficult to interpret; can overfit |
| Random Forest | Many decision trees averaged together | Tests nonlinear feature interactions | Can overfit repeated event snapshots; less smooth for tiny samples |
| Extra Trees | More randomized tree ensemble | Tests another nonlinear tree approach | Can find accidental patterns in a small holdout |
| Gradient Boosting | Sequential trees that correct earlier errors | Tests nonlinear predictive structure | Sensitive to tuning and holdout selection |
| Histogram Gradient Boosting | Efficient regularized boosting | Additional nonlinear benchmark | Still data-hungry relative to independent event count |

All models use the same chronological split and the same target definition for
a fair comparison. Variance models were also fit on a **log-transformed
target**. This forces fitted variance predictions to be positive after
transforming them back and tests whether the raw variance scale is poorly
behaved.

## 5. Metrics used

All metrics are calculated on the unseen chronological holdout.

- **MAE:** average absolute error. Lower is better. It is easy to interpret and
  is less dominated by a few extreme observations.
- **RMSE:** square root of average squared error. Lower is better. It penalizes
  very large mistakes more heavily and is the main comparison metric here.
- **R²:** compares the model with a constant-average prediction. An R² of zero
  means no improvement over that simple reference; a negative R² means the
  model is worse than it.
- **QLIKE:** a loss for non-negative variance forecasts. Lower is better. It
  penalizes underestimating variance strongly and is not used to compare return
  models.
- **Negative prediction rate:** acceptable for return models because returns
  can be negative. It is a warning for variance models because variance cannot
  be negative.
- **Test rows:** the number of held-out cases. Results with 15 cases are much
  less reliable than results with 286 cases.

Metrics must be compared only within the same target and horizon. A 1-day
return RMSE cannot be directly compared with a 20-day return RMSE.

## 6. Best results by target and horizon

The following table gives the best RMSE configuration found among the tested
models. It is a **model-search summary**, not an unbiased final estimate,
because many configurations were tried on the same holdout.

| Target | Horizon | Best feature set | Best model | Log target? | RMSE | R² | Test rows |
|---|---:|---|---|---|---:|---:|---:|
| Return | 1 day | Event-only | Elastic Net | No | 0.007730 | 0.034 | 286 |
| Return | 5 days | Event-only | Random Forest | No | 0.016764 | 0.008 | 57 |
| Return | 20 days | Event-only | Gradient Boosting | No | 0.040077 | 0.043 | 15 |
| Variance | 1 day | History-only | Extra Trees | No | 0.000109 | 0.003 | 286 |
| Variance | 5 days | History-only | Extra Trees | Yes | 0.000203 | 0.247 | 57 |
| Variance | 20 days | History-plus-event | Ridge, alpha 100 | Yes | 0.000536 | 0.197 | 15 |

### Important reading of this table

The event-only return models performed best in the model search for all three
return horizons. This is interesting evidence that the event probability
features may contain information about future SPY returns.

However, it is not yet a reliable conclusion because:

1. 189 configurations were tried;
2. all configurations used the same holdout period;
3. only 15 observations were tested for the 20-day return result;
4. flexible models can find accidental patterns in a small test period;
5. event snapshots are repeated observations around the same meetings.

The 5-day volatility result has the highest R² in the experiment:

```text
R² = 0.247
```

It uses history-only Extra Trees with a log variance target and 57 test cases.
This is the strongest numerical result, but it does not show that event
features helped. It shows that a nonlinear model and a positive log target may
represent recent volatility better than the first Ridge setup.

## 7. History-plus-event versus history-only

This comparison directly tests the project question: **do event features add
value beyond recent SPY history?**

| Target | Horizon | Best history-only RMSE | Best history-plus-event RMSE | Change |
|---|---:|---:|---:|---:|
| Return | 1 day | 0.007860 | 0.007730 | 1.66% better |
| Return | 5 days | 0.016867 | 0.017083 | 1.28% worse |
| Return | 20 days | 0.041038 | 0.041030 | 0.02% better |
| Variance | 1 day | 0.000109 | 0.000113 | 3.12% worse |
| Variance | 5 days | 0.000203 | 0.000208 | 2.04% worse |
| Variance | 20 days | 0.000557 | 0.000536 | 3.65% better |

The improvements are small and inconsistent. Event features do not reliably
improve the combined model, even though event-only models sometimes perform
well.

## 8. Possible explanations for the observations

### 8.1 Event-only return models sometimes win

Possible explanations:

- The prediction-market data contains information that is not present in the
  short history features.
- Event probabilities may identify broad market regimes, such as calm or
  uncertain policy periods.
- Event features may be better aligned with medium-term return behaviour than
  with one-day volatility.
- The result may be chance from searching many models.

The positive interpretation is plausible, but it must be tested with
event-blocked and walk-forward validation before being accepted.

### 8.2 Adding history can make the event model worse

This can happen when:

- the history features add noise for a particular horizon;
- event and history features contain overlapping information;
- the combined model has more opportunities to overfit;
- regularization is not perfectly tuned for the expanded feature set.

It does not necessarily mean history is useless. It means the extra history
features did not improve that particular holdout prediction.

### 8.3 History-only models often beat combined volatility models

Recent squared returns are a direct measure of recent volatility. The current
event features describe possible Federal Reserve outcomes, but they do not
directly describe all causes of daily price movement. They may therefore be
less useful for variance than recent market volatility itself.

### 8.4 Log-variance models behave better

Variance is non-negative and often skewed, while ordinary regression on the raw
variance scale can produce negative predictions. Predicting log variance makes
the target easier to model and avoids negative fitted values after reversing the
transformation.

This is a modelling improvement, not evidence that event features are useful.

### 8.5 Strong collinearity is present

The diagnostics show:

- largest absolute feature correlation: approximately **0.958**;
- feature-matrix condition number: approximately **5.4 × 10^15**;
- selected independent event IDs: approximately **27**.

This is strong evidence that the feature set contains redundant information
and that the effective sample is small. Ridge and Elastic Net reduce the
damage, but they cannot create independent information.

### 8.6 Many daily rows do not mean many independent observations

The same meeting can appear in the probability data on many dates. The model
may therefore see repeated versions of one event during training and testing.
This can make a result look more certain than it really is.

### 8.7 Raw probability may be less useful than surprise

Market prices already reflect expectations. SPY may react more strongly to:

```text
actual rate decision - expected rate decision
```

The current features mostly describe expectations and uncertainty. A later
experiment should explicitly construct announcement-surprise features.

## 9. Overall conclusion

The experiment found preliminary evidence that event probability features can
sometimes predict SPY returns, especially in event-only models. It also found
that history-plus-event models do not consistently beat history-only models.
For volatility, the strongest result came from a history-only nonlinear model
with a log variance target; the history-plus-event improvement appeared only
at 20 days and was based on 15 test cases.

The most likely explanation is a combination of:

- some genuine event information;
- high feature collinearity;
- few independent Federal Reserve events;
- repeated daily snapshots;
- model-search selection bias;
- timing mismatch between a meeting probability and the forecast horizon;
- missing market drivers such as earnings, inflation, yields, and geopolitical
  news.

The correct current claim is:

> Event features are promising enough to investigate further, but the current
> experiment does not yet prove reliable incremental predictive value.

## 10. Recommended next validation

Before selecting a final model or claiming that event probabilities improve
performance:

1. Freeze a small set of models before evaluation.
2. Use walk-forward validation rather than one holdout split.
3. Hold out complete Federal Reserve events, not just individual daily rows.
4. Report uncertainty across folds/events.
5. Reduce or group highly collinear features.
6. Add event-surprise and days-to-meeting features.
7. Test smart-wallet features against the same history-only and event-only
   baselines.
