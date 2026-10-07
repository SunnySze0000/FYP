# Four-wallet pre-meeting review

This is a retrospective case study of frozen candidates **3, 6, 7 and 12** across
July 2025, September 2025, October 2025, December 2025, January 2026, March 2026
and April 2026. It examines their **observed trading decisions**, not their stated
beliefs, full positions or profits. No wallet receives a production weight.

## What we found

All four have some pre-cutoff activity in all seven meetings, but that does not mean
they traded in the final week of every meeting. The main review uses the seven days
ending immediately before each existing decision cutoff.

| Candidate | Wallet prefix | Scored / 7 meetings | Positive scores | Mean flow alignment |
| --- | --- | ---: | ---: | ---: |
| 3 | `0xe8dd7741` | 4 | 1 | +0.000580 |
| 6 | `0x21ffd2b7` | 5 | 2 | +0.005192 |
| 7 | `0xbc54e696` | 6 | 2 | -0.000070 |
| 12 | `0xa8b7f8b` | 3 | 0 | -0.001165 |

These are dimensionless diagnostics, **not returns or probabilities**. Positive
means the signed flow aligned with the final outcome relative to the available
pre-cutoff market quote. Missing meetings are excluded from the mean and explicitly
counted as abstentions, rather than treated as wins or losses.

- **#3:** final-week records were almost entirely NO purchases. The strongest
  negative flow was against a 50+ bp cut in September, December and January,
  and against a 25+ bp increase in March. This does not identify which alternative
  the wallet expected. For example, buying NO on a 50+ bp cut does not distinguish
  a 25 bp cut from no change. Three meetings had no final-week activity.
- **#6:** July flow leaned toward no change and away from a 25 bp cut; December
  flow leaned toward a 25 bp cut. Both outcomes occurred. October flow leaned
  toward no change, while the result was a 25 bp cut. In January, tiny residual
  flow leaned toward a cut, while the result was no change. These signs include
  sales of NO tokens, which could be closing earlier positions. March and April
  had no final-week activity. The positive seven-day mean becomes negative in
  the one-day and thirty-day reviews.
- **#7:** bought and sold YES tokens in several markets. September's strongest
  positive flow was toward a 25+ bp increase, although a 25 bp cut occurred.
  March and April flow leaned toward a 25 bp cut, while no change occurred.
  Heavy netting in several meetings makes the remaining directional flow small.
  July had no final-week activity; the one-day mean is positive, while the
  seven-day and thirty-day means are negative.
- **#12:** September's strongest positive flow was toward a 50+ bp cut, while
  a 25 bp cut occurred. October flow opposed the winning 25 bp cut. January
  flow opposed no change, which occurred. December has 11 duplicate-candidate
  rows out of 197 and is excluded by the inherited 5% rule; we do not silently
  deduplicate them. July, March and April had no final-week activity. Its
  thirty-day mean is positive despite negative one-day and seven-day means.

**Conclusion:** data collection and interpretable wallet-flow analysis are feasible.
The seven meetings and sensitivity results do not establish persistent predictive skill.
This is not a validated ranking: different wallets have different scored subsets,
and the four were chosen after these historical meetings using later June activity
and complete prior-meeting coverage. That selection creates retrospective bias.

## A reproducible diagnostic for the data we actually have

For wallet `w`, meeting `e`, and binary outcome market `m`, sum shares in the window:

```text
D_m = BUY_YES - SELL_YES + SELL_NO - BUY_NO
G   = sum over all markets of all BUY and SELL token shares
p_m = latest team CSV YES probability timestamped at or before the cutoff
y_m = resolved YES outcome, 0 or 1

flow_alignment(w, e) = sum_m D_m * (y_m - p_m) / G
wallet_mean         = equal-weight mean over scored meetings
```

Each binary token has a one-unit settlement payoff. Positive `D_m` is flow in the
YES direction; negative is flow in the NO direction. The score asks whether that
direction agreed with the outcome's deviation from the quote. For example, 100
YES shares bought at a meeting whose cutoff quote is 0.80 and outcome is YES gives
`100 * (1 - 0.80) / 100 = +0.20`. Buying 100 NO shares instead gives -0.20.
The execution price is deliberately absent: this measures flow association with
outcomes, **not entry timing, trading returns or actual profit**.

Divide by gross shares rather than absolute net flow so near-cancelled buys and
sells cannot amplify a tiny residual. `netting_ratio = sum(abs(D_m)) / G` shows
how much directional flow remains; a low ratio means heavy cancellation. Scores
lie in [-1, 1], and scaling every trade equally does not change a meeting score.
This is an analyst-defined diagnostic, **not a proper probability scoring rule**.
The method was designed after examining these histories, not preregistered.

The main window is 7 days. Both 1-day and 30-day outputs are included as
sensitivity checks, not selected according to which produces the best result.
Windows are `[cutoff - window, cutoff)`. Each meeting is one observation; hundreds
of fills do not provide hundreds of independent Fed decisions. Shared meetings
and counterparties also mean wallets are not independent replications.

Abstain when there is no window activity, zero net flow across every market, or
more than 5% duplicate-candidate rows. The 5% rule carries forward the earlier
exploratory data-quality convention; it is not a statistically derived threshold.
Below the threshold, flagged rows remain, so small scores may still be affected.
No activity is different from zero flow. No minimum sample size proves skill here.

Market baselines are the latest available daily rows, at most 24 hours old. All
four markets must have valid quotes and consistent outcome labels or the build
fails. These are **daily baseline quotes, not synchronized live cutoff prices**.
Their timestamps and ages are exported. Binary quotes are used as supplied,
without normalizing; `baseline_probability_sum` exposes whether they sum to one.
Team CSV publication times have not been verified: a timestamped row is not proof
it was archived and available to our system then.

## Defensible probability evaluation for the FYP

The eventual target is to test whether wallet information improves **our model's
probability forecast**. We cannot currently score a wallet's own forecast with
Brier loss: it never supplied one, and purchases do not reveal a coherent
four-outcome probability vector. Reconstructed holdings alone would not reveal
subjective beliefs either, especially under hedging and market making.

Use the following protocol for a future experiment:

1. Verify scheduled announcement times from an official FOMC source; fix one
   horizon, such as 24 hours before announcement. The present cutoffs are Gamma
   `endDate - 24h`, a conservative convention, not verified announcement times.
2. Select an activity-based cohort using information available **before** the
   training/evaluation period. Keep inactive wallets and coverage gaps visible.
   Verify original outcome availability before using resolved results for weights.
3. Build features from past-only signed flow, turnover, coverage and quality.
   Transfers, splits, merges and initial balances must be included if a feature
   claims to measure positions. Current prior trade records have no Polygon checks.
4. Learn a mapping from those features and market probabilities to `p_adjusted`
   using chronological training meetings only. Use a softmax or other explicitly
   coherent mapping to ensure nonnegative probabilities summing to one. This is
   **our fitted forecast**, not a claim about wallet beliefs. Fix normalization,
   cohort rules, windows and model parameters before held-out evaluation.
5. For K mutually exclusive outcomes, evaluate `Brier(p, y) = sum_k (p_k-y_k)^2`
   on a complete forecast at the fixed cutoff. Lower is better. Use the same
   convention for both models. Normalize the raw binary quotes into a categorical
   baseline by a documented rule before this comparison; retain original quotes.
   Missing baseline/adjusted forecasts require abstention, never a fabricated vector.
6. Report paired improvement `Brier(p_raw, y) - Brier(p_adjusted, y)` per held-out
   meeting, the mean, coverage and uncertainty across **meetings**. Also compare
   with simple historical/no-change and identity-blind flow baselines. Use the
   same valid meeting subset for every paired comparison. Seven meetings give
   weak evidence; acquire more independent events before claiming an improvement.

The Brier rule is a standard proper scoring rule for probability forecasts;
see [Gneiting and Raftery (2007)](https://doi.org/10.1198/016214506000001437).
Our flow diagnostic above is a separate descriptive construction, not sourced
from that paper. Lifecycle operations are supported separately from trades in
the [official Polymarket SDK](https://github.com/Polymarket/py-sdk/blob/main/src/polymarket/clients/secure.py).

June can be reserved as a later-time case after fixing the method, but its labels
are already known today and the dataset was collected retrospectively. Do not
describe that as a genuinely prospective or blinded experiment. Persist a frozen
method and begin collecting a future meeting before its result for stronger evidence.

## Files and reproducibility

| File | Rows | Grain / purpose |
| --- | ---: | --- |
| `outcome_flows.csv` | 336 | 4 wallets × 7 meetings × 4 markets × 3 windows; YES/NO purchases and sales, signed flow, quote, result and numerator |
| `meeting_decisions.csv` | 84 | 4 wallets × 7 meetings × 3 windows; directional descriptions, cancellation, score or explicit abstention |
| `wallet_diagnostics.csv` | 12 | 4 wallets × 3 windows; equal-meeting descriptive means, coverage, signs and range |
| `report.json` | — | Method parameters, claims, limitations and frozen input SHA-256 hashes |
| `SHA256SUMS` | — | File integrity checks |

Full addresses and IDs remain strings. Shares and score components are decimal
values; UTC timestamps retain timezone offsets. Blank scores mean abstention,
not zero. `strongest_positive_flow_outcome` and `strongest_negative_flow_outcome`
describe the largest signed residual; they are not forecasts or holdings. Ties
are separated with semicolons. There may be no positive flow at all.

Source: existing [prior-history export](../prior_history/README.md), collected from
Polymarket public Data API v2, plus Gamma token/resolution metadata and the team's
`datasets/forward_probabilities.csv` for daily baselines. This stage is entirely
offline and adds no chain-derived data. Original resolution timestamps, lifecycle
coverage, historical position snapshots and actual PnL remain unavailable.

Run from the repository root:

```bash
python3 -B scripts/polymarket/review_wallet_decisions.py
```

The script preserves source datasets and the frozen candidate list. It rebuilds
the three CSVs, input-hash report and checksums; this README is maintained separately.
