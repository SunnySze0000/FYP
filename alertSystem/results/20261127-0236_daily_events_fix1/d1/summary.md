## D1 · Point-in-time universe

**Question.** Do the passed findings hold on every market the app could see at the time, not only hindsight-chosen ones?

**Verdict: PASS.** Without the hindsight filter (329 markets, watch rule): V1 +0.24× (CI +0.14 to +0.33); W3 AUC gain +0.048 (CI +0.036 to +0.063); W5 whale +0.82 (CI low +0.64) vs retail +0.09 points.

| metric | value |
|---|---|
| checks.a_v1_all_candidates | True |
| checks.b_w3_gain | True |
| checks.c_w5_whale_above_retail | True |
| v1.mean | 0.2391 |
| v1.low | 0.1437 |
| v1.high | 0.3328 |
| v1.n | 329 |
| v1.groups | 329 |
| v1.p_two_sided | 0 |
| v1_slices | [{'slice': 'all candidates (watched)', 'mean': 0.2390950340556899, 'low': 0.14368858272352372, 'high': 0.3327802452462573, 'n': 329, 'groups': 329, 'p_two_sided': 0.0}, {'slice': 'research markets only', 'mean': 0.24192438849154954, 'low': 0.14624704245980003, 'high': 0.338747863575333, 'n': 321, 'groups': 321, 'p_two_sided': 0.0}, {'slice': 'markets the hindsight filter dropped', 'mean': 0.12556718731682265, 'low': -0.15828152830487818, 'high': 0.395288933226896, 'n': 8, 'groups': 8, 'p_two_sided': 0.38}, {'slice': 'lowest-volume third', 'mean': 0.2545808697157563, 'low': 0.11863962075467677, 'high': 0.40666095246092715, 'n': 107, 'groups': 107, 'p_two_sided': 0.001}] |
| w3.auc_price_only | 0.8695 |
| w3.auc_with_wallets | 0.9177 |
| w3.gain | 0.04825 |
| w3.low | 0.03564 |
| w3.high | 0.06255 |
| w3.top5pct_lift | 13.2 |
| w3.coefficients.intercept | -6.761 |
| w3.coefficients.abs_dp | 0.1402 |
| w3.coefficients.recent_vol | 0.4179 |
| w3.coefficients.gross_z | -0.0186 |
| w3.coefficients.whale_z | -0.0546 |
| w3.coefficients.wallets_z | 0.8308 |
| w3.coefficients.new_z | 0.0037 |
| w3.coefficients.imbalance | -0.0782 |
| w3.train_hours | 457813 |
| w3.test_hours | 371132 |
| w3.test_jumps | 1361 |
| w5_whale.mean | 0.008199 |
| w5_whale.low | 0.006404 |
| w5_whale.high | 0.009993 |
| w5_whale.n | 13223 |
| w5_whale.groups | 280 |
| w5_whale.p_two_sided | 0 |
| w5_retail.mean | 0.0009442 |
| w5_retail.low | 0.0004917 |
| w5_retail.high | 0.001443 |
| w5_retail.n | 44518 |
| w5_retail.groups | 322 |
| w5_retail.p_two_sided | 0.0005 |
| watched_wallet_hours | 837213 |
| low_volume_cut_usd | 3.151e+06 |

Tables: [v1_slices](tables/v1_slices.csv)

- Watch rule: >= 24 h of history and probability 1 h earlier in 10-90%.
- Pass rule (pre-registered): (a) V1 CI > 0 on all candidates, (b) W3 gain CI > 0, (c) W5 whale CI above retail.
