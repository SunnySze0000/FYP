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

Tables: [market_index](tables/market_index.csv), [wallet_recent_markets](tables/wallet_recent_markets.csv), [wallet_scores](tables/wallet_scores.csv)

- Wallet scores use every resolved market (the app looks forward from today), so historical market pages contain hindsight; the out-of-sample hit rate uses point-in-time tiers only.
