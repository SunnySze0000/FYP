## E5 · App export

**Question.** What does the trading helper load?

**Verdict: DESCRIPTIVE.** Exported 2000 wallet track records (3012 in the top tier) and 31 market pages. Out of sample, the top tier's net side won in 100% of 15 markets (the market's own mid-life favourite: 87%).

| metric | value |
|---|---|
| ranked_wallets | 30041 |
| top_wallets | 3012 |
| top_threshold | 0.0165 |
| exported_wallets | 2000 |
| markets | 31 |
| out_of_sample_markets_with_top_flow | 15 |
| top_net_side_hit_rate | 1 |
| market_favourite_hit_rate | 0.8667 |
| fair_value.a | 0 |
| fair_value.b | 1 |
| fair_value.n | 48 |
| fair_value.fitted | False |

Tables: [market_index](tables/market_index.csv), [wallet_recent_markets](tables/wallet_recent_markets.csv), [wallet_scores](tables/wallet_scores.csv)

- Wallet scores use every resolved market (the app looks forward from today), so historical market pages contain hindsight; the out-of-sample hit rate uses point-in-time tiers only.
