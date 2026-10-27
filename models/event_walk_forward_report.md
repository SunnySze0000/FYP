# Event-level walk-forward validation

Each complete Federal Reserve event is held out in chronological order.
Training uses only earlier events. This is stricter than a daily random
or single-date holdout because repeated snapshots of one meeting stay in
the same event block.

- Minimum training events before a test: 10
- Test event blocks evaluated: 17
- Total scored fold/model rows: 720

## Aggregate results

### return, 1 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| return   |         1 | event_only         | elastic_net       |      17 |         629 |    0.008539 |      0.008913 |   0.006293 | -0.011302 |          nan |
| return   |         1 | history_plus_event | elastic_net       |      17 |         629 |    0.008542 |      0.008919 |   0.006299 | -0.011265 |          nan |
| return   |         1 | history_only       | elastic_net       |      17 |         629 |    0.008595 |      0.008981 |   0.006322 | -0.02062  |          nan |
| return   |         1 | history_only       | gradient_boosting |      17 |         629 |    0.008694 |      0.009085 |   0.006402 | -0.044568 |          nan |
| return   |         1 | history_plus_event | gradient_boosting |      17 |         629 |    0.008703 |      0.009106 |   0.006429 | -0.046415 |          nan |
| return   |         1 | history_only       | ridge             |      17 |         629 |    0.008687 |      0.009151 |   0.006434 | -0.032532 |          nan |
| return   |         1 | event_only         | gradient_boosting |      17 |         629 |    0.008766 |      0.009152 |   0.006503 | -0.07037  |          nan |
| return   |         1 | history_plus_event | ridge             |      17 |         629 |    0.009293 |      0.009991 |   0.006868 | -0.182583 |          nan |
| return   |         1 | event_only         | ridge             |      17 |         629 |    0.009301 |      0.010071 |   0.006814 | -0.208277 |          nan |

### return, 5 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| return   |         5 | history_only       | elastic_net       |      17 |         125 |    0.018794 |      0.020316 |   0.015399 | -0.241788 |          nan |
| return   |         5 | history_plus_event | elastic_net       |      17 |         125 |    0.018814 |      0.020335 |   0.015299 | -0.235996 |          nan |
| return   |         5 | event_only         | elastic_net       |      17 |         125 |    0.01875  |      0.020403 |   0.01519  | -0.223417 |          nan |
| return   |         5 | history_only       | gradient_boosting |      17 |         125 |    0.019129 |      0.020465 |   0.015736 | -0.361279 |          nan |
| return   |         5 | history_plus_event | gradient_boosting |      17 |         125 |    0.018974 |      0.020584 |   0.015438 | -0.290919 |          nan |
| return   |         5 | event_only         | gradient_boosting |      17 |         125 |    0.019105 |      0.020689 |   0.015306 | -0.3018   |          nan |
| return   |         5 | history_only       | ridge             |      17 |         125 |    0.019055 |      0.020704 |   0.015707 | -0.273969 |          nan |
| return   |         5 | history_plus_event | ridge             |      17 |         125 |    0.019664 |      0.021287 |   0.015978 | -0.360667 |          nan |
| return   |         5 | event_only         | ridge             |      17 |         125 |    0.019936 |      0.021829 |   0.01604  | -0.391271 |          nan |

### return, 20 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| return   |        20 | event_only         | gradient_boosting |      14 |          26 |    0.028546 |      0.038107 |   0.026198 |  -7.63955 |          nan |
| return   |        20 | history_plus_event | gradient_boosting |      14 |          26 |    0.030893 |      0.039257 |   0.028144 |  -7.18358 |          nan |
| return   |        20 | history_only       | gradient_boosting |      14 |          26 |    0.034399 |      0.041471 |   0.031117 |  -5.8381  |          nan |
| return   |        20 | history_plus_event | elastic_net       |      14 |          26 |    0.047957 |      0.062343 |   0.043426 | -15.7139  |          nan |
| return   |        20 | history_plus_event | ridge             |      14 |          26 |    0.048645 |      0.066939 |   0.045746 | -18.1075  |          nan |
| return   |        20 | event_only         | elastic_net       |      14 |          26 |    0.046274 |      0.082175 |   0.043878 |  -6.73362 |          nan |
| return   |        20 | event_only         | ridge             |      14 |          26 |    0.05101  |      0.09718  |   0.048588 |  -7.8212  |          nan |
| return   |        20 | history_only       | ridge             |      14 |          26 |    0.055231 |      0.103534 |   0.041895 | -18.7351  |          nan |
| return   |        20 | history_only       | elastic_net       |      14 |          26 |    0.056505 |      0.108375 |   0.04264  | -21.1938  |          nan |

### variance, 1 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| variance |         1 | history_only       | ridge             |      17 |         629 |    0.000191 |      0.000323 |   0.0001   | -0.467612 |    460.352   |
| variance |         1 | history_only       | gradient_boosting |      17 |         629 |    0.000179 |      0.000323 |   8.6e-05  | -0.055257 |      3.32615 |
| variance |         1 | history_plus_event | gradient_boosting |      17 |         629 |    0.000183 |      0.000326 |   8.9e-05  | -0.184082 |      1.58104 |
| variance |         1 | history_only       | elastic_net       |      17 |         629 |    0.000182 |      0.000327 |   9.4e-05  | -0.178804 |      1.74488 |
| variance |         1 | history_plus_event | elastic_net       |      17 |         629 |    0.000182 |      0.000327 |   9.4e-05  | -0.178969 |      1.74496 |
| variance |         1 | history_plus_event | ridge             |      17 |         629 |    0.000227 |      0.000368 |   0.000129 | -1.45503  |    452.429   |

### variance, 5 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| variance |         5 | history_only       | gradient_boosting |      17 |         125 |    0.000437 |      0.000845 |   0.000266 |  -2.08336 |     0.38757  |
| variance |         5 | history_plus_event | gradient_boosting |      17 |         125 |    0.000448 |      0.000858 |   0.000276 |  -2.1087  |     0.434435 |
| variance |         5 | history_plus_event | elastic_net       |      17 |         125 |    0.000466 |      0.000874 |   0.000303 |  -4.14758 |     0.536729 |
| variance |         5 | history_only       | elastic_net       |      17 |         125 |    0.000466 |      0.000874 |   0.000303 |  -4.26938 |     0.537004 |
| variance |         5 | history_only       | ridge             |      17 |         125 |    0.000533 |      0.00088  |   0.000358 |  -4.79802 |  1412.49     |
| variance |         5 | history_plus_event | ridge             |      17 |         125 |    0.000647 |      0.000958 |   0.000469 |  -8.10768 |  2739.44     |

### variance, 20 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |    mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|-----------:|-------------:|
| variance |        20 | history_plus_event | gradient_boosting |      14 |          26 |    0.001572 |      0.003106 |   0.001245 |   -43.8515 |     0.419861 |
| variance |        20 | history_only       | gradient_boosting |      14 |          26 |    0.001634 |      0.003153 |   0.00129  |   -97.3399 |     0.395607 |
| variance |        20 | history_only       | ridge             |      14 |          26 |    0.00367  |      0.007592 |   0.00246  |  -332.668  | 13180.7      |
| variance |        20 | history_only       | elastic_net       |      14 |          26 |    0.00368  |      0.008281 |   0.002346 |  -154.009  |  7282.41     |
| variance |        20 | history_plus_event | elastic_net       |      14 |          26 |    0.006369 |      0.017803 |   0.003742 |  -406.096  |  9355.56     |
| variance |        20 | history_plus_event | ridge             |      14 |          26 |    0.010492 |      0.027734 |   0.006637 | -1194.86   | 16516        |

## Interpretation

History-plus-event is useful only if it beats history-only for the
same target and horizon across event folds, not just in one fold.
A result supported by many event folds is more credible than a result
from a single 15-row holdout. This test still has a small number of
independent events, so uncertainty should be reported.
