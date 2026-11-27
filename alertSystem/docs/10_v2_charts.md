# 10 · V2 charts: holding volatility vs linked event jumps, across the whole history

Folder: `results/20261127-1600_v2_charts/`. Scripts: `scripts/v2_history.py` (full history) and
`scripts/v2_charts.py` (zoom-ins, event-time profile, overnight). Crypto bets and crypto assets are excluded.

- **A_full_history.png:** Nov 2024 to Nov 2026, 8 holdings. The line is daily volatility (5-day average,
  1 = normal). Under it, the linked event jumps of each day point up (blue) and the unrelated ones point down (orange).
- **B_correlation_by_holding.png:** for 19 holdings, the Spearman correlation of daily volatility with linked
  jumps vs with unrelated jumps.
- **C_volatility_by_jump_count.png:** all holdings and all days pooled. Volatility rises with the number of
  linked jumps that day: 0.98 (none), 1.06 (1), 1.15 (2), 1.11 (3–4), 1.29 (5–9), 1.46 (10+). By unrelated jumps
  it stays flat: 0.96–1.13, and 0.99 at 10+.
- Zoom-ins and tests: `1_timelines.png` (hourly bars, linked-jump hours 1.3–1.5× normal),
  `2_event_time_profile.png` (S1), `4_overnight_next_open.png` (S2: 1.16× vs 0.96×).

**Honest reading:** at the daily level the effect is clear when pooled (C), but per holding it is weak
(ρ = −0.07 to +0.21). Linked jumps beat unrelated jumps in only about half the holdings, and the AI/tech
holdings show none. One jump hour is diluted in a whole trading day, and big market-wide weeks (April 2025)
raise everything. The signal lives at the hourly level and around the open, not in daily volatility.
