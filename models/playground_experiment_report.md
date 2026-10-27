# Playground experiment log

This file records the broad model comparison run on the committed SPY and
prediction-market data. The test period is chronological (last 30%), and
multi-day origins are sampled every H trading days to avoid overlapping
targets. These are exploratory results, not final evidence.

## Data and diagnostics

- Market rows after cleaning: 954
- Unique selected event IDs: 27
- Feature count in the full feature set: 17
- Largest absolute feature correlation: 0.9584
- Feature matrix condition number: 5410177931518126.00

A high pairwise correlation or condition number indicates collinearity.
The event rows are daily snapshots, so unique events are a better measure
of independent information than the raw row count.

## Best models by target and horizon

- **return, 1d:** `elastic_net` + `event_only` + log=False (RMSE 0.0077299817, R2 0.0337, test rows 286)
- **return, 5d:** `random_forest` + `event_only` + log=False (RMSE 0.016764485, R2 0.0080, test rows 57)
- **return, 20d:** `gradient_boosting` + `event_only` + log=False (RMSE 0.040077183, R2 0.0434, test rows 15)
- **variance, 1d:** `extra_trees` + `history_only` + log=False (RMSE 0.00010917183, R2 0.0035, test rows 286)
- **variance, 5d:** `extra_trees` + `history_only` + log=True (RMSE 0.0002034126, R2 0.2472, test rows 57)
- **variance, 20d:** `ridge_alpha_100` + `history_plus_event` + log=True (RMSE 0.00053649032, R2 0.1966, test rows 15)

## History-plus-event versus history-only

- **return, 1d:** best history-only `elastic_net` RMSE 0.0078603728; best combined `elastic_net` RMSE 0.0077299817; combined improved by 1.66%.
- **return, 5d:** best history-only `ridge_alpha_0.01` RMSE 0.016867413; best combined `random_forest` RMSE 0.017083408; combined worsened by 1.28%.
- **return, 20d:** best history-only `hist_gradient_boosting` RMSE 0.041037711; best combined `hist_gradient_boosting` RMSE 0.041030376; combined improved by 0.02%.
- **variance, 1d:** best history-only `extra_trees` RMSE 0.00010917183; best combined `svr_rbf` RMSE 0.00011258263; combined worsened by 3.12%.
- **variance, 5d:** best history-only `extra_trees` RMSE 0.0002034126; best combined `random_forest` RMSE 0.00020756502; combined worsened by 2.04%.
- **variance, 20d:** best history-only `ridge_alpha_100` RMSE 0.00055683378; best combined `ridge_alpha_100` RMSE 0.00053649032; combined improved by 3.65%.

## Interpretation rules

- Compare history-plus-event with history-only at the same target and horizon.
- A lower RMSE on one 15-row 20-day test is weak evidence.
- If many complex models win only on the same small holdout, selection bias is possible.
- If Ridge and tree models agree across horizons, the result is more credible.
- If event features help only after log transformation, the original variance scale may be misspecified.
- Better fit alone is not enough: event-blocked and walk-forward validation are still required.

## Full run

Every attempted configuration is recorded in `playground_experiment_results.csv`.
