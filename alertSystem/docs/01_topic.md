# 01 · Topic decision

*Status: decided 2026-11-26 (iteration 1). Revisions are appended at the bottom, never edited in place.*

## Constraint from the brief

The project must involve **Polymarket**, **wallets**, and end in a **trading / financial helper tool**.

## Candidate topics

| # | Topic | What is predicted | Why it might fail |
|---|---|---|---|
| A | Polymarket event odds → stock returns / volatility | SPY, QQQ moves | The link is indirect; most event markets are near-certain by the day that matters; few independent events (≈8 Fed meetings a year). |
| B | **Smart money inside Polymarket**: do some wallets have persistent skill, and does their trading tell us where *the same market* is heading? | The Polymarket price and the market's resolution | Skill may be luck; edge may vanish after delay and costs. |
| C | Calibration / fair value: are Polymarket prices biased (e.g. long shots overpriced)? | Resolution vs price | Known effect, no wallet component on its own. |
| D | Wash-trading / manipulation detection | Labels unavailable | No ground truth, hard to evaluate. |

## Decision: **B, with C as a building block**

**WalletLens — finding Polymarket wallets with persistent skill, testing whether their trades carry information, and turning that into a trading helper.**

Reasons:

1. **The wallet data and the target live in the same place.** A wallet's trade in a market is judged by that market's own price path and resolution: no fragile mapping to stocks.
2. **Sample size.** Every resolved market is an independent test. Hundreds of markets are available, against a handful of Fed meetings.
3. **Contested markets can be chosen on purpose.** We restrict to markets that spent time between 15% and 85%, so there was real disagreement to be right about.
4. **Calibration (C) is needed anyway.** If long shots are systematically overpriced, a wallet that always sells long shots looks "skilled" without knowing anything. Measuring edge against a *calibrated* fair price separates style from skill.
5. **Whatever the result, a useful tool exists.** A positive result gives a smart-money signal; a negative result still gives fair-value estimates and honest wallet track records.

## Research questions and pre-registered hypotheses

All tests use only information available at the time (walk-forward by market resolution date). Thresholds are fixed **before** looking at results.

Common choices: markets are split in time into an earlier half (**period A**) and a later half (**period B**), keeping all markets of one event on the same side. The fair-value map is fitted on period A only (identity if fewer than 100 calibration points). H2 and H3 are evaluated on period-B markets, with skill always computed from markets closed before each trade. H2's main test uses trades with YES price in [0.05, 0.95] and the markout to resolution, with equal weight per trade; +1 h, +24 h, all trades and size-weighted versions are reported as secondary results. Tests with fewer than 5 events or 10 markets are reported as inconclusive.

| ID | Question | Test | Pass if |
|---|---|---|---|
| H0 | Are Polymarket prices calibrated? | Reliability of price vs outcome at fixed horizons before close; bias by price bucket | Descriptive. Produces the `fair_value(p)` map used by H1–H3. |
| H1 | **Is wallet skill persistent?** | Wallet edge (vs fair value) in earlier markets vs later markets; Spearman across wallets with ≥ 5 markets in each period | ρ > 0 with permutation p < 0.05 |
| H2 | **Do skilled wallets' trades carry information?** | After trades by wallets ranked top-decile on *prior* skill, does the price move their way (markout at +1 h, +24 h, to resolution) more than for other wallets? Clustered by market | Top-minus-rest markout > 0 with bootstrap 95% CI excluding 0 |
| H3 | **Is it tradable?** | Copy top-decile trades after a delay (1 min, 1 h) with a cost (1¢, 2¢), hold to resolution | Mean return per $ > 0 with CI excluding 0 at 1 h delay and 1¢ cost |

## What each outcome means for the product

| Result | Product |
|---|---|
| H1 ✓ H2 ✓ H3 ✓ | **Smart-money signal**: alerts when skilled wallets trade, with expected edge. |
| H1 ✓ H2 ✓ H3 ✗ | **Smart-money radar as evidence**: show who is on each side and their track record, plus fair value, but no "copy" button. |
| H1 ✓ H2 ✗ | **Wallet track-record explorer** plus fair value. |
| H1 ✗ | **Pivot**: fair-value / mispricing helper (topic C) and refine the topic. |

## Known risks, handled up front

- **Look-ahead:** skill is always computed from markets resolved *before* the trade being evaluated.
- **Selection bias:** wallets are never chosen using the test period.
- **Style vs skill:** edge is measured against calibrated fair value, and against a wallet-shuffled null.
- **Market makers:** a maker earns the spread with no information, so the spread is reported and costs are applied in H3.
- **Many tests:** every threshold above is fixed in advance, and all results, failures included, are logged in `results/`.

---

## Revision 1 · 2026-11-26

The user prefers advice for **actual financial markets**; Polymarket-internal advice (this document's topic) becomes the fallback **F**. The pilot on 31 Fed markets also showed that Fed-market "skill" is mostly favourite-buying style (E2: ρ 0.28 → 0.01 after the style control). New candidates and the proof gates that must pass before any app is built are in [00_PLAN.md](00_PLAN.md). The hypotheses above stay valid for topic F and are reused if we fall back to it.

---

## Revision 2 · 2026-11-27 · Final topic

**Polymarket event probabilities as a real-time risk monitor for portfolios.**

When a Polymarket probability linked to an asset jumps (≥ 10 points in an hour), the linked assets move about 25% more than unrelated assets in that hour, most of all bonds and the dollar on Fed/rates markets and China ETFs on tariff markets. The next hour leans weakly in a predictable direction (53%, up to 60% for rates). Wallet data, required by the brief, is used to show *who* is moving the market and is tested honestly: across all three topics, skilled wallets did not move first or predict better than ordinary order flow. That negative result is part of the project's contribution.

Rejected, with evidence: T1 (Polymarket crypto markets follow BTC/ETH by about a minute rather than leading it) and F (no persistent or copyable wallet skill in 300 contested markets). See 02_research_log.md.
