# 05 · Daily-use applicability check (pre-registration)

*Written 2026-11-27 02:15 HKT, **before** any of these tests were run. Pass rules are fixed here and are not
changed after seeing results. If a gate fails, we do not build: we diagnose, propose a fix, and retest the
fix as a new, separately labelled test.*

## Why this check

V1 (event shocks move related assets), W3 (wallet early warning) and W5 (large-wallet pressure) passed on a
research dataset. A tool someone opens **every day** needs more than that:

1. It must work on the markets the app can **see at the time**, not on markets chosen with hindsight.
2. It must keep working **over time**, including the most recent months.
3. Its alerts must carry **real information** and come at a **usable rate** (not silent, not spam).
4. The **live data** it needs must be available, fresh and fast enough to fetch.
5. It must work across **event types**, not only one lucky group.

## Known limitations of the research so far (stated up front)

| # | Limitation | Where it bites | Addressed by |
|---|---|---|---|
| L1 | Markets were kept only if they spent ≥ 36 hours in the 15–85% band over their **whole** life: hindsight. | App cannot know this in advance. | D1 |
| L2 | Candidate markets needed ≥ $100k **final** volume: also hindsight, but mild (a live app can rank by volume so far). | Small markets may behave differently. | D1 (low-volume third reported) — stays a limitation |
| L3 | Results were pooled over Aug 2024 – Nov 2026. A pooled pass can hide an effect that faded. | Recent usefulness. | D2 |
| L4 | V1 is a ratio of averages; it does not say whether an individual alert is informative. | Alert quality. | D3 |
| L5 | Only a sample of markets (≤ 1,200 candidates, 200 per group) was collected; the live universe is larger. | Alert counts. | D3 reports counts as a *lower bound* |
| L6 | Hourly prices only; stock assets trade 6.5 h/day on weekdays, so many shocks happen when stocks are closed. | Coverage, timing. | D3, D5 |
| L7 | Event → asset links come from keyword groups, not a learned model. Some links are loose. | False alerts. | D6, stays a limitation |
| L8 | Association, not causation; the direction hint is weak (≈ 53%). | Advice wording. | App says "risk", never "trade" |
| L9 | Research used historical endpoints; the live endpoints may differ or lag. | Everything live. | D4 |

## Tests and pass rules

Shock = |Δp| ≥ 10 points in one hour (unchanged). Bootstrap = resampling markets, 2,000 draws, 95% CI.

**Point-in-time watch rule** (used by D1–D3, D6): at hour *t* a market is *watched* if it has ≥ 24 hours of
price history before *t* and its probability one hour earlier was between 10% and 90%. Uses only the past.

| Test | Question | Pass rule | Required to build? |
|---|---|---|---|
| **D1** Point-in-time universe | Do V1, W3 and W5 still hold without the hindsight "contested" filter? | (a) V1 on **all 1,200 candidate markets** under the watch rule: mapped − placebo ratio > 0, CI > 0. (b) W3 AUC gain CI > 0 and (c) W5 whale CI above retail's mean, both using watched hours only. | Yes (a, b, c) |
| **D2** Stability over time | Do the effects hold quarter by quarter, including the latest? | (a) V1 mapped − placebo > 0 in ≥ 2/3 of calendar quarters with ≥ 20 markets, **and** > 0 in the most recent such quarter. (b) W3 rolling-origin (train on all hours before the quarter, test on the quarter): gain > 0 in ≥ 2/3 of quarters with ≥ 30 jumps, and pooled rolling gain CI > 0. (c) W5 whale − retail > 0 in ≥ 2/3 of quarters with ≥ 20 markets. | Yes |
| **D3** Alert value and load | Is an alert informative, and how many would a user get? | (a) Value: share of alert hours where the related asset makes a big move (above its own 80th-percentile hourly move) minus the same share for placebo assets > 0, CI > 0. (b) Load, reference portfolio SPY, QQQ, TLT, GLD, USO, BTC-USD, over the last 180 days of data: ≥ 1 alert on ≥ 50% of days **and** 95th-percentile alerts/day ≤ 30. | Yes |
| **D4** Live feasibility | Can the app get what it needs, live, fast enough? (run on the laptop) | All four sources reachable; median age of the latest trade across the 50 most-traded watched markets ≤ 60 min; BTC-USD latest bar ≤ 90 min old; one full refresh (market list + 50 markets' prices and trades + 6 assets) ≤ 120 s. | Yes |
| **D5** Daily resolution | Does it still work for someone who only looks once a day? | Daily version of V1 (day-level |Δp| ≥ 10 points vs daily asset |return|): mapped − placebo > 0, CI > 0. | No: decides whether the app gets a **daily digest** |
| **D6** Generality across event types | Is the effect broad, not one group? | V1 mapped − placebo > 0 in ≥ half of the groups with ≥ 10 markets, **and** leaving out any single group keeps the CI > 0. | Yes |

**Build rule:** D1, D2, D3, D4 and D6 all pass → build prototype v1. Any of them fails → no build; write down
why, propose an improvement, and test it as D-fix-n with its own pass rule written before running.

## Results (run 2026-11-27 02:17, `results/20261127-0230_daily_events`, D4 from `results/20261127-021157_live_check`)

| Test | Verdict | Result |
|---|---|---|
| D1 Point-in-time universe | **pass** | V1 +0.22× (CI +0.13 to +0.32, 350 markets with watched shocks); W3 gain +0.040 (CI +0.027 to +0.055); W5 large wallets +0.84 points vs retail +0.09 |
| D2 Stability over time | **pass** | V1 positive in 6/6 quarters with ≥ 20 markets (latest, 2026 Q2: +0.09×, the weakest); W3 positive in 8/8 quarters, pooled +0.049 (CI +0.040 to +0.060); W5 large > retail in 8/8 quarters |
| D3 Alert value and load | **pass** | Related asset makes a top-20% move after 24% of alerts vs 17% for unrelated assets (+7.0 points, CI +4.3 to +9.6). Reference portfolio: ≥ 1 alert on 56% of days, median 1/day, 95th percentile 8/day |
| D4 Live feasibility | **pass** | All 4 sources up; refresh 21 s for 50 markets + 6 assets; median newest trade 19 min old; 45/50 markets traded in the last hour |
| D5 Daily resolution | **pass** | Day level +0.23× (CI +0.16 to +0.29); without crypto-price markets +0.10× (CI +0.04 to +0.16) → daily digest included |
| D6 Generality | **pass** | Positive in 6 of 7 groups; **US politics is negative (−0.18)**; leave-one-group-out lowest CI +0.10 |

**Decision:** all required gates pass → build prototype v1, with a daily digest.

### What the results do *not* show (limitations that remain)

1. **Recent data is thin.** 2026 Q3 has 15 markets and Q4 has 5 (Q4 is −0.15, too few to judge). The latest quarter
   with enough markets (Q2) is the weakest positive one. → The app records every alert it raises and scores it
   against what the asset did next, so a forward track record builds up from day one.
2. **The hindsight filter turned out not to matter much**, because markets outside the band rarely produce watched
   shocks: only 8 of the 350 markets in D1 came from markets the old filter dropped. D1 confirms the watch rule
   is safe; it is not evidence about very low-probability markets.
3. **US-politics links are unreliable** (−0.18). The app shows them labelled "weak link", not as risk alerts.
4. **Alert value is modest:** 24% vs 17% big-move rate. An alert means "elevated risk", not "the asset will move".
5. **Alert counts are a lower bound** (sampled markets; L5) and stock assets only react in US trading hours (L6).
6. **No direction or trade advice** (L8): the direction hint stays a weak hint (≈ 53%).
7. D4 was run on a US holiday (Thanksgiving), so stock-quote freshness was not tested; BTC was.

## D-fix-1 · Keyword-matching bug (found while building, 2026-11-27 02:35, before rerunning)

**What happened.** The first prototype screen linked *"Will the Edmonton Oilers win the Stanley Cup?"* to oil
and gold. The event-to-asset keywords were matched as plain substrings, so "Oilers" matched *oil*, "Borussia"
matched *Russia* and "Senators" matched *NATO*. Of the 1,200 candidate markets, **62 (5%)** were linked wrongly,
mostly sports. All earlier T2 results (V1–V5, W0–W6, D1–D6) include this noise.

**Fix.** Keywords are now matched as whole words; a trailing `*` allows longer forms ("iran*" matches "Iranian").
Markets left with no group are dropped.

**Retest (pass rules unchanged, fixed before rerunning).** Rerun the `daily` suite D1–D6 with the corrected
links. The build decision stands only if D1, D2, D3, D4 and D6 still pass. False links act like extra placebo
pairs, so the effects should stay the same or get stronger; if they get *weaker*, that is a warning sign
to report.

**D-fix-1 result** (`results/20261127-0236_daily_events_fix1`): all six still pass, and the effects are
slightly stronger, as expected once false links are removed.

| Test | Before fix | After fix |
|---|---|---|
| D1 | V1 +0.22× (CI +0.13 to +0.32); W3 +0.040; W5 +0.84 vs +0.09 | V1 +0.24× (CI +0.14 to +0.33); W3 +0.048; W5 +0.82 vs +0.09 |
| D2 | V1 6/6 quarters (latest +0.09×); W3 8/8; W5 8/8 | V1 6/6 (latest +0.12×); W3 8/8; W5 8/8 |
| D3 | 24% vs 17% (+7.0, CI +4.3 to +9.6); alerts on 56% of days | 25% vs 18% (+7.5, CI +4.6 to +10.3); 55% of days |
| D5 | +0.23× | +0.23× (without crypto-price markets +0.11×) |
| D6 | 6/7 groups; US politics −0.18 | 6/7 groups; US politics −0.12 |

The app uses the corrected matching and the model exported from this run.

## D-fix-2 · Early warnings fired too often in busy markets (found on the first live scan, 02:41)

**What happened.** The first live scan flagged 13 of 35 watched markets, against about 5% expected. The live
list is the 60 *busiest* markets. In the research data, the single threshold (top 5% of all hours) flags busy
markets far more often: in markets with a $250+ trade in most hours, 19% of hours were flagged (lift 4.9×),
against 1% of hours in quiet markets (lift 33×). One threshold was fine for the pooled test, but it is wrong
for a daily tool that mostly watches busy markets.

**Fix (decided before checking it out of sample).** One threshold per activity level (share of the previous
48 hours with any $250+ trade: ≤ 10%, 25%, 50%, 75%, 100%). Each level flags its own top 5%. The model's
coefficients are unchanged. Pass rule: on the later half, with thresholds set on the earlier half, every level
flags 3–8% of hours with lift ≥ 3×.

**Result.** Pass. Later half, by activity level: flagged 5.1%, 5.3%, 5.3%, 5.3% and 3.7% of hours. Lifts were
12.0×, 13.2×, 13.5×, 13.7× and 15.5×; overall, 5.0% of hours were flagged with a 12.8× lift. In the busiest
markets, a flagged hour is followed by a jump 15–18% of the time. The app now shows that chance, not a multiplier.

## D7 · Live calibration of the early warning (pre-registered 02:58, before running on live data)

After D-fix-2, the live scan still flagged 12 of 35 watched markets in one snapshot. One snapshot is noisy:
replaying single days of research data hour by hour gave flag rates of 2.0–11.4% (10 random days, median
4.6%), with individual hours up to 24%. So the test uses a full day, not a snapshot.

**Test.** `python -m walletlens calibrate` (double-click `calibrate.bat`) takes the 60 busiest watched live
markets and replays the last 24 hours, flagging each watched market-hour exactly as the app does.
**Pass:** the flag rate falls within 2–12%, the range seen in research days. **If it fails**, the early warning
is hidden in the app (alerts and pressure stay) until the cause is found.

**D7 result (02:52, `results/20261127-025155_live_calibration`): FAIL.** 17.6% of 908 watched live
market-hours were flagged; a repeat at 02:55 gave 18.6%. As pre-registered, the early warning is hidden
until fixed.

**Diagnosis (02:56).** The live price features were about 2.5 times the research values: mean |hourly move|
0.013 vs 0.005, and recent volatility 0.013 vs 0.005. The wallet features were close to research
(wallets_z mean 0.07 vs 0.02). The live app fetched prices at 10-minute resolution (`fidelity=10`), but the
research used hourly points (`fidelity=60`). The finer, noisier series inflated both price features. Over-flagging
was worst in quiet markets (45% and 29% in the two lowest activity levels), where the price features carry the
most weight.

**D-fix-3.** Live prices are now fetched hourly (`fidelity=60`), and the warning is computed on the last whole
hour, exactly as in the research. Jump alerts still use the current price. Replay parity after the fix: 4.0%
of hours flagged; jump next hour 5.2% after a flag vs 0.02% otherwise. **Retest:** D7 again on live data,
same pass band (2–12%), same rule (if it fails, the warning stays hidden).

**D7 retest after D-fix-3 (02:58, `results/20261127-025815_live_calibration`): FAIL again.** 16.0% of 904
market-hours were flagged. The live price features are still about twice the research values at hourly
resolution (mean |hourly move| 0.011 vs 0.005). Live markets genuinely move more per hour than the
resolved research markets did. The busier activity levels are fine: 4.2% and 4.0% flagged. The quiet levels
over-fire: 44% and 27%. On the positive side, all 4 jumps in those 24 hours came right after a flag. That is
too few to judge, but it is not a sign the model is wrong. It is a sign that the research thresholds do not
transfer to today's market mix.

**Decision for v1.** The early warning runs in **shadow mode**: it is computed and logged every scan to
`data/app/warnings_shadow.jsonl`, but not shown. Jump alerts, large-wallet pressure and the cluster mix are
unaffected and stay on.

**Proposed improvement (to test, not yet adopted).** Set the threshold relative to live markets: flag the top
5% of scores among the watched live market-hours of the previous week, within each activity level. Because
this fixes the flag rate at 5% by construction, the flag rate is no test of it. The test is precision: after
≥ 2 weeks of shadow logs, a flagged hour must be followed by a 10-point jump at least 3× as often as an
unflagged one (CI above 1), with ≥ 20 jumps in total.
