# Event-level walk-forward validation

Each complete Federal Reserve event is held out in chronological order.
Training uses only earlier events. This is stricter than a daily random
or single-date holdout because repeated snapshots of one meeting stay in
the same event block.

- Minimum training events before a test: 10
- Test event blocks evaluated: 17
- Total scored fold/model rows: 711

## Aggregate results

### return, 1 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| return   |         1 | event_only         | elastic_net       |      17 |         591 |    0.008495 |      0.008868 |   0.006252 | -0.017595 |          nan |
| return   |         1 | history_plus_event | elastic_net       |      17 |         591 |    0.0085   |      0.008879 |   0.006261 | -0.017384 |          nan |
| return   |         1 | history_only       | elastic_net       |      17 |         591 |    0.008514 |      0.008898 |   0.006266 | -0.019634 |          nan |
| return   |         1 | history_only       | gradient_boosting |      17 |         591 |    0.008565 |      0.008955 |   0.00633  | -0.031515 |          nan |
| return   |         1 | history_plus_event | gradient_boosting |      17 |         591 |    0.008602 |      0.008998 |   0.00635  | -0.040231 |          nan |
| return   |         1 | event_only         | ridge             |      17 |         591 |    0.008673 |      0.009059 |   0.00644  | -0.059155 |          nan |
| return   |         1 | event_only         | gradient_boosting |      17 |         591 |    0.008683 |      0.009063 |   0.006437 | -0.065899 |          nan |
| return   |         1 | history_only       | ridge             |      17 |         591 |    0.008604 |      0.009082 |   0.006375 | -0.029611 |          nan |
| return   |         1 | history_plus_event | ridge             |      17 |         591 |    0.008796 |      0.009288 |   0.006563 | -0.077752 |          nan |

### return, 5 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| return   |         5 | event_only         | elastic_net       |      17 |         118 |    0.018046 |      0.019501 |   0.014942 | -0.318493 |          nan |
| return   |         5 | history_only       | gradient_boosting |      17 |         118 |    0.018489 |      0.019712 |   0.014903 | -0.554763 |          nan |
| return   |         5 | history_plus_event | gradient_boosting |      17 |         118 |    0.018655 |      0.020028 |   0.015158 | -0.637689 |          nan |
| return   |         5 | event_only         | gradient_boosting |      17 |         118 |    0.018498 |      0.020052 |   0.015322 | -0.465313 |          nan |
| return   |         5 | history_only       | elastic_net       |      17 |         118 |    0.018659 |      0.020688 |   0.014721 | -0.41777  |          nan |
| return   |         5 | event_only         | ridge             |      17 |         118 |    0.019067 |      0.020774 |   0.015817 | -0.573066 |          nan |
| return   |         5 | history_plus_event | elastic_net       |      17 |         118 |    0.01915  |      0.020819 |   0.01513  | -0.565883 |          nan |
| return   |         5 | history_only       | ridge             |      17 |         118 |    0.019166 |      0.02132  |   0.01499  | -0.50638  |          nan |
| return   |         5 | history_plus_event | ridge             |      17 |         118 |    0.02112  |      0.023349 |   0.016507 | -0.854626 |          nan |

### return, 20 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| return   |        20 | history_only       | elastic_net       |      14 |          25 |    0.025331 |      0.02731  |   0.024334 |  -26.6812 |          nan |
| return   |        20 | history_only       | ridge             |      14 |          25 |    0.025527 |      0.027597 |   0.024582 |  -26.7281 |          nan |
| return   |        20 | history_plus_event | gradient_boosting |      13 |          23 |    0.025592 |      0.027896 |   0.023295 |  -48.8092 |          nan |
| return   |        20 | history_only       | gradient_boosting |      14 |          25 |    0.025362 |      0.028035 |   0.022288 |  -60.084  |          nan |
| return   |        20 | event_only         | gradient_boosting |      13 |          23 |    0.028787 |      0.033179 |   0.026863 |  -15.3949 |          nan |
| return   |        20 | event_only         | elastic_net       |      13 |          23 |    0.029574 |      0.034506 |   0.028356 |  -19.1127 |          nan |
| return   |        20 | event_only         | ridge             |      13 |          23 |    0.030091 |      0.035052 |   0.028497 |  -21.0132 |          nan |
| return   |        20 | history_plus_event | elastic_net       |      13 |          23 |    0.03488  |      0.044008 |   0.032538 |  -64.9325 |          nan |
| return   |        20 | history_plus_event | ridge             |      13 |          23 |    0.035881 |      0.045525 |   0.033302 |  -70.3142 |          nan |

### variance, 1 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| variance |         1 | history_only       | gradient_boosting |      17 |         591 |    0.000174 |      0.000322 |   8.3e-05  | -0.028203 |      5.92282 |
| variance |         1 | history_plus_event | gradient_boosting |      17 |         591 |    0.000177 |      0.000323 |   8.6e-05  | -0.128975 |      5.70291 |
| variance |         1 | history_only       | ridge             |      17 |         591 |    0.000191 |      0.000324 |   0.000102 | -0.527863 |    460.624   |
| variance |         1 | history_only       | elastic_net       |      17 |         591 |    0.000179 |      0.000326 |   9.2e-05  | -0.160997 |      1.73954 |
| variance |         1 | history_plus_event | elastic_net       |      17 |         591 |    0.000179 |      0.000326 |   9.2e-05  | -0.161153 |      1.73963 |
| variance |         1 | history_plus_event | ridge             |      17 |         591 |    0.000201 |      0.000331 |   0.000115 | -0.865816 |    455.714   |

### variance, 5 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| variance |         5 | history_only       | gradient_boosting |      17 |         118 |    0.000472 |      0.00087  |   0.000283 |  -1.13407 |     0.447758 |
| variance |         5 | history_plus_event | gradient_boosting |      17 |         118 |    0.000466 |      0.000872 |   0.000282 |  -1.12414 |     0.417954 |
| variance |         5 | history_only       | ridge             |      17 |         118 |    0.000576 |      0.000874 |   0.000389 |  -4.74504 |  2333.27     |
| variance |         5 | history_only       | elastic_net       |      17 |         118 |    0.00048  |      0.000885 |   0.000308 |  -1.65122 |     0.549209 |
| variance |         5 | history_plus_event | elastic_net       |      17 |         118 |    0.000484 |      0.000887 |   0.00031  |  -1.74264 |     0.552248 |
| variance |         5 | history_plus_event | ridge             |      17 |         118 |    0.000689 |      0.000989 |   0.000458 | -14.7482  |  2688.37     |

### variance, 20 trading day(s)

| target   |   horizon | feature_set        | model             |   folds |   test_rows |   mean_rmse |   pooled_rmse |   mean_mae |   mean_r2 |   mean_qlike |
|:---------|----------:|:-------------------|:------------------|--------:|------------:|------------:|--------------:|-----------:|----------:|-------------:|
| variance |        20 | history_only       | ridge             |      14 |          25 |    0.000889 |      0.001536 |   0.000726 |  -27.5024 |     0.203741 |
| variance |        20 | history_plus_event | ridge             |      13 |          23 |    0.001077 |      0.001839 |   0.000852 |  -39.4561 |     0.417311 |
| variance |        20 | history_only       | elastic_net       |      14 |          25 |    0.001068 |      0.002125 |   0.000802 |  -16.8422 |     0.280487 |
| variance |        20 | history_only       | gradient_boosting |      14 |          25 |    0.001238 |      0.002155 |   0.000965 |  -43.985  |     0.341796 |
| variance |        20 | history_plus_event | elastic_net       |      13 |          23 |    0.001054 |      0.002192 |   0.000781 |  -24.1255 |     0.30017  |
| variance |        20 | history_plus_event | gradient_boosting |      13 |          23 |    0.001239 |      0.002304 |   0.00094  |  -10.2444 |     0.30642  |

## Interpretation

History-plus-event is useful only if it beats history-only for the
same target and horizon across event folds, not just in one fold.
A result supported by many event folds is more credible than a result
from a single 15-row holdout. This test still has a small number of
independent events, so uncertainty should be reported.
