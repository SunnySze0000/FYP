## W6 · Robustness of the wallet passes

**Question.** Do W2, W3 and W5 survive a timestamp check and a 15-minute gap before each hour?

**Verdict: FAIL.** Hourly prices match the last trade at the timestamp itself (best offset +0 min), so there is no stale-snapshot leak. With wallet flows ending 15 min before each hour: W2 large-wallet jumps +2.3 pts (CI -1.5 to +6.1); W3 AUC gain +0.018 (CI +0.010 to +0.029); W5 whale +0.39 vs retail +0.03 pts. Still holding: w3_auc_gain, w5_whale_beats_retail.

| metric | value |
|---|---|
| timestamp_best_offset_min | 0 |
| w2_gap.diff | 0.02318 |
| w2_gap.low | -0.01477 |
| w2_gap.high | 0.06124 |
| w2_gap.mean_high_group | -0.01672 |
| w2_gap.mean_low_group | -0.0399 |
| w2_gap.n_high | 262 |
| w2_gap.n_low | 1530 |
| w2_gap.markets | 436 |
| w3_gap.auc_price_only | 0.8866 |
| w3_gap.auc_with_wallets | 0.905 |
| w3_gap.gain | 0.01835 |
| w3_gap.low | 0.009639 |
| w3_gap.high | 0.02862 |
| w3_gap.top5pct_lift | 12.6 |
| w3_gap.coefficients.intercept | -7.057 |
| w3_gap.coefficients.abs_dp | 0.1395 |
| w3_gap.coefficients.recent_vol | 0.3719 |
| w3_gap.coefficients.gross_z | 0.0227 |
| w3_gap.coefficients.whale_z | -0.0752 |
| w3_gap.coefficients.wallets_z | 0.7576 |
| w3_gap.coefficients.new_z | -0.0057 |
| w3_gap.coefficients.imbalance | -0.1221 |
| w3_gap.train_hours | 699265 |
| w3_gap.test_hours | 602579 |
| w3_gap.test_jumps | 1718 |
| w5_gap_whale.mean | 0.00385 |
| w5_gap_whale.low | 0.002864 |
| w5_gap_whale.high | 0.004836 |
| w5_gap_whale.n | 20951 |
| w5_gap_whale.groups | 312 |
| w5_gap_whale.p_two_sided | 0 |
| w5_gap_retail.mean | 0.0003398 |
| w5_gap_retail.low | 2.465e-05 |
| w5_gap_retail.high | 0.0006622 |
| w5_gap_retail.n | 59340 |
| w5_gap_retail.groups | 338 |
| w5_gap_retail.p_two_sided | 0.039 |
| checks.w2_large_wallets_behind | False |
| checks.w3_auc_gain | True |
| checks.w5_whale_beats_retail | True |

Tables: [timestamp_check](tables/timestamp_check.csv)

- Added after W2, W3 and W5 passed; a robustness check, not a new pass rule. Verdict: pass only if the timestamps are aligned and all three still hold with the gap.
