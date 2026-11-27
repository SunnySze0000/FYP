# 02 · Research log

One entry per research run, newest first. Full outputs: `results/<run_id>/summary.md`; all topics side by side: `results/OVERVIEW.md`.

## 2026-11-27 · Wallet directions for the event-risk monitor (W0–W6)

Pre-registered in `04_wallet_directions.md`; full table there. 2.78 M trades (≥ $250) by 147 k wallets in 689 event markets; the team's sniper grouping, hard rules and frozen behaviour clustering are included.

- **Pass and robust:** W3 early warning (AUC +0.027 out of time; a surge in distinct wallets precedes jumps) and W5 (price follows $5k+ trades by +0.42 points next hour vs +0.05 after retail).
- **Pass but not robust:** W2 (whale-backed jumps hold 3.9 points better over 24 h; not significant once the last 15 minutes are excluded).
- **Fail:** W1 confirmation, W4 direction boost; skilled, new and frequent wallets never beat retail.
- Team clusters: all three lean against the next move (liquidity-provider behaviour); sniper grouping finds only 2 same-owner groups in event markets.

## 2026-11-27 · Full run, all three topics

### T1 · Crypto up/down markets vs BTC/ETH spot — **fails**
5,239 markets (5m / 15m / 1h / 4h, BTC and ETH, Mar–Nov 2026), 4.6 M trades, 422 k spot minutes per asset.

| Gate | Result |
|---|---|
| G0 data | **pass**: 218,808 asset-minutes over 250 days; outcome matches Binance in 98.9% of markets that moved ≥ 2 bps |
| G1 market lead | **fail**: out-of-sample R² gain −0.008% at 5 min (CI −0.017% to 0.000%, 229 test days). Lead–lag: spot moves first, Polymarket follows one minute later (corr 0.41 BTC, 0.33 ETH); the reverse is ≈ 0 |
| G2 wallet lead | **fail**: skilled flow adds −0.009% R² (CI −0.033% to +0.013%); crypto wallet edge persistence ρ = 0.09 (2,588 wallets) |
| G3 tradable | **fail**: best rule −6.0 bps per trade at 5 bps cost (CI −9.1 to −2.9) |

### F · Smart money inside Polymarket — **fails**
300 contested markets (random sample of 30,038 candidates, Jan 2025 – Oct 2026), 490 k trades, 57 k wallets.

| Test | Result |
|---|---|
| E1 calibration | buckets off by 6.6 points on average; recalibration (b = 0.89) does not improve later markets |
| E2 persistence | ρ = 0.09 (p = 0.16, 129 wallets); same after the style control |
| E3 information | top tier +0.4 points vs the rest (CI −4.0 to +4.9) |
| E4 copy trading | −3.8% per $1 at 1 h delay and 1¢ cost (CI −16% to +8%) |

### T2 · Event-probability shocks → related assets — **passes (risk use)**
689 contested event markets (balanced across 8 event groups), 7,156 shock hours (|Δp| ≥ 10 points in an hour), 26 assets hourly.

| Test | Result |
|---|---|
| V1 same-hour sensitivity | **pass**: related assets move +25% more than unrelated ones in shock hours (CI +15% to +34%, 366 markets); without crypto-price markets +22% (CI +11% to +34%). Strongest: rates → TLT/IEF/SHY/UUP/XLF (2.2× vs 1.6×), China/tariffs → FXI/KWEB/EEM (1.9× vs 1.2×), macro (1.7× vs 1.2×) |
| V2 next-hour direction | **pass (weak)**: 53.1% hit rate (CI 50.6–55.5%); rates 60%, China 56%, AI/tech 55% |
| V3 wallets lead the probability | **pass vs zero, but not vs everyone else**: +0.70 points after skilled buying, +0.53 after anyone's buying |
| V4 stable exposures | **fail**: sign kept in 44% of pairs (CI 34–54%), so fixed hedge ratios are not reliable |
| V5 robustness (added) | V2 placebo on unrelated assets 50.5% (as it should be); without crypto 53.4%. Hourly Polymarket prices sit closer to trades *before* their timestamp (0.72 vs 0.98 points), so no look-ahead. V3 head to head: skilled minus others −3.4 points per market (CI −6.0 to −1.3): no skilled-wallet edge |

**Decision:** T2 is the topic. The product is an **event-risk monitor** for portfolio holders: it flags when a Polymarket probability linked to their assets jumps, says how much those assets usually move in such hours, and shows the weak directional lean as a hint. It does **not** give hedge ratios (V4) or wallet-based signals (V3/V5, T1, F).

## 2026-11-26 · Pilot, Fed markets (`pilot_fed`, 31 markets, 7 meetings, 4.1 M trades, 256 k wallets)

| Test | Result |
|---|---|
| E1 calibration | Too few points to fit a fair-value map (48 < 100), so fair value = price |
| E2 persistence (H1) | ρ = 0.28 (p = 0.001, 1,842 wallets), but **0.01 after controlling for long-shot/favourite style** |
| E3 information (H2) | Top tier −1.2 points vs the rest; inconclusive (3 events in period B) |
| E4 copy trading (H3) | −6% per $1 at 1 h delay and 1¢ cost; inconclusive (3 events) |
| E5 | Top tier's net side won 100% of 15 later markets, but so did the market favourite in 87% of them: style, not information |

**Takeaway:** wallet "skill" in near-certain markets is a style effect. Tests need contested markets, many independent events, and a style control. This fed directly into the iteration-2 candidates in `00_PLAN.md`.


## 2026-11-27 · Daily-use applicability (D1–D6) and D-fix-1

- Pre-registration: docs/05_daily_applicability.md. Runs: `results/20261127-0230_daily_events` (original),
  `results/20261127-0236_daily_events_fix1` (after the keyword fix), D4 `results/20261127-021157_live_check`.
- All six pass both times. After the fix: V1 +0.24× without hindsight; 6/6 quarters; alert → big move 25% vs 18%;
  ~1 alert/day for a 6-asset portfolio; live refresh 21 s; daily view +0.23×; 6/7 groups (US politics negative).
- Live early-warning model (without the `new_z` feature the app cannot compute exactly): out-of-time AUC 0.917
  vs 0.871 price-only. Replay parity check of the app's engine: flagged hours jump next hour 4.5% vs 0.05%.

## 2026-11-27 · W7 cluster surge → holding risk
- Pre-registration and results: `docs/04_wallet_directions.md` (section W7). Tables: `results/20261127-1200_round3/w7_*.csv`.
- PASS for market makers C0 (+9.0% next-hour move, 19/22 holdings) and burst traders C2 (+6.3%, 15/22).
  Patient traders C1 fail (no better than placebo). Energy holdings go the other way.

## 2026-11-27 · Round 3: W9, W10, M1, M2, M3
- Pre-registration and results: `docs/06_round3_research.md`. Tables: `results/20261127-1200_round3/w9_summary.csv`.
- W9b cross-market wallets PASS (+20.7%, 15/18 holdings; +15.2% without crypto assets). W9a, W9c, W9d, W9e fail.
- W10 supervised wallet model, M1 learned links, M2 move size and M3 direction all FAIL. M1 and M2 stay open with notes on what to try next.

## Where each W result lives
| Test | Pre-registration and write-up | Run output |
|---|---|---|
| W0–W6 | `docs/04_wallet_directions.md` | `results/20261127-014406_wallets/<w*>/summary.md` (and `OVERVIEW.md`) |
| W7 | `docs/04_wallet_directions.md` (W7 section) | `results/20261127-1200_round3/w7_summary.csv`, `w7_per_holding.csv` |
| W8 (early-warning fix, open) | `docs/05_daily_applicability.md` (D7, D-fix-2, D-fix-3, proposed fix) | `results/*_live_calibration/`, `data/app/warnings_shadow.jsonl` |
| W9 | `docs/06_round3_research.md` | `results/20261127-1200_round3/w9_summary.csv` |
| W10 | `docs/06_round3_research.md` | in the doc (run from `w10_m3_models.py`) |

## 2026-11-27 · Sequence test S1–S3 (does the jump come first?)
- Pre-registration and results: `docs/09_sequence_test.md`. Tables: `results/20261127-1400_sequence/`.
- S2 PASS: jumps while the US market is closed → bigger move at the next open (+0.28, CI +0.20 to +0.38; +0.31 without crypto).
- S1 FAIL: in trading hours the stock moves most in the hour *before* the jump; only a small excess afterwards. S3 FAIL (direction 49.8%).
