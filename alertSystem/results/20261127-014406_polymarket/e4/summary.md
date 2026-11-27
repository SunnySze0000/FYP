## E4 · Copy-trading backtest (H3)

**Question.** After realistic delay and costs, does following skilled wallets make money?

**Verdict: FAIL.** Copying top-tier wallets 60 min later with a 1¢ cost returns -3.8% per $1 (95% CI -16.2% to +8.1%; 1678 copies in 124 markets) vs -2.7% for other ranked wallets.

| metric | value |
|---|---|
| main.tier | top |
| main.delay_s | 3600 |
| main.cost | 0.01 |
| main.signals | 1912 |
| main.copies | 1678 |
| main.markets | 124 |
| main.events | 121 |
| main.mean_return | -0.03802 |
| main.low | -0.1624 |
| main.high | 0.08144 |
| main.hit_rate | 0.5077 |
| main.mean_entry_price | 0.5866 |
| baseline_rest.tier | ranked_rest |
| baseline_rest.delay_s | 3600 |
| baseline_rest.cost | 0.01 |
| baseline_rest.signals | 21024 |
| baseline_rest.copies | 18632 |
| baseline_rest.markets | 142 |
| baseline_rest.events | 139 |
| baseline_rest.mean_return | -0.027 |
| baseline_rest.low | -0.07823 |
| baseline_rest.high | 0.0309 |
| baseline_rest.hit_rate | 0.5518 |
| baseline_rest.mean_entry_price | 0.5694 |

![copy_trading](figures/copy_trading.png)

Tables: [backtest_grid](tables/backtest_grid.csv)

- Signals: top-tier trades of at least $100 with YES price in (0.05, 0.95), one per wallet/market/hour; entry at the last price after the delay plus the cost; held to resolution.
- Pass rule (pre-registered): 60-minute delay, 1¢ cost, mean > 0 with CI above 0.
