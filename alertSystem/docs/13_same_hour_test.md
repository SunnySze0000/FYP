# 13 · Within the same hour: do linked holdings move more than the other holdings? (pre-registration)

*Written 2026-11-27 16:30 HKT, before running. Follow-up to doc 12.*

**Why.** Doc 12 found that hours with *any* bet jump move more, beyond the VIX. Here we compare holdings
**within the same hour**: everything common to that hour (the VIX, market-wide news, time of day) cancels out.
If the holdings linked to the jumping bets still move more than the others in that hour, the link is specific.

**Data.** The 19 non-crypto holdings, trading hours Nov 2024 – Nov 2026, only hours in which at least one
(non-crypto) bet jumped.

**Outcome:** |hourly return| ÷ the holding's average at that hour of day.

**Model.** The outcome is regressed on the holding's **linked-jump count** that hour (0, 1, 2, …) and its
recent volatility (previous 24 trading hours). The model includes **hour fixed effects** (each clock hour of
each day is its own group, which absorbs the VIX and all market-wide news) and **holding fixed effects**.
Bootstrap by day, 1,000 draws.

Reported in two forms:
- (a) a single **linked (yes/no)** term;
- (b) **count** terms: 1 linked jump, 2+ linked jumps.

**Pass:** (a) linked > 0 with CI > 0.
**Also reported** (user question): does **2+ linked jumps** give a larger effect than 1? This is the dose-response.

## Results (2026-11-27 16:35, `results/20261127-1630_same_hour/same_hour.json`)

760 news hours (a bet jumped somewhere); 14,401 holding-hours; 3,437 of them linked to a jumping bet. 1 = normal move.

| Comparison, within the same hour | Linked holdings vs the other holdings | 95% CI |
|---|---|---|
| **All news hours (main test)** | **+7% bigger move** | **+2% to +12% → PASS** |
| Overnight → first hour at the open | **+12%** | +4% to +20% |
| During trading hours | +2% | −4% to +9% (no effect) |
| 1 linked jump | +6% | +0% to +11% |
| **2+ linked jumps** | **+9%** | +2% to +17% |

**Reading**
- **The link is specific, but small.** With the VIX and all market-wide news cancelled out (same hour), holdings
  linked to the jumping bet move about 7% more than the other holdings.
- **It is almost entirely an overnight effect.** At the next open, linked holdings move about 12% more than the
  rest. During trading hours there is no holding-specific difference, matching S1 (stocks react first intraday).
- **More linked jumps → a bigger effect** (+6% for one, +9% for two or more), the dose-response the user expected.
- **This reconciles doc 12.** Doc 12 compared all hours with an unrelated-jump control and could not separate
  them; comparing holdings *within* the same hour is sharper, and the specific effect shows up, concentrated
  at the open.
