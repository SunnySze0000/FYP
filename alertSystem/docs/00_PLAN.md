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

## Work breakdown

1. **Shared foundation (done):** project layout, config, logging, structured results, Polymarket API clients, resumable collector, wallet-skill and calibration maths, tests with planted-skill and null worlds. Reused by every topic.
2. **T1 / G0:** collector for crypto up/down and above-X markets (trades with wallets, hourly or finer prices), plus 1-minute BTC/ETH klines from Binance's public data dump; coverage report.
3. **T1 / G1–G3:** experiments e10–e13 under the same `results/` structure.
4. **Decision:** record it in the log below and in `docs/01_topic.md`.
5. **Only then:** the app (UI plan in `docs/03_app_plan.md`, drafted but not built).

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
- [ ] Run EventLens live for 2+ weeks: forward track record of alerts, and shadow-mode test of the early warning (docs/05 end)
- [ ] v2 candidates: weak direction hint, push notifications, more assets per group

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
