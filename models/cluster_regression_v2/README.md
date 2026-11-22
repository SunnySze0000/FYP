# Cluster-implied probability regression

- Snapshot: `fed_20260531_v1`; memberships `datasets/polymarket/wallet_pipeline/fed_20260531_v2/memberships.csv.gz`; feature mode `summary`; skill `off`
- Implied-probability config: window 7.0 d, k = 3.0, beta = 2.0
- Clusters N = 6 (C0, C1, C2, C3, C4, C5); features per cluster M = 4; model inputs N x M = 24
- Cluster panel: 17 as-of days x 5 markets
- Rows joined to SPY trading days: 12 across 1 event(s)
- Share of cluster-market-days with any member activity: C0 100%, C1 81%, C2 100%, C3 100%, C4 54%, C5 100%
- Status: **insufficient_events: 1 event(s) with cluster features; walk-forward needs at least 3**

No model was scored. With one meeting and roughly a dozen trading days,
24 cluster inputs cannot be fitted and tested out of sample; any
in-sample fit would be overfitting. The pipeline below is verified end to end
so that a rolling-cutoff panel covering several meetings can be dropped in.

## Exploratory Spearman correlations (descriptive only)

Each uses n <= 12 overlapping daily rows from one meeting.

| feature                  | target              |   n |   spearman |
|:-------------------------|:--------------------|----:|-----------:|
| C0__expected_move_gap    | target_return_1d    |  12 |     0.1608 |
| C0__expected_move_gap    | target_return_5d    |  12 |     0.6993 |
| C0__expected_move_gap    | target_return_20d   |  12 |     0.7832 |
| C0__expected_move_gap    | target_variance_1d  |  12 |     0.5944 |
| C0__expected_move_gap    | target_variance_5d  |  12 |     0.042  |
| C0__expected_move_gap    | target_variance_20d |  12 |    -0.4406 |
| C1__expected_move_gap    | target_return_1d    |  12 |    -0.2937 |
| C1__expected_move_gap    | target_return_5d    |  12 |     0.2308 |
| C1__expected_move_gap    | target_return_20d   |  12 |    -0.0559 |
| C1__expected_move_gap    | target_variance_1d  |  12 |     0.2448 |
| C1__expected_move_gap    | target_variance_5d  |  12 |     0.2727 |
| C1__expected_move_gap    | target_variance_20d |  12 |     0.3706 |
| C2__expected_move_gap    | target_return_1d    |  12 |    -0.3427 |
| C2__expected_move_gap    | target_return_5d    |  12 |    -0.6084 |
| C2__expected_move_gap    | target_return_20d   |  12 |    -0.6853 |
| C2__expected_move_gap    | target_variance_1d  |  12 |    -0.5804 |
| C2__expected_move_gap    | target_variance_5d  |  12 |     0.2028 |
| C2__expected_move_gap    | target_variance_20d |  12 |     0.6434 |
| C3__expected_move_gap    | target_return_1d    |  12 |    -0.1678 |
| C3__expected_move_gap    | target_return_5d    |  12 |     0.1538 |
| C3__expected_move_gap    | target_return_20d   |  12 |     0.035  |
| C3__expected_move_gap    | target_variance_1d  |  12 |    -0.5245 |
| C3__expected_move_gap    | target_variance_5d  |  12 |    -0.1189 |
| C3__expected_move_gap    | target_variance_20d |  12 |    -0.035  |
| C4__expected_move_gap    | target_return_1d    |  12 |    -0.028  |
| C4__expected_move_gap    | target_return_5d    |  12 |     0.0909 |
| C4__expected_move_gap    | target_return_20d   |  12 |     0.1748 |
| C4__expected_move_gap    | target_variance_1d  |  12 |     0.0979 |
| C4__expected_move_gap    | target_variance_5d  |  12 |     0.7483 |
| C4__expected_move_gap    | target_variance_20d |  12 |     0.3776 |
| C5__expected_move_gap    | target_return_1d    |  12 |     0.3287 |
| C5__expected_move_gap    | target_return_5d    |  12 |     0.2727 |
| C5__expected_move_gap    | target_return_20d   |  12 |     0.1538 |
| C5__expected_move_gap    | target_variance_1d  |  12 |     0.0909 |
| C5__expected_move_gap    | target_variance_5d  |  12 |    -0.5035 |
| C5__expected_move_gap    | target_variance_20d |  12 |    -0.5664 |
| C0__move_std_gap         | target_return_1d    |  12 |    -0.2587 |
| C0__move_std_gap         | target_return_5d    |  12 |    -0.7203 |
| C0__move_std_gap         | target_return_20d   |  12 |    -0.8741 |
| C0__move_std_gap         | target_variance_1d  |  12 |    -0.3497 |
| C0__move_std_gap         | target_variance_5d  |  12 |     0.1538 |
| C0__move_std_gap         | target_variance_20d |  12 |     0.4825 |
| C1__move_std_gap         | target_return_1d    |  12 |     0.5245 |
| C1__move_std_gap         | target_return_5d    |  12 |     0.5035 |
| C1__move_std_gap         | target_return_20d   |  12 |     0.7133 |
| C1__move_std_gap         | target_variance_1d  |  12 |    -0.0909 |
| C1__move_std_gap         | target_variance_5d  |  12 |     0.1538 |
| C1__move_std_gap         | target_variance_20d |  12 |    -0.2098 |
| C2__move_std_gap         | target_return_1d    |  12 |     0.007  |
| C2__move_std_gap         | target_return_5d    |  12 |     0.3427 |
| C2__move_std_gap         | target_return_20d   |  12 |     0.4895 |
| C2__move_std_gap         | target_variance_1d  |  12 |     0.3427 |
| C2__move_std_gap         | target_variance_5d  |  12 |    -0.5874 |
| C2__move_std_gap         | target_variance_20d |  12 |    -0.8811 |
| C3__move_std_gap         | target_return_1d    |  12 |     0.042  |
| C3__move_std_gap         | target_return_5d    |  12 |     0.5944 |
| C3__move_std_gap         | target_return_20d   |  12 |     0.4476 |
| C3__move_std_gap         | target_variance_1d  |  12 |     0.0769 |
| C3__move_std_gap         | target_variance_5d  |  12 |     0.3497 |
| C3__move_std_gap         | target_variance_20d |  12 |     0.2517 |
| C4__move_std_gap         | target_return_1d    |  12 |    -0.049  |
| C4__move_std_gap         | target_return_5d    |  12 |    -0.1538 |
| C4__move_std_gap         | target_return_20d   |  12 |    -0.2308 |
| C4__move_std_gap         | target_variance_1d  |  12 |     0.0769 |
| C4__move_std_gap         | target_variance_5d  |  12 |    -0.5035 |
| C4__move_std_gap         | target_variance_20d |  12 |    -0.2937 |
| C5__move_std_gap         | target_return_1d    |  12 |     0.3357 |
| C5__move_std_gap         | target_return_5d    |  12 |     0.4476 |
| C5__move_std_gap         | target_return_20d   |  12 |     0.6503 |
| C5__move_std_gap         | target_variance_1d  |  12 |     0.4406 |
| C5__move_std_gap         | target_variance_5d  |  12 |    -0.5385 |
| C5__move_std_gap         | target_variance_20d |  12 |    -0.8531 |
| C0__tail_probability_gap | target_return_1d    |  12 |    -0.1608 |
| C0__tail_probability_gap | target_return_5d    |  12 |    -0.7203 |
| C0__tail_probability_gap | target_return_20d   |  12 |    -0.8601 |
| C0__tail_probability_gap | target_variance_1d  |  12 |    -0.2517 |
| C0__tail_probability_gap | target_variance_5d  |  12 |     0.021  |
| C0__tail_probability_gap | target_variance_20d |  12 |     0.2028 |
| C1__tail_probability_gap | target_return_1d    |  12 |     0.6643 |
| C1__tail_probability_gap | target_return_5d    |  12 |     0.1119 |
| C1__tail_probability_gap | target_return_20d   |  12 |     0.4685 |
| C1__tail_probability_gap | target_variance_1d  |  12 |    -0.1748 |
| C1__tail_probability_gap | target_variance_5d  |  12 |    -0.2937 |
| C1__tail_probability_gap | target_variance_20d |  12 |    -0.5385 |
| C2__tail_probability_gap | target_return_1d    |  12 |     0.1538 |
| C2__tail_probability_gap | target_return_5d    |  12 |     0.4056 |
| C2__tail_probability_gap | target_return_20d   |  12 |     0.4825 |
| C2__tail_probability_gap | target_variance_1d  |  12 |     0.3357 |
| C2__tail_probability_gap | target_variance_5d  |  12 |    -0.6014 |
| C2__tail_probability_gap | target_variance_20d |  12 |    -0.8881 |
| C3__tail_probability_gap | target_return_1d    |  12 |     0.2727 |
| C3__tail_probability_gap | target_return_5d    |  12 |     0.9021 |
| C3__tail_probability_gap | target_return_20d   |  12 |     0.8671 |
| C3__tail_probability_gap | target_variance_1d  |  12 |     0.2448 |
| C3__tail_probability_gap | target_variance_5d  |  12 |     0.021  |
| C3__tail_probability_gap | target_variance_20d |  12 |    -0.4545 |
| C4__tail_probability_gap | target_return_1d    |  12 |    -0.1329 |
| C4__tail_probability_gap | target_return_5d    |  12 |     0.1329 |
| C4__tail_probability_gap | target_return_20d   |  12 |     0.1678 |
| C4__tail_probability_gap | target_variance_1d  |  12 |     0.2657 |
| C4__tail_probability_gap | target_variance_5d  |  12 |     0.2517 |
| C4__tail_probability_gap | target_variance_20d |  12 |    -0.1329 |
| C5__tail_probability_gap | target_return_1d    |  12 |     0.2727 |
| C5__tail_probability_gap | target_return_5d    |  12 |     0.4056 |
| C5__tail_probability_gap | target_return_20d   |  12 |     0.6224 |
| C5__tail_probability_gap | target_variance_1d  |  12 |     0.3566 |
| C5__tail_probability_gap | target_variance_5d  |  12 |    -0.5524 |
| C5__tail_probability_gap | target_variance_20d |  12 |    -0.8601 |
| C0__kl_from_market       | target_return_1d    |  12 |    -0.3007 |
| C0__kl_from_market       | target_return_5d    |  12 |    -0.5175 |
| C0__kl_from_market       | target_return_20d   |  12 |    -0.6294 |
| C0__kl_from_market       | target_variance_1d  |  12 |    -0.4056 |
| C0__kl_from_market       | target_variance_5d  |  12 |     0.3497 |
| C0__kl_from_market       | target_variance_20d |  12 |     0.7063 |
| C1__kl_from_market       | target_return_1d    |  12 |     0.2308 |
| C1__kl_from_market       | target_return_5d    |  12 |     0.1888 |
| C1__kl_from_market       | target_return_20d   |  12 |     0.4196 |
| C1__kl_from_market       | target_variance_1d  |  12 |     0.042  |
| C1__kl_from_market       | target_variance_5d  |  12 |     0.3846 |
| C1__kl_from_market       | target_variance_20d |  12 |     0.0979 |
| C2__kl_from_market       | target_return_1d    |  12 |    -0.0699 |
| C2__kl_from_market       | target_return_5d    |  12 |    -0.3566 |
| C2__kl_from_market       | target_return_20d   |  12 |    -0.5035 |
| C2__kl_from_market       | target_variance_1d  |  12 |    -0.3636 |
| C2__kl_from_market       | target_variance_5d  |  12 |     0.5664 |
| C2__kl_from_market       | target_variance_20d |  12 |     0.8671 |
| C3__kl_from_market       | target_return_1d    |  12 |    -0.1189 |
| C3__kl_from_market       | target_return_5d    |  12 |    -0.4545 |
| C3__kl_from_market       | target_return_20d   |  12 |    -0.4545 |
| C3__kl_from_market       | target_variance_1d  |  12 |    -0.0839 |
| C3__kl_from_market       | target_variance_5d  |  12 |    -0.1329 |
| C3__kl_from_market       | target_variance_20d |  12 |     0.3566 |
| C4__kl_from_market       | target_return_1d    |  12 |    -0.1259 |
| C4__kl_from_market       | target_return_5d    |  12 |    -0.007  |
| C4__kl_from_market       | target_return_20d   |  12 |     0.1888 |
| C4__kl_from_market       | target_variance_1d  |  12 |     0.007  |
| C4__kl_from_market       | target_variance_5d  |  12 |     0.1189 |
| C4__kl_from_market       | target_variance_20d |  12 |    -0.0979 |
| C5__kl_from_market       | target_return_1d    |  12 |     0.3497 |
| C5__kl_from_market       | target_return_5d    |  12 |     0.2098 |
| C5__kl_from_market       | target_return_20d   |  12 |     0.3497 |
| C5__kl_from_market       | target_variance_1d  |  12 |     0.2797 |
| C5__kl_from_market       | target_variance_5d  |  12 |    -0.7762 |
| C5__kl_from_market       | target_variance_20d |  12 |    -0.8112 |

