## D4 · Live feasibility

**Question.** Can the app get the live data it needs, fresh and fast enough?

**Verdict: PASS.** 20261127-021157_live_check: refresh 21.1 s for 50 watched markets; median latest-trade age 19.1 min; BTC bar age -1.1 min; sources {'gamma': True, 'data_api': True, 'clob': True, 'yahoo': True}.

| metric | value |
|---|---|
| id | d4 |
| verdict | pass |
| run_at | 2026-11-26T18:12:18.116135+00:00 |
| reachable.gamma | True |
| reachable.data_api | True |
| reachable.clob | True |
| reachable.yahoo | True |
| checks.all_sources_reachable | True |
| checks.median_trade_age_ok | True |
| checks.btc_bar_fresh | True |
| checks.refresh_fast | True |
| refresh_seconds | 21.1 |
| markets_scanned | 500 |
| watched_markets | 50 |
| median_trade_age_min | 19.12 |
| markets_with_trade_last_hour | 45 |
| btc_bar_age_min | -1.143 |

- Pass rule (pre-registered): all sources reachable; median trade age <= 60 min; BTC bar <= 90 min; refresh <= 120 s.
