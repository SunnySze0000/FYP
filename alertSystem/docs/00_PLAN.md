# 00 · Master plan

> **System workflow:** `docs/08_system_workflow.md` describes how EventLens works end to end. Update it in the same change whenever the product changes.

*The reference for what we are doing and why. Update the **Status** section at every step. Decisions are appended to the log at the bottom, never rewritten.*

## Value proposition (2026-11-27, from S1–S3 in docs/09)

**EventLens is an event-risk radar for your holdings, strongest while the US market is closed.** It watches
the Polymarket bets linked to each holding, says when one of them moves, and shows what that has meant for the
holding before. It is not a trading signal: it gives no direction, and during US trading hours it is not early.

1. **Early while the US market is closed (headline).** 72% of event jumps (1,672 non-crypto jumps) happen
   outside US trading hours. Then the bet moves first, and the linked holding's first hour at the next open is
   bigger than usual: +0.28 to +0.31 of a normal hour vs unrelated assets (S2). For an investor in Asia, this
   covers most of the day.
2. **Explains moves during trading hours.** Stocks usually move before or with the bet in trading hours (S1),
   so here EventLens says *why* a holding is moving: linked assets move 1.4–1.8× normal in jump hours (V1, D1).
3. **Says how long the risk lasts.** After an intraday jump, linked holdings keep moving more than unrelated
   assets for 2–3 hours (+0.18, +0.22, +0.12), which is useful for sizing, stops and timing orders.
4. **Wallet patterns come first.** Market-maker and burst-trader surges, and wallets trading several linked
   bets at once, come before 6–21% larger next-hour moves, tested with a 15-minute data delay (W7, W9b).

**Not offered:** direction or buy/sell calls (S3, M3, V2/V4 ≈ 50%). Intraday alerts are worded "risk is live
now", not as forecasts.

**Product consequences:**
- "Watch the open" (D4) is the headline feature.
- The daily digest centres on what happened to the holdings' events while the US market was closed.
- Intraday alerts are framed as explanations.

## What an alert means, and what it doesn't (read this before presenting EventLens)

**An alert does NOT mean the price will go up or down, and it does NOT guarantee a bigger move.** It means the
*chance* of an unusually big move is higher than usual, like a storm warning.

- **On average, yes:** linked holdings move about 1.4× their normal hourly size in jump hours, and the overnight
  effect at the open is clear (CI +0.20 to +0.38). These averages are solid over hundreds of events.
- **On a single alert, often not:** a big move (the holding's top 20% of hours) followed only **25%** of alerts,
  against **18%** for unrelated assets. So **about three in four alerts are NOT followed by an unusually big move.**
- **Real days:** of 257 days with a linked jump both overnight and during the session, **72 (28%)** look like the
  illustrative diagram (bigger open *and* a > 1.5× move near the intraday jump), against **21.6%** of 7,086
  comparable days with no linked jump. 53% opened bigger than normal (45% on no-jump days). The pattern is
  more common, not certain. See `docs/11_illustrative_day.md`.
- **Direction is a coin flip (≈ 50%).** Never present an alert as a reason to buy or sell.
- **During US trading hours the stock often moves before the bet does,** so part of the move may already have happened.

### How strong is the effect? (all measures side by side)

| Measure | With a linked jump | Without | Difference |
|---|---|---|---|
| Chance a day looks like the diagram (bigger open **and** a > 1.5× move near the intraday jump) | 28% | 21.6% | +6 points (1.3× as likely) |
| Chance of a **top-20% move** in the alert hour | 25% | 18% (unrelated assets, same hour) | +7 points (1.4× as likely) |
| **Average size** of the holding's move in jump hours | 1.4–1.6× normal | 1.0× | **+40–60%** |
| First hour at the open after an overnight jump | 1.16× | 0.96× | +20% |
| Day with 10+ linked jumps (daily volatility) | 1.46× | 0.99× (10+ unrelated jumps) | +47% |
| Linked-jump hour after controlling for the VIX level and recent volatility (doc 12) | +17% bigger move (CI +10 to +24) | unrelated-jump hours: +13% | linked − unrelated +4% (CI −3 to +11): **not significant** |
| Linked holdings vs the other holdings **in the same hour** (doc 13; cancels the VIX and market-wide news) | +7% (CI +2 to +12); overnight → open **+12% (CI +4 to +20)**; intraday +2% (n.s.); 2+ linked jumps +9% | other holdings, same hour | **PASS**: specific but small, mostly at the open |

**VIX check (doc 12, FAIL on specificity):** jumps carry information beyond the VIX, but at the hourly level most of
it is "event news is moving markets", which unrelated jumps share. The extra for the holding's own topics is
small and uncertain.

**What is a "top-20% move"?** For each holding, take every past trading hour and rank the hours by how much the
price moved, up or down, ignoring the sign. The top-20% hours are the fifth with the biggest moves. For a
typical large ETF, that is roughly any hour that moves more than about 1.3–1.5× its average hour. By
definition, 20% of all hours are top-20% hours. So "25% of alert hours are top-20% moves" means alert hours
land in the biggest-move group a bit more often than chance (18–20%).

**Reading:** the *chance* that a single alert turns into a big move rises only modestly, so most alerts end
calm. The *average size* of moves rises clearly, because the cases that do react tend to react a lot. As a
trading signal this is weak; as a risk monitor it is a consistent, tested tilt. **Open question:** we have not
yet checked whether options and the VIX already price this in (see the proposed VIX-control test).

## Evidence map: what EventLens can and cannot do, and which test shows it

*Plain-language summary, kept up to date. Test IDs link to the docs: T/F/E = 01–02, V = 02, W = 04/06,
D = 05, M = 06, S = 09, charts = 10–11, VIX = 12, same-hour = 13.*

### A. What EventLens can do

| # | What it does (value / function) | Supported by | Result in one line | What it means for the product |
|---|---|---|---|---|
| A1 | **Names which event matters to your holdings, with live odds.** Each holding is linked to Polymarket bets by name and by topic; every link is checked on the holding's own price history. | V1, D1, D6, D-fix-1, history check in doc 07 | Linked assets move 1.4–1.8× normal in hours when their bets jump; the effect holds in 6 of 7 topics and without hindsight. | Core feature. Show the bet, its odds and why it is linked. US-politics links are labelled "weak". |
| A2 | **Warns before the US open when a linked bet moved overnight** (headline). | S2, same-hour test (doc 13), real days (doc 11), V2 chart 4 | Next-open first hour is bigger after an overnight linked jump (1.16× vs 0.96×); vs other holdings that same hour **+12%** (CI +4 to +20). 72% of jumps happen while the market is closed. | "Watch the open" (D4) is the headline feature. Strongest and most holding-specific evidence we have. |
| A3 | **Flags hours when event news is moving markets, beyond the VIX.** | VIX control (doc 12) | Hours with a bet jump move about 13–17% more than the VIX and recent volatility predicted. | Useful as a general "news is happening" radar, even beyond your own links. **V3 (doc 15):** against each sector's own fear gauge, only the overnight part survives (+13%); intraday, a jump says what the gauge already says. |
| A4 | **Explains why a holding is moving during trading hours.** | S1, V1 | Linked holdings are already moving around the jump hour (peak the hour before). | Intraday alerts are worded as an explanation ("this event is moving now"), not a warning. |
| A5 | **Says how long the extra risk lasts.** | S1 (hour-by-hour profile) | Extra movement fades over about 2–3 hours after a jump. | Show "risk stays raised for ~2–3 h". |
| A6 | **More linked jumps → more risk.** | Same-hour test (doc 13), V2 chart C | One linked jump +6%, two or more +9% (same hour); daily 0.98× (none) → 1.46× (10+). | Show the number of linked jumps; use it in M2. |
| A7 | **Shows who is moving the odds (wallet layer).** | W5, W7, W9b | Large-wallet buying leads the bet's price (+0.82 vs +0.09 points). Market-maker / burst-trader surges and wallets trading several linked bets come before 6–21% bigger next-hour moves in the holding. | Large-wallet pressure and per-holding wallet notes (D2, D3), shown as context. |
| A8 | **Works for your own portfolio (import any US large stock or ETF).** | History check (doc 07), D1 | 13 of 26 research links confirmed by history; wrong links are dropped. | Portfolio import with checked links. |
| A9 | **Works daily and live, and keeps testing itself.** | D2, D3, D4, D5, live track record (V1) | Holds quarter by quarter; about 1 alert a day for a 6-holding portfolio; live refresh 21 s; every alert is logged and scored. | Daily digest; Track record page. |

### B. What EventLens cannot do

| # | What it cannot do | Shown by | Result in one line | What it means for the product |
|---|---|---|---|---|
| B1 | **Tell you which way the price will move.** | V2, V4, W4, M3, S3 | Every direction test is about 50% (a coin flip). | No buy/sell advice, no up/down arrows. |
| B2 | **Guarantee a big move after an alert.** | D3, real days (doc 11), effect table | A top-20% move follows 25% of alerts vs 18% otherwise; about 3 in 4 alerts end calm. Only 28% of linked-jump days look like the textbook picture (vs 21.6%). | Alerts say "higher chance", never "will". |
| B3 | **Warn you early during US trading hours.** | S1, same-hour test (doc 13) | Intraday the stock usually moves before or with the bet; no holding-specific effect intraday (+2%, n.s.). | Intraday = explanation only. |
| B4 | **Predict exactly how big a move will be.** | M2 | The model was no better than a fixed "× normal" per holding. | Show the historical average; retry M2 with jump count and event kind. |
| B5 | **Act as a trading signal on crypto or inside Polymarket.** | T1 (C1–C3), F (E2–E4) | Polymarket follows bitcoin by about a minute; copying "smart" wallets lost money. | Not offered. |
| B6 | **Give an early warning from unusual wallet activity (yet).** | W3, D7 | Worked in research, but over-fires on live markets (16–18% of hours flagged). | Hidden (shadow mode) until W8 passes on live data. |
| B7 | **Pick skilled wallets or link bets with a home-made text model.** | W1, W10, M1 | No wallet group beat others on direction; the text model linked worse than keywords. | Keyword links + history check; clusters shown as context only. |
| B8 | **Fully separate "your holding's news" from "big news in general" at all times.** | VIX control (doc 12) | Beyond the VIX, linked and unrelated jumps both raise movement; the holding-specific extra is only clear at the open. | Wording: "event news is moving markets, and this one is linked to your holding". |

### C. Test register (one line per test)

| Test | Question | Result | Verdict | Implication |
|---|---|---|---|---|
| T1 crypto (C0–C3) | Do Polymarket crypto bets lead BTC/ETH? | They lag spot by about 1 min; trading lost 6 bps | Fail | Dropped the crypto topic |
| F (E2–E4) | Can wallets' skill be copied inside Polymarket? | Skill does not persist; copying lost 3.8% | Fail | Dropped the Polymarket-trading topic |
| V1 | Do event jumps move linked assets more? | +25% (CI +15 to +34) vs placebo assets | Pass | Core of the product |
| V2, V4 | Do jumps predict direction? | 53%, unstable | Fail | No direction |
| V5 | Is V1 look-ahead free? | Placebo 50.5%, no look-ahead | Pass | Trust V1 |
| W0–W2 | Wallet data; hedge ratio; jump persistence | Data OK; W1 fail; W2 not robust | Mixed | Not in product |
| W3 | Wallet early warning (research) | AUC 0.887 → 0.917 | Pass | Became the early warning… |
| D7 | …does it work on live markets? | Flags 16–18% of hours (2–12% expected) | Fail | Shadow mode; W8 fix |
| W4 | Large wallets improve direction? | 52% vs 54% | Fail | No direction |
| W5 | Large-wallet buying leads the bet? | +0.82 vs +0.09 points | Pass | Pressure feature |
| W6 | Robust to a 15-min data delay? | W3, W5 hold; W2 not | Partial | Only W3/W5 kept |
| W7 | Cluster surge → bigger holding move? | C0 +9% (86% of holdings), C2 +6% (68%) | Pass | Wallet notes (D2) |
| W9b | Wallets trading several linked bets? | +21% (83% of holdings) | Pass | Wallet note (D3) |
| W9a/c/d/e, W10 | Other wallet ideas; supervised wallet model | No effect beyond chance | Fail | Not in product |
| D1–D6 | Daily-use checks (no hindsight, stable, alert value, live, daily, all topics) | All pass, before and after the keyword fix | Pass | Build approved |
| M1 | Text model for links | Worse than keywords | Fail (open) | Keywords + history check; retry with more data |
| M2 | Predict move size | No better than fixed ratio | Fail (open) | Retry with jump count, event kind |
| M3 / S3 | Direction model / direction after jump | ≈ 50% | Fail | No direction |
| S1 | Does the stock move after the jump (intraday)? | Stock moves most the hour before | Fail | Intraday = explanation |
| S2 | Overnight jump → bigger next open? | +0.28 to +0.31 (CI > 0) | Pass | Headline feature |
| Charts (doc 10–11) | Visible across history / real days? | Pooled dose-response clear; per holding weak; 72 of 257 days match (28% vs 21.6%) | Supportive | Honest "higher chance" wording |
| VIX (doc 12) | Beyond the VIX, is the effect specific? | Beyond VIX yes (+17%); specific part n.s. (+4%) | Fail (specificity) | Wording change |
| Same hour (doc 13) | Linked vs other holdings, same hour? | +7% overall; **+12% at the open**; intraday none; 2+ jumps +9% | Pass | Supports D4 and jump-count feature |
| V4 clean links (doc 14) | Is the effect stronger on direct links? | Direct **+10.6%** (CI +4 to +18), overnight **+16%**; loose links +2% (n.s.); gap +8.7 pts, CI just touches 0 | Pass (rule 1), narrow fail (rule 2) | Direct links shown first and labelled in D4; M1 targets direct links |
| V3 sector gauges (doc 15) | Still there after oil/gold/China/Nasdaq volatility gauges? (bond gauge too short, dropped) | All hours +5.4% (CI −2 to +13): about half absorbed. **Overnight +13% (CI +1.5 to +26) survives**; intraday 0 | Fail (all hours), **Pass (overnight)** | D4 stands; no "beyond sector fear" claim for intraday alerts |

## The brief

- **Must use:** Polymarket, and wallet-level data.
- **Must end in:** a trading or financial helper tool.
- **User preference (2026-11-26):** the advice should be for **actual financial markets** (stocks, crypto, rates and so on). Advice for trading on Polymarket itself is only a **fallback** if the preferred direction is shown not to work.
- **Rule:** do **not** build the app until a research gate has passed. Every claim the app makes must come from a logged result in `results/`.

## Lessons carried over from the earlier FYP work

These are why the first attempt (Fed odds → SPY) failed, and the new topic must avoid them:

1. **Too few independent events.** About 8 Fed meetings a year: no test has power.
2. **Near-certain outcomes.** By decision day the odds are about 99%, so there is nothing left to learn.
3. **Mismatched clocks.** Polymarket trades 24/7, stocks trade 6.5 hours a day. Daily alignment blurs any lead or lag.
4. **Wallet "skill" is mostly style.** Pilot E2: persistence ρ = 0.28 falls to 0.01 once favourite-buying style is controlled.

## Candidate topics (iteration 2)

| ID | Topic | Real-market advice | Fixes lessons | Main risk |
|---|---|---|---|---|
| **T1** | **Polymarket crypto markets as a lead signal for BTC/ETH.** Hourly and daily "Bitcoin up or down" and "above X" markets. Does the flow of skilled wallets in them predict the next minutes or hours of spot BTC/ETH? | Yes: spot or perpetual BTC/ETH | 1: thousands of markets. 2: coin-flip markets, real disagreement. 3: both trade 24/7, so minute-level alignment works. 4: skill is measured on many quick resolutions. | Polymarket probably *follows* spot (arbitrage bots), so there may be no lead. |
| T2 | **Event-probability shocks across many event types** (tariffs, geopolitics, elections, recession, Fed path 1–6 months out) mapped to the assets they affect (oil, defence, China ETFs, Treasuries). Measure the asset's sensitivity to a 10-point probability move, and whether skilled wallets move first. | Yes: risk exposure and hedge ratios for a portfolio | 1: many event types. 2: chooses contested markets. 3: uses intraday asset data where possible. | Hard to map events to assets; little intraday stock data for free. |
| F | **Smart money inside Polymarket** (the WalletLens pipeline already built). | No: it advises Polymarket trades | Yes | Fallback only. |

**Proposed order:** T1 first (cleanest test, biggest sample, data is free), then T2 if T1 fails, then F.

## Gates: proof before building

Each gate has a pass rule fixed in advance. Failing a gate sends us to the next candidate topic, not to a looser test.

| Gate | Question | Pass rule |
|---|---|---|
| G0 Data | Can we get the data at the resolution the test needs? | ≥ 500 resolved markets with wallet-level trades, and spot prices at 1-minute resolution covering the same period |
| G1 Market lead | Does the Polymarket price (or its change) predict the *next* spot return better than spot's own recent returns? | Out-of-sample, walk-forward by day: positive incremental R² or hit rate, with a CI excluding 0, at a horizon ≥ 5 min |
| G2 Wallet lead | Does flow from skilled wallets (skill judged only on earlier markets) add to G1? | Incremental predictive power of skilled flow over plain flow and price, CI excluding 0 |
| G3 Tradable | Does a simple rule built on G1/G2 make money in spot after fees and delay? | Mean return per trade > 0 with CI excluding 0 at realistic costs (≥ 5 bps round trip) and ≥ 1 min delay |
| G4 Build | Is there something worth putting in front of a user? | Passing G3 gives a **signal tool**. Passing G1/G2 but not G3 gives a **risk/insight tool**, stated honestly. Nothing passed means pivot. |

## T2 gate definitions (events)

| Experiment | Pass rule |
|---|---|
| V0 data | ≥ 100 contested event markets aligned with hourly asset prices |
| V1 same-hour sensitivity | In shock hours (|Δp| ≥ 10 points), related assets' |return| ratio (shock ÷ normal) exceeds unrelated assets', CI above 0 |
| V2 next-hour lead | Next-hour direction hit rate > 50% with CI above 50% (sign learned from earlier hours only) |
| V3 skilled wallets lead | Next-hour probability move in the direction of skilled-wallet flow > 0, CI above 0 |
| V4 stable exposures | Exposure sign agrees between first and second half of a market's life > 50%, CI above 50% |

## Work breakdown (current, same IDs as the task list)

| ID | Task | Status | Depends on / blocked by |
|---|---|---|---|
| **D – Dashboard** | | | |
| D1 | Portfolio import with checked links | Done (v1.1) | – |
| D2 | Wallet note: cluster surge (W7) per holding | Done (v1.1) | – |
| D3 | Wallet note: wallets on several linked bets (W9b) | Done (v1.1) | – |
| D4 | "Watch the open" after overnight linked jumps; intraday alerts reworded | Done (v1.2); V3 confirms the overnight effect | – |
| **W – Wallet research** | | | |
| W8 | Fix and retest the wallet early warning | Waiting | Blocked by V1 (≈ 2 weeks of live logs) |
| **M – Models** | | | |
| M1 | Learned bet-to-holding links (own text model) | Open | Blocked by V5 (more markets). V4 done: train on direct links first |
| M2 | Move-size model with jump count, event kind, overnight flag | Open (optional) | Soft-blocked by V5 |
| M4 | **Volatility model on the whole jump stream** (keep open: big payoff if it works). Takes every jump, not one at a time; first target "will the next hour / the open be a top-20% move?" (yes/no), then size, then direction. Design below. | Open, **priority model** | Blocked by V5 (training data) and V1 (live out-of-sample test); V6 helps (5-min targets) |
| **V – Validation** | | | |
| V1 | Run EventLens live ≈ 2 weeks (track record) | Running. From 2026-11-27 it runs from `FYP/alertSystem` (`restart.bat`, v1.2); live logs copied over from fyptest1, which is no longer used | – |
| V3 | Controls with oil/gold/bond/China/Nasdaq volatility gauges (doc 15) | Done: overnight effect survives (+13%), all-hours effect half absorbed | Bonds not tested (MOVE gauge too short) |
| V4 | Same-hour test on the cleanest links only (doc 14) | Done: direct +10.6%, loose none | – |
| V5 | Collect the full Polymarket universe: up to 4,000 event markets, max 700 per topic (was 1,200 / 200), `fyptest1/config/v5.json`; the old dataset is backed up to `events_before_v5` | Ready: run `tonight_v5v6.bat` | Long laptop run (hours); blocks M1, M2, M4 |
| V6 | 5-minute stock data around jumps (`scripts/v6_download_5m.py`, merges into `data/raw/prices_5m/`; Yahoo keeps 60 days, so rerun every few weeks to build history) | Ready: run `tonight_v5v6.bat` | – |
| **H – Housekeeping** | | | |
| H1 | Clean up `_stage` folders in fyptest1 | Done (≈ 119 MB removed) | – |
| H2 | Delete the temporary `tonight_v5v6.bat` and `fyptest1/config/v5.json` (keep `scripts/v6_download_5m.py`) | Open | After V5 and V6 have run |
| H3 | Fold `docs/TONIGHT_2026-11-27.md` results into numbered docs (M1 → doc 16, M4 → doc 17), then delete it | Open | After tonight's run |
| Rule | Update `docs/08_system_workflow.md` with every product change | Standing | – |

### M4 design (to be pre-registered before training)

M4 differs from M2: M2 sized the move after a single jump; M4 reads the **stream** of jumps (and other signals)
up to now and forecasts the holding's next hour or next open. It is tested as a grid of input × output
combinations, each against the same baseline, with walk-forward splits (train on the past, test on the next
block, never shuffle) and a final check on V1 live data.

| | Options to compare |
|---|---|
| **Inputs** | (a) baseline only: the holding's own recent volatility (autoregressive, HAR-style 1 h / 1 day / 1 week averages) + VIX; (b) + linked jumps: count in the last 1 / 6 / 24 h, size, direct vs loose (V4), event group, overnight flag, time since last jump; (c) + wallet signals: C0 / C2 surges, wallets on several linked bets, $5k+ net flow; (d) + sector gauge (V3) |
| **Outputs** | (1) yes/no: next hour (or the open) is a top-20% move; (2) size: \|return\| ÷ normal; (3) direction: up/down (expected to fail, as S3, M3) |
| **Models** | logistic / linear regression first; then a small gradient-boosted tree; an autoregressive sequence model only if the simple ones show signal |
| **Pass rule** | inputs (b)–(d) beat input (a) out of sample: for (1) higher AUC and Brier skill, CI above 0; for (2) lower error, CI above 0; for (3) accuracy CI above 50% |
| **Product use** | if (1) passes, the Watch-the-open and holding views show "chance of a big move" from M4 instead of the fixed +12% / +16% |


## Status

- [x] Foundation built and tested (11 tests, synthetic planted-skill and null checks)
- [x] Pilot on Fed data (`results/*_pilot_fed`): style, not skill; inconclusive on H2/H3
- [x] User: research all topics in parallel; one script runs every collector (2026-11-26)
- [x] T1 collector, minute panel, experiments C0–C3 (tested: planted lead found, null rejected)
- [x] T2 collector, event-asset analysis, experiments V0–V4 (tested: planted link found, null rejected)
- [x] F collector and experiments E0–E5; `run.ps1 all` runs collectors in parallel, then all research
- [x] Quick trial run on the laptop; collector and research bugs found and fixed (see decision log)
- [x] Full collection paused 2026-11-26 19:56 (resume: double-click `full.bat`). Done: crypto 5,239 markets / 4.6 M trades + BTC/ETH 1-min spot; events 669 contested markets / 1.15 M hourly prices; Polymarket 300 contested markets' trades. Still to do: rebuild the universe dataset, re-select event markets from the full candidate list, run all research
- [x] Preview of T2 (events, trial market list): V1 passes only because of crypto-price markets (+0.09×; without them +0.02×, CI −0.05 to +0.09); V2 and V4 fail
- [x] Full research run 2026-11-27: T1 fails, F fails, T2 passes V1 (robust) and V2 (weak); wallets add nothing anywhere (see 02_research_log.md)
- [x] Topic decision recorded: **T2, event-risk monitor** (docs/01_topic.md, revision 2)
- [x] Wallet round W0–W6 (docs/04_wallet_directions.md): W3 early warning and W5 large-wallet pressure pass robustly; team clusters used descriptively
- [x] Daily-use applicability check D1–D6 (docs/05): all pass; keyword-matching bug found and fixed (D-fix-1), all still pass
- [x] Prototype v1 built: **EventLens** event-risk monitor (`python -m walletlens app`, or double-click `eventlens.bat`)
- [x] D7 live calibration of the early warning: FAIL twice (16–18% of hours flagged vs 2–12%); price-resolution bug fixed (D-fix-3), still fails → early warning in shadow mode
- [x] v1.1: portfolio import, wallet notes, 24 h backfill, version stamps (docs/07); system workflow doc (docs/08)
- [x] Research round 3 (docs/06): W9b passes; W10, M1, M2, M3 fail
- [x] Sequence tests (docs/09): S2 passes (overnight → open), S1 and S3 fail
- [x] Charts and real days (docs/10–11): pooled dose-response; 72 of 257 days match the textbook picture
- [x] VIX control (docs/12): beyond the VIX yes, holding-specific part not significant
- [x] Same-hour test (docs/13): +7% overall, +12% at the open, none intraday → supports D4
- [x] Copied to `FYP/alertSystem`, branch `alert-system`; work continues there
- [x] V4 clean links (docs/14): direct links carry the effect (+10.6%, overnight +16%); loose links none
- [x] D4 "Watch the open" built (v1.2, docs/08 section 6b)
- [x] V3 sector gauges (docs/15): overnight effect survives (+13%), intraday effect is shared with the sector gauge
- [ ] Open work: see the Work breakdown table above (V1 running)
- [ ] Later ideas: push notifications for overnight jumps; more holdings per topic. (A direction hint is ruled out: B1 in the Evidence map.)

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-11-26 | Iteration 1 topic: smart money inside Polymarket (F) | Wallet data and target live in the same market |
| 2026-11-26 | Pilot on 31 Fed markets: apparent skill is favourite-buying style | E2 ρ 0.28 → 0.01 with style control; E3/E4 inconclusive (3 events) |
| 2026-11-26 | App work paused; topic re-opened toward real-market advice | User: advice should target actual markets; build only after proof |
| 2026-11-26 | Research T1, T2 and F in parallel; one run script | User request; data collection happens on the user's laptop |
| 2026-11-26 | T1 markets found by slug (`btc-updown-15m-<ts>`, `bitcoin-up-or-down-<date>-<h>am-et`) instead of scanning every market; 5-minute windows added | Full scan would take 7+ hours; 362/364 slugs resolved in the trial |
| 2026-11-26 | T1 G0 alignment measured with the Binance close of the last candle, on markets that moved ≥ 2 bps | Trial: 93% raw agreement, 97.5% on clear moves; 5m/15m markets settle on Chainlink, so exact ties can differ. Fixed before any full-data verdict |
| 2026-11-26 | Hourly price history from CLOB in 14-day windows (last 180 days of each market) | The Data API keeps hourly prices for about a month only |
| 2026-11-26 | T2 market list balanced: ≤ 200 markets per event group, ≤ 1,200 in total | Crypto-price markets were half of the list; keeps the collection to minutes, not hours |
| 2026-11-26 | Topic F screens candidates in random order until 1.2× the sample size is contested | Screening all ~80 k candidates would take many hours; the sample stays random |
| 2026-11-27 | T1 rejected | G1–G3 fail; Polymarket follows spot by about a minute |
| 2026-11-27 | F rejected | E2–E4 fail on 300 contested markets |
| 2026-11-27 | V5 robustness added to T2 after V2/V3 passed narrowly | Placebo, no-crypto, timestamp and skilled-vs-everyone checks; V2 holds weakly, V3's wallet edge does not |
| 2026-11-27 | **Topic chosen: T2 event-risk monitor** (no hedge ratios, no wallet signals) | V1 robust; V2 weak; V4 fails; wallets add nothing |
| 2026-11-27 | Wallet round W0–W5 pre-registered, using the team's pipeline where it fits | User: find how wallets can help the monitor |
| 2026-11-27 | Event-market trades at ≥ $250 (not $10) | Largest markets have 60 k+ trades ≥ $10; whales (≥ $5 k) are unaffected |
| 2026-11-27 | W6 robustness added after W2/W3/W5 passed | timestamp alignment + 15-min gap; W2 dropped, W3/W5 kept |
| 2026-11-27 | **Wallet features in the product: early warning (W3), large-wallet pressure (W5), cluster mix (descriptive)** | Only robust passes go in |

- **2026-11-27 02:15** — User asked for a final daily-use check before building. Pre-registered D1–D6 (docs/05).
- **2026-11-27 02:17** — D1–D6 all pass → build.
- **2026-11-27 02:35** — Building revealed a keyword bug ("Oilers" → oil, "Borussia" → Russia; 62 of 1,200 markets). Fixed to whole-word matching; D1–D6 rerun as D-fix-1, all pass with slightly stronger effects.
- **2026-11-27 03:00** — Prototype v1 (EventLens) built: holdings with 24-hour event strips, jump alerts, W3 early warning, W5 large-wallet pressure, team clusters shown descriptively, forward track record, evidence page. US-politics links shown as "weak link" (D6).
- **2026-11-27 02:58** — D7 (early warning on live data) failed twice; cause: live markets move ~2× more per hour than the research markets, so research thresholds over-fire in quiet markets. Early warning moved to shadow mode; improvement pre-registered (live-relative thresholds, judged on precision after 2 weeks).
- **2026-11-27 14:05** — Value proposition written down (top of this file): off-hours early warning is the headline; intraday alerts explain moves; no direction. Based on S1–S3 (docs/09) and the 72% off-hours share of jumps.
- **2026-11-27 16:10** — Added 'What an alert means' to the plan: an alert is a higher chance of a big move, not a guarantee (25% vs 18%; 72/257 real days, 28% vs 21.6%), never a direction.
- **2026-11-27 16:15** — Added the effect-strength table and the definition of a top-20% move under 'What an alert means'.
- **2026-11-27 16:25** — VIX control test (doc 12): FAIL on specificity. Linked-jump hours +17% beyond the VIX level and recent volatility (CI +10 to +24), but unrelated-jump hours +13%; linked − unrelated +4% (CI −3 to +11). Alerts carry 'event news is moving markets' information beyond the VIX; holding-specific extra is weak at the hourly level.
- **2026-11-27 16:35** — Same-hour test (doc 13) PASS: linked holdings move +7% more than other holdings in the same news hour (CI +2 to +12); +12% at the open after overnight jumps (CI +4 to +20); none intraday; 2+ linked jumps +9%. The holding-specific effect is real but small and concentrated at the open.
- **2026-11-27 16:40** — Added the Evidence map (can / cannot / test register) to the plan.
