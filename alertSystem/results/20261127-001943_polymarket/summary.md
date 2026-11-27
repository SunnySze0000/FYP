# F · Smart money inside Polymarket

Run `20261127-001943_polymarket` on dataset **universe**.

| Experiment | Verdict | Headline |
|---|---|---|
| [E0 Dataset overview](e0/summary.md) | **descriptive** | 300 markets in 294 events, 489,682 trades by 56,852 wallets; 1,877 wallets traded 5+ markets and the top 1% of wallets did 61% of the volume. |
| [E1 Calibration and fair value (H0)](e1/summary.md) | **descriptive** | Prices are off by 6.6% on average across buckets; the fair-value map (b = 0.89) does not improve period-B log loss (0.5040 → 0.5102). |
| [E2 Skill persistence (H1)](e2/summary.md) | **fail** | Spearman ρ between period-A and period-B edge = 0.086 (95% CI -0.106 to 0.267, permutation p = 0.1588, 129 wallets with ≥ 5 markets in each period). Holding long-shot style fixed: ρ = 0.085. |
| [E3 Information in skilled wallets' trades (H2)](e3/summary.md) | **fail** | Top-tier trades beat other trades by +0.39 points to resolution (95% CI -3.97 to +4.87; 128 markets, 125 events). |
| [E4 Copy-trading backtest (H3)](e4/summary.md) | **fail** | Copying top-tier wallets 60 min later with a 1¢ cost returns -3.8% per $1 (95% CI -16.2% to +8.1%; 1678 copies in 124 markets) vs -2.7% for other ranked wallets. |
| [E5 App export](e5/summary.md) | **descriptive** | Exported 2000 wallet track records (529 in the top tier) and 300 market pages. Out of sample, the top tier's net side won in 62% of 133 markets (the market's own mid-life favourite: 73%). |

**Decision (pre-registered rule):** Pivot: fair-value / mispricing helper; refine the topic.

## E0 · Dataset overview

**Question.** What does the data cover, and do enough wallets trade many markets to measure skill?

**Verdict: DESCRIPTIVE.** 300 markets in 294 events, 489,682 trades by 56,852 wallets; 1,877 wallets traded 5+ markets and the top 1% of wallets did 61% of the volume.

| metric | value |
|---|---|
| markets | 300 |
| events | 294 |
| trades | 489682 |
| wallets | 56852 |
| first_close | 2024-11-15 |
| last_close | 2026-10-31 |
| split_date | 2026-03-01 |
| period_a_markets | 148 |
| period_b_markets | 152 |
| top_1pct_wallets_share_of_volume | 0.6136 |
| wallets_with_5plus_markets | 1877 |
| wallets_with_3plus_events | 5248 |
| yes_resolution_rate | 0.3967 |

![coverage](e0/figures/coverage.png)

Tables: [markets](e0/tables/markets.csv), [wallet_repeat](e0/tables/wallet_repeat.csv)

- Trade rows are participant records: each fill appears once for every wallet in it.
- Dataset source: collector

## E1 · Calibration and fair value (H0)

**Question.** Do YES prices match how often YES happens, and can a simple recalibration improve them?

**Verdict: DESCRIPTIVE.** Prices are off by 6.6% on average across buckets; the fair-value map (b = 0.89) does not improve period-B log loss (0.5040 → 0.5102).

| metric | value |
|---|---|
| points | 691 |
| markets | 300 |
| mean_abs_gap | 0.06641 |
| brier_by_horizon.1d | 0.1414 |
| brier_by_horizon.7d | 0.1835 |
| brier_by_horizon.30d | 0.1653 |
| fair_value.a | 0.4468 |
| fair_value.b | 0.8923 |
| fair_value.n | 343 |
| fair_value.fitted | True |
| period_b_logloss_market | 0.504 |
| period_b_logloss_fair | 0.5102 |
| period_b_logloss_improvement | -0.006232 |

![calibration](e1/figures/calibration.png)

Tables: [brier](e1/tables/brier.csv), [reliability](e1/tables/reliability.csv)

- Fair value is fitted on period A only and used for every edge measure in E2–E4.
- Points from different horizons of the same market are not independent.

## E2 · Skill persistence (H1)

**Question.** Do wallets with high edge in earlier markets also have high edge in later markets?

**Verdict: FAIL.** Spearman ρ between period-A and period-B edge = 0.086 (95% CI -0.106 to 0.267, permutation p = 0.1588, 129 wallets with ≥ 5 markets in each period). Holding long-shot style fixed: ρ = 0.085.

| metric | value |
|---|---|
| edge_vs_fair.rho | 0.08607 |
| edge_vs_fair.p_one_sided | 0.1588 |
| edge_vs_fair.low | -0.1061 |
| edge_vs_fair.high | 0.2674 |
| edge_vs_fair.n | 129 |
| edge_vs_price.rho | 0.0949 |
| edge_vs_price.p_one_sided | 0.1439 |
| edge_vs_price.low | -0.09188 |
| edge_vs_price.high | 0.2947 |
| edge_vs_price.n | 129 |
| partial_longshot.rho | 0.08529 |
| partial_longshot.n | 129 |
| rolling_mean_rho | 0.08074 |
| rolling_events | 214 |
| min_markets_per_period | 5 |

![persistence](e2/figures/persistence.png)

Tables: [rolling](e2/tables/rolling.csv), [wallet_pairs](e2/tables/wallet_pairs.csv)

- Pass rule (pre-registered): ρ > 0 with permutation p < 0.05; fewer than 30 wallets = inconclusive.
- Edge is measured against fair value from E1; the raw-price version is reported for comparison.

## E3 · Information in skilled wallets' trades (H2)

**Question.** Is the price more likely to move in a trade's direction when the trader has proven skill?

**Verdict: FAIL.** Top-tier trades beat other trades by +0.39 points to resolution (95% CI -3.97 to +4.87; 128 markets, 125 events).

| metric | value |
|---|---|
| main.sample | band |
| main.weighting | equal |
| main.horizon | markout_res |
| main.top_mean | 0.005545 |
| main.rest_mean | 0.001678 |
| main.diff | 0.003867 |
| main.low | -0.03967 |
| main.high | 0.0487 |
| main.p | 0.871 |
| main.markets | 128 |
| main.events | 125 |
| top_tier_share_of_trades | 0.03168 |
| period_b_trades | 289456 |
| banded_trades | 233173 |

![markouts](e3/figures/markouts.png)

Tables: [markout_tests](e3/tables/markout_tests.csv), [per_market_main](e3/tables/per_market_main.csv), [tier_means_pct_points](e3/tables/tier_means_pct_points.csv)

- Skill tier is decided with markets closed before each trade (walk-forward).
- Main test (pre-registered): trades with YES price in the band, equal weight, to resolution; per-market differences, bootstrap over events. Fewer than 5 events or 10 markets = inconclusive.

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

![copy_trading](e4/figures/copy_trading.png)

Tables: [backtest_grid](e4/tables/backtest_grid.csv)

- Signals: top-tier trades of at least $100 with YES price in (0.05, 0.95), one per wallet/market/hour; entry at the last price after the delay plus the cost; held to resolution.
- Pass rule (pre-registered): 60-minute delay, 1¢ cost, mean > 0 with CI above 0.

## E5 · App export

**Question.** What does the trading helper load?

**Verdict: DESCRIPTIVE.** Exported 2000 wallet track records (529 in the top tier) and 300 market pages. Out of sample, the top tier's net side won in 62% of 133 markets (the market's own mid-life favourite: 73%).

| metric | value |
|---|---|
| ranked_wallets | 5284 |
| top_wallets | 529 |
| top_threshold | 0.07703 |
| exported_wallets | 2000 |
| markets | 300 |
| out_of_sample_markets_with_top_flow | 133 |
| top_net_side_hit_rate | 0.6165 |
| market_favourite_hit_rate | 0.7293 |
| fair_value.a | 0.4468 |
| fair_value.b | 0.8923 |
| fair_value.n | 343 |
| fair_value.fitted | True |

Tables: [market_index](e5/tables/market_index.csv), [wallet_recent_markets](e5/tables/wallet_recent_markets.csv), [wallet_scores](e5/tables/wallet_scores.csv)

- Wallet scores use every resolved market (the app looks forward from today), so historical market pages contain hindsight; the out-of-sample hit rate uses point-in-time tiers only.
