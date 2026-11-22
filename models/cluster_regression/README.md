# Cluster-implied probability regression

- Snapshot: `fed_20260531_v1`; memberships `pilot cluster_membership.csv`; feature mode `summary`; skill `off`
- Implied-probability config: window 7.0 d, k = 3.0, beta = 2.0
- Clusters N = 2 (C0, C1); features per cluster M = 4; model inputs N x M = 8
- Cluster panel: 17 as-of days x 5 markets
- Rows joined to SPY trading days: 12 across 1 event(s)
- Share of cluster-market-days with any member activity: C0 96%, C1 20%
- Status: **insufficient_events: 1 event(s) with cluster features; walk-forward needs at least 3**

No model was scored. With one meeting and roughly a dozen trading days,
8 cluster inputs cannot be fitted and tested out of sample; any
in-sample fit would be overfitting. The pipeline below is verified end to end
so that a rolling-cutoff panel covering several meetings can be dropped in.

## Exploratory Spearman correlations (descriptive only)

Each uses n <= 12 overlapping daily rows from one meeting.

| feature                  | target              |   n |   spearman |
|:-------------------------|:--------------------|----:|-----------:|
| C0__expected_move_gap    | target_return_1d    |  12 |     0.4685 |
| C0__expected_move_gap    | target_return_5d    |  12 |     0.5385 |
| C0__expected_move_gap    | target_return_20d   |  12 |     0.5524 |
| C0__expected_move_gap    | target_variance_1d  |  12 |     0.2517 |
| C0__expected_move_gap    | target_variance_5d  |  12 |    -0.4545 |
| C0__expected_move_gap    | target_variance_20d |  12 |    -0.7483 |
| C1__expected_move_gap    | target_return_1d    |  12 |     0.0841 |
| C1__expected_move_gap    | target_return_5d    |  12 |    -0.3923 |
| C1__expected_move_gap    | target_return_20d   |  12 |    -0.5079 |
| C1__expected_move_gap    | target_variance_1d  |  12 |    -0.4448 |
| C1__expected_move_gap    | target_variance_5d  |  12 |     0.4659 |
| C1__expected_move_gap    | target_variance_20d |  12 |     0.7916 |
| C0__move_std_gap         | target_return_1d    |  12 |    -0.0699 |
| C0__move_std_gap         | target_return_5d    |  12 |     0.6154 |
| C0__move_std_gap         | target_return_20d   |  12 |     0.5874 |
| C0__move_std_gap         | target_variance_1d  |  12 |     0.1748 |
| C0__move_std_gap         | target_variance_5d  |  12 |     0.0769 |
| C0__move_std_gap         | target_variance_20d |  12 |    -0.1049 |
| C1__move_std_gap         | target_return_1d    |  12 |     0.1261 |
| C1__move_std_gap         | target_return_5d    |  12 |     0.4343 |
| C1__move_std_gap         | target_return_20d   |  12 |     0.5009 |
| C1__move_std_gap         | target_variance_1d  |  12 |     0.3608 |
| C1__move_std_gap         | target_variance_5d  |  12 |    -0.5849 |
| C1__move_std_gap         | target_variance_20d |  12 |    -0.8687 |
| C0__tail_probability_gap | target_return_1d    |  12 |    -0.3217 |
| C0__tail_probability_gap | target_return_5d    |  12 |     0.3427 |
| C0__tail_probability_gap | target_return_20d   |  12 |     0.3217 |
| C0__tail_probability_gap | target_variance_1d  |  12 |     0.2168 |
| C0__tail_probability_gap | target_variance_5d  |  12 |     0.1958 |
| C0__tail_probability_gap | target_variance_20d |  12 |     0.0839 |
| C1__tail_probability_gap | target_return_1d    |  12 |     0.1331 |
| C1__tail_probability_gap | target_return_5d    |  12 |     0.3783 |
| C1__tail_probability_gap | target_return_20d   |  12 |     0.3958 |
| C1__tail_probability_gap | target_variance_1d  |  12 |     0.4378 |
| C1__tail_probability_gap | target_variance_5d  |  12 |    -0.5429 |
| C1__tail_probability_gap | target_variance_20d |  12 |    -0.8336 |
| C0__kl_from_market       | target_return_1d    |  12 |    -0.0979 |
| C0__kl_from_market       | target_return_5d    |  12 |     0.0769 |
| C0__kl_from_market       | target_return_20d   |  12 |     0.049  |
| C0__kl_from_market       | target_variance_1d  |  12 |    -0.0559 |
| C0__kl_from_market       | target_variance_5d  |  12 |     0.7203 |
| C0__kl_from_market       | target_variance_20d |  12 |     0.5594 |
| C1__kl_from_market       | target_return_1d    |  12 |    -0.035  |
| C1__kl_from_market       | target_return_5d    |  12 |    -0.7075 |
| C1__kl_from_market       | target_return_20d   |  12 |    -0.718  |
| C1__kl_from_market       | target_variance_1d  |  12 |    -0.1296 |
| C1__kl_from_market       | target_variance_5d  |  12 |     0.1786 |
| C1__kl_from_market       | target_variance_20d |  12 |     0.5674 |

