# 04 · Can wallets help the event-risk monitor? (W0–W5)

*Pre-registered 2026-11-27, before any event-market trades were downloaded. Suite: `wallets`.*

The final topic (T2) uses Polymarket event probabilities as a risk monitor. Earlier tests found no
wallet that predicts *outcomes* or *spot prices*. This round asks a narrower, product-shaped question:
**can wallet data make the monitor's alerts more useful?**

## Data

* Trades of **≥ $250** in the 689 contested event markets (newest 30,000 per market). A $10 floor was
  tried first, but the largest markets have more than 60,000 such trades each.
* Wallet types, decided with information available at the time of each trade:

| Type | Definition |
|---|---|
| whale | the trade is worth ≥ $5,000 |
| skilled | top 10% of shrunk edge over event markets that closed earlier (≥ 3 markets) |
| new | first trade in these markets less than 3 days earlier |
| frequent | already ≥ 200 trades in these markets |
| retail | none of the four above (baseline) |

* **The team's wallet pipeline**, reused unchanged from the FYP repo (`walletlens/wallet_pipeline`),
  on trades before the median market close:
  1. sniper / same-owner grouping (co-timed trades within 1 s on ≥ 5 moments and ≥ 3 days, Jaccard ≥ 0.2)
  2. hard rules (≥ 10 trades, ≥ 3 active days, ≥ $100, ≤ 500 trades per day, few duplicates)
  3. behaviour features and KMeans clustering, frozen and applied to the later half
  Pipeline outputs are used as extra types: `linked` (same-owner group), `filtered_out` (fails the hard
  rules) and the behaviour clusters `C0…Ck`. They are reported as **secondary** results, because the
  pipeline was designed for Fed markets and is applied here as is.

## Directions and pass rules

| ID | Question | Test | Pass if |
|---|---|---|---|
| W0 | Enough data? | markets with trades; jumps with same-hour trades | ≥ 100 markets and ≥ 300 jumps |
| W1 | **Confirmation:** do assets react more to jumps that large wallets push? | asset reaction ratio (|r| ÷ normal hour), whale-backed vs not | difference > 0, 95% CI above 0 (markets resampled) |
| W2 | **Will it stick?** does who is behind a jump predict 24 h continuation? | four splits: whale-backed, skilled-backed, many wallets, new-wallet-driven | any split's 98.75% CI (Bonferroni, 4 tests) excludes 0, in either direction |
| W3 | **Early warning:** does unusual wallet activity this hour predict a jump next hour? | logistic model, price-only vs price + wallet activity; trained on earlier-closing markets, tested on later ones | AUC gain > 0, 95% CI above 0 |
| W4 | **Direction:** is V2's hint better when large wallets agree with the jump? | hit rate, agree vs not | difference > 0, 95% CI above 0 |
| W5 | **Whose buying leads?** | next-hour probability move after each type's net buying, later half only | a main type's 98.75% CI lies above retail's mean |

Secondary (pipeline) results never change a verdict; they are reported next to the main ones.

## What passing means for the product

| Passed | Feature in the monitor |
|---|---|
| W1 | alerts are ranked higher when large wallets back the jump |
| W2 | each jump is labelled "likely to stick" / "likely to fade" by who is behind it |
| W3 | an early-warning badge on markets with unusual wallet activity |
| W4 | the direction hint is shown only (or more strongly) when large wallets agree |
| W5 | the alert names the wallet type whose buying leads |
| none | wallets stay as descriptive context ("who is moving this market") |

---

## Results · 2026-11-27 (2.78 M trades ≥ $250 by 147 k wallets, 689 markets, 1,880 jumps with same-hour trades)

Team pipeline on these markets: 2 same-owner groups (sniper grouping finds little in slow event markets),
9,878 of 74,227 entities pass the hard rules, 3 frozen behaviour clusters:
C0 = active on many days and markets, trades both sides (market-maker-like);
C1 = long gaps, few trades per day (patient);
C2 = bursty, concentrated in one market.

| ID | Verdict | Result |
|---|---|---|
| W0 | pass | data as above |
| W1 confirmation | **fail** | assets react +0.01× more to whale-backed jumps (CI −0.28 to +0.36) |
| W2 will it stick | **pass, not robust** | jumps on average give back 3.5 points in 24 h; whale-backed jumps hold 3.9 points better (98.75% CI +0.2 to +7.6). With flows ending 15 min before the hour (W6): +2.3 (CI −1.5 to +6.1) |
| W3 early warning | **pass, robust** | out-of-time AUC 0.887 → 0.914 (gain +0.027, CI +0.018 to +0.038); the 5% most unusual hours are followed by a jump 12.8× as often. Driver: a surge in the number of distinct wallets. With the 15-min gap: +0.018 (CI +0.010 to +0.029) |
| W4 direction | **fail** | hit rate 52.3% when whales agree vs 53.6% otherwise |
| W5 whose buying leads | **pass, robust** | next hour the price follows whale buying by +0.42 points vs +0.05 after retail; skilled, new and frequent wallets do not beat retail. With the gap: whale +0.39 vs retail +0.03 |
| W5 secondary (team clusters) | — | all three behaviour clusters lean *against* the next move (C0 −0.16, C1 −0.05, C2 −0.13 points): they behave like liquidity providers, so their flow is a mild contrarian sign |
| W6 robustness | partial | Polymarket's hourly price equals the last trade at its timestamp (best offset 0 min), so no stale-snapshot leak; W3 and W5 survive the 15-min gap, W2 does not |

**Into the product:**
1. **Early-warning badge (W3):** flag markets where the number of distinct wallets trading this hour is unusually high for that market; a jump follows far more often than usual.
2. **Large-wallet pressure (W5):** show net $5k+ trade flow on each linked event; the probability tends to keep moving the way large wallets push it over the next hour.
3. **Wallet mix (team pipeline, descriptive):** show the share of flow from each behaviour cluster; heavy market-maker-cluster flow leans contrarian.

Not used: confirmation ranking (W1), "will it stick" labels (W2, not robust), direction boost (W4),
skilled-wallet signals (W5, and every earlier topic).

## W7 · Cluster surge → holding risk (pre-registered 2026-11-27 11:20, before running)

**Question.** When one wallet cluster suddenly trades far more than usual in the markets linked to a
holding, does the holding make a bigger move in the next hour? This asks about the *size* of the holding's
move, not the bet's direction. W5 already showed no cluster leads the bet's price.

**Setup.**
- Holdings: the 26 research assets.
- Linked markets: all markets whose group (whole-word matching) maps to the holding. US-politics markets
  are excluded (weak link, D6).
- Flow: for each holding, cluster (C0 market makers, C1 patient, C2 burst) and hour, the total dollars
  traded by that cluster's wallets across the linked markets, in the hour ending 15 minutes before the
  asset bar starts (data-delay gap).
- Surge: log(1 + flow) at least 2 above its trailing 48-hour mean for that holding and cluster, and flow ≥ $1,000.
- Outcome: the holding's |return| in the next hourly bar, divided by that asset's average |return| at the
  same hour of day. Hour of day is controlled because stocks and wallets are both busiest around the US open.
- Effect: mean outcome in surge hours minus mean outcome in other hours, per holding.
- Out of sample: clusters were fitted on trades before 2026-01-01, so the main test uses only hours after
  that date. The earlier period is reported for reference.

**Controls.**
- (a) **Placebo:** the same surge, computed on markets *not* linked to the holding. This catches "everything
  is busy" effects.
- (b) **Without jump hours:** drop hours where a linked market also jumped ≥ 10 points. This shows whether
  surges add anything beyond the existing jump alerts.

**Pass rule, per cluster** (all required; Bonferroni for 3 clusters, so 98.3% intervals):
1. Pooled effect > 0, with the interval above 0 (bootstrap by day).
2. Positive in ≥ 50% of holdings with ≥ 20 surge hours (the user's generality criterion: a majority, or
   about half, of holdings is enough).
3. Linked minus placebo > 0, with the interval above 0.
4. Still > 0 (point estimate) after dropping jump hours.

All-wallet and large-wallet ($5k+) surges are reported alongside, for comparison only.

### W7 result (run 2026-11-27 11:25, `results/20261127-1125_w7`)

The main test covers hours after 1 Jan 2026 (out of sample), with 22 holdings that have ≥ 20 surge hours.
Outcome 1.00 = a normal-sized move for that asset at that hour of day.

| Surge by | Next-hour move vs normal | 98.3% CI | Holdings positive | Placebo (unlinked markets) | Without jump hours | Verdict |
|---|---|---|---|---|---|---|
| **C0 market makers** | **+9.0%** | +2.6 to +15.8 | **86%** (19/22) | −2.6% | +7.9% | **pass** |
| C1 patient traders | +3.4% | −2.4 to +9.0 | 82% | +4.3% (no better than placebo) | +4.9% | fail |
| **C2 burst traders** | **+6.3%** | +0.7 to +12.4 | **68%** (15/22) | −7.4% | +6.5% | **pass** |
| *All wallets (reference)* | −0.9% | −6.6 to +5.1 | 65% | +1.8% | +0.3% | – |
| *$5k+ trades (reference)* | +8.1% | +2.3 to +14.1 | 68% | −7.4% | +9.2% | – |

**Reading.**
- A surge by market makers or burst traders in a holding's linked markets comes before a somewhat bigger
  next-hour move in that holding: about 6–9% bigger than normal.
- This holds for most holdings, not just a few pairs, and it is not explained by general busyness (the placebo
  is negative) or by the existing jump alerts.
- A surge in *all* wallets shows nothing, so the cluster split is what carries the signal. This is the first
  place where the team's clustering adds measurable value.
- The earlier period, which is in sample for the clusters, points the same way but weaker (+4.3% and +2.9%).

**Limits.**
- The effect is small (+6–9%), far below a jump alert's effect.
- Energy holdings go the other way: USO and XLE are negative for all three clusters, and GLD for C1 and C2.
- Only one out-of-sample period (2026). It must hold up in the live track record before the app treats it as more than a hint.

**Product implication (proposed, not built).** Each holding gets a small "cluster surge" note ("market makers
active in linked bets: moves tend to run about 9% larger than usual next hour"), shown as context next to the
jump alerts. Energy holdings are excluded until a reason is understood.
