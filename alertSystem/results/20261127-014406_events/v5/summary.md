## V5 · Robustness of V2 and V3

**Question.** Do the narrow V2/V3 passes survive placebo, subgroup and head-to-head checks?

**Verdict: PASS.** V2 direction holds: placebo assets 50.5% (≈ 50% as it should be), related assets without crypto-price markets 53.4%. V3: skilled minus other wallets' flow = -3.40 points per market (CI -5.99 to -1.32), so skilled wallets do not move first beyond ordinary order-flow momentum.

| metric | value |
|---|---|
| direction_mapped.hit_rate | 0.5315 |
| direction_mapped.low | 0.5061 |
| direction_mapped.high | 0.5547 |
| direction_mapped.markets | 343 |
| direction_placebo.hit_rate | 0.5052 |
| direction_placebo.low | 0.4768 |
| direction_placebo.high | 0.5331 |
| direction_placebo.markets | 363 |
| direction_mapped_without_crypto.hit_rate | 0.534 |
| direction_mapped_without_crypto.low | 0.5064 |
| direction_mapped_without_crypto.high | 0.5624 |
| direction_mapped_without_crypto.markets | 256 |
| wallets.per_market_top_minus_rest.mean | -0.03401 |
| wallets.per_market_top_minus_rest.low | -0.05993 |
| wallets.per_market_top_minus_rest.high | -0.01316 |
| wallets.per_market_top_minus_rest.n | 170 |
| wallets.per_market_top_minus_rest.groups | 170 |
| wallets.per_market_top_minus_rest.p_two_sided | 0.0085 |
| wallets.markets | 170 |
| wallets.regression_points.skilled_flow | 0.007896 |
| wallets.regression_points.other_flow | 0.006247 |
| wallets.regression_points.hours | 11693 |
| v2_holds | True |
| skilled_beat_others | False |

Tables: [direction_by_group](tables/direction_by_group.csv)

- Added after V2 and V3 passed narrowly; reported as a robustness check, not a new pass rule.
- Verdict reflects V2 only; the wallet head-to-head is reported in the metrics and headline.
