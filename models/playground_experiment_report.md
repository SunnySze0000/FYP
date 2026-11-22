# Playground experiment log

This file records the broad model comparison run on the committed SPY and
prediction-market data. The test period is chronological (last 30%), and
multi-day origins are sampled every H trading days to avoid overlapping
targets. These are exploratory results, not final evidence.

## Data and diagnostics

- Market rows after cleaning: 908
- Unique selected event IDs: 27
- Feature count in the full feature set: 17
- Largest absolute feature correlation: 0.9667
- Feature matrix condition number: 5743001782833231.00

A high pairwise correlation or condition number indicates collinearity.
The event rows are daily snapshots, so unique events are a better measure
of independent information than the raw row count.

## Best models by target and horizon

- **return, 1d:** `elastic_net` + `event_only` + log=False (RMSE 0.0078824048, R2 0.0127, test rows 273)
- **return, 5d:** `random_forest` + `history_plus_event` + log=False (RMSE 0.016409472, R2 0.0438, test rows 55)
- **return, 20d:** `gradient_boosting` + `history_plus_event` + log=False (RMSE 0.024840166, R2 0.3273, test rows 14)
- **variance, 1d:** `gradient_boosting` + `history_only` + log=False (RMSE 0.00010775356, R2 0.0588, test rows 273)
- **variance, 5d:** `extra_trees` + `history_only` + log=True (RMSE 0.0002384361, R2 0.1324, test rows 55)
- **variance, 20d:** `ridge_alpha_0.01` + `history_only` + log=True (RMSE 0.00049113691, R2 0.3277, test rows 14)

## History-plus-event versus history-only

- **return, 1d:** best history-only `elastic_net` RMSE 0.0079334452; best combined `elastic_net` RMSE 0.0078882359; combined improved by 0.57%.
- **return, 5d:** best history-only `extra_trees` RMSE 0.016492592; best combined `random_forest` RMSE 0.016409472; combined improved by 0.50%.
- **return, 20d:** best history-only `random_forest` RMSE 0.026245322; best combined `gradient_boosting` RMSE 0.024840166; combined improved by 5.35%.
- **variance, 1d:** best history-only `gradient_boosting` RMSE 0.00010775356; best combined `gradient_boosting` RMSE 0.00011207129; combined worsened by 4.01%.
- **variance, 5d:** best history-only `extra_trees` RMSE 0.0002384361; best combined `extra_trees` RMSE 0.00024237037; combined worsened by 1.65%.
- **variance, 20d:** best history-only `ridge_alpha_0.01` RMSE 0.00049113691; best combined `hist_gradient_boosting` RMSE 0.00059927787; combined worsened by 22.02%.

## Interpretation rules

- Compare history-plus-event with history-only at the same target and horizon.
- A lower RMSE on one 15-row 20-day test is weak evidence.
- If many complex models win only on the same small holdout, selection bias is possible.
- If Ridge and tree models agree across horizons, the result is more credible.
- If event features help only after log transformation, the original variance scale may be misspecified.
- Better fit alone is not enough: event-blocked and walk-forward validation are still required.

## Full run

Every attempted configuration is recorded in `playground_experiment_results.csv`.
