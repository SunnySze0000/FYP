# EventLens playground: findings and recommended direction

Branch `sunny_playground`, November 2026. Every number below is reproduced by
`python scripts/run_research.py`; the full tables are in
[`reports/results.md`](reports/results.md) and `reports/*.csv`.

## TL;DR

1. **The pipeline is now trustworthy.** It recovers all 21 independently
   verifiable Fed decisions from Polymarket resolution, and reproduces the
   documented FOMC-day volatility effect: SPY's standardised variance is
   **2.9x** normal on announcement days (placebo p = 0.002).
2. **The original equity question cannot be answered with this data.** With
   27 meetings, only correlations above |ρ| = 0.52 are detectable. All five
   pre-registered event-study tests are near zero (|ρ| ≤ 0.07). The day
   before a meeting, Polymarket already gives the realised outcome about 92%
   probability, so there is almost no "surprise" left to explain moves. The
   largest reaction (Dec 2024, a −7.5σ day) came from forward guidance, which
   these markets do not price.
3. **The pattern that does show up is the favourite–longshot bias.**
   - Fed-market prices of 5–25% resolved YES only 0–8% of the time; prices
     of 50–90% resolved YES 77–94% of the time.
   - Across 30,000 wallets, skill is **persistent out of sample**: ρ = 0.30
     between formation and test periods, p < 0.001. The persistent winners
     are one-directional buyers of near-certain favourites.
4. **Nothing is yet a proven trading edge.** The Fed favourite rule never
   clears its break-even test with ~27 meetings. Copying "smart" wallets one
   hour later loses money after costs. Their information is priced within
   the hour.
5. **Recommended direction:** keep Polymarket and the wallets as the core,
   but move the main test to **thousands of markets across all categories**.
   That is where the favourite–longshot edge, and wallet skill, can be
   confirmed or rejected with real statistical power. The collectors and a
   leakage-safe walk-forward backtest for this are built and tested; they
   need one run on a PC with internet access.

## What was wrong before and what changed

| Problem in `models/` and `playground.ipynb` | Fix in this branch |
|---|---|
| Three outcome-to-basis-point maps that disagree | One taxonomy (`data/taxonomy.py`) with explicit rate ranges |
| Probabilities that did not sum to 1 were silently rescaled | Reported by `validation/checks.py`; such snapshots are excluded |
| Settled markets (price ≈ 0 or 1) fed as "live" features after a meeting | Snapshots taken strictly before the announcement, tested in `tests/` |
| Stale features forward-filled across a 50-day gap | Gaps reported; event-level design needs no forward fill |
| Daily rows treated as independent (27 events → "thousands" of rows) | Unit of analysis is the meeting; CIs resample whole meetings |
| Return prediction with nine model families on one holdout | Five hypotheses fixed in advance, permutation p-values, power analysis |
| Weekend rows created by forward-filling SPY returns | Trading-day series only |

## 1. Sanity checks (`reports/fomc_day_volatility.csv`)

- 27 Fed meetings have markets. The March, May and June 2025 meetings are
  missing from the team dataset.
- All 21 meetings with an official reference decision resolved to the
  correct bucket.
- On FOMC days, SPY's mean squared standardised return is 3.35, against 1.16
  on other days: a ratio of 2.9, placebo p = 0.002.

**Takeaway for the helper:** "an FOMC announcement is within your horizon"
is solid, defensible risk advice on its own.

## 2. Event study (`reports/event_study_tests.csv`, `power_analysis.csv`)

| Hypothesis | ρ | 95% CI | p |
|---|---|---|---|
| Bigger surprise → bigger move | 0.04 | −0.38 to 0.44 | 0.84 |
| Hawkish surprise → equities fall | −0.07 | −0.48 to 0.32 | 0.74 |
| More uncertainty → bigger move | 0.00 | −0.44 to 0.42 | 1.00 |
| More uncertainty → higher post-event volatility | 0.06 | −0.34 to 0.44 | 0.76 |

The confidence intervals are wide enough to include large effects, so this
is "no evidence", not "evidence of no effect". To detect ρ = 0.2 you need
about 200 independent events. That is the core reason the earlier models
looked like noise.

## 3. Fed-market calibration (`reports/fed_calibration.csv`, `fed_favourite_rule.csv`)

- Prices are informative: Brier skill versus the base rate is 0.92 within 7
  days of the meeting and 0.40 at 3+ months.
- **Longshots are overpriced and favourites underpriced.** This is the
  classic favourite–longshot bias.
- Buying the favourite side at 80–99% and holding to resolution averaged
  +1.5% to +16% per trade after a 1¢ cost. **But** the lower 95% bound of
  the win rate never exceeds the break-even win rate. With roughly 30 trades
  per setting, a single loss would wipe out the edge, so this is not yet a
  credible edge.

## 4. Smart wallets (`reports/wallet_*`)

The data are every trade (596k records, 30k wallets) in the five June 2026
Fed markets, from PR #1. Wallets are scored on Dec–mid May; the score is
tested on mid May–June. A wallet's score is its average "markout": how much
the price moved in its favour after each trade, per share, shrunk towards
zero for small samples.

| Test-period target | ρ (formation vs test score) | p |
|---|---|---|
| 24-hour markout | 0.30 | <0.001 |
| 1-hour markout | 0.40 | <0.001 |
| P&L if held to resolution | 0.22 | 0.006 |

- Top-quintile wallets earned **+1.1% per dollar** to resolution in the
  test period; the bottom two quintiles lost.
- Their profile: one-directional bets at a median YES price of 0.975. They
  are systematic favourite buyers, consistent with section 3.
- Restricted to contested prices (5–95¢), 24h skill still persists
  (ρ = 0.25, p = 0.015), but resolution P&L does not (n = 96 wallets).
- **Following them does not work:**
  - Their daily net flow does not predict the next day's price (ρ ≈ 0.05).
  - Copying each trade one hour later loses 0.2–0.8¢ per share after a 0.5¢
    cost.

**Caveat:** this is one meeting. The five markets share one outcome, so this
is strong evidence of within-event persistence, not yet cross-event.

## Recommended direction (stays close to the original proposal)

EventLens becomes a **Polymarket trading assistant with an event-risk view**:

1. **Fair-value layer.** For any market, show the price next to a calibrated
   probability learnt from thousands of resolved markets. That's the
   favourite–longshot correction, by category and time to close. Trade only
   when the gap clears cost and a statistical hurdle. This is
   `analysis/universe.py`, already validated on synthetic data: it finds a
   planted bias (+7%) and stays out of fairly priced markets.
2. **Wallet layer.** Show which persistent-skill wallets are positioned and
   which way. It is an evidence panel, not a copy-trading signal, because
   copying is shown not to work at hourly speed.
3. **Event-risk layer.** For equity users: scheduled events in the horizon,
   the market-implied outcome distribution, and the documented 2.9x
   announcement-day variance. That's honest advice that doesn't depend on
   an unproven forecast.

## Next steps, in order

1. Run the collectors (README, about an hour), then rerun
   `scripts/run_research.py`. Section 6 of the report fills in automatically
   with cross-market calibration and the walk-forward backtest.
2. If the walk-forward return's CI is above 0 across categories, that's the
   core result of the FYP. If not, report the null. Either way it's a
   rigorous finding.
3. Extend the wallet study across many events. Score on earlier resolved
   markets and test on later ones, using the Data API trade collector from
   PR #1.
4. Build the dashboard on the three layers above.

## Limitations

- Daily Polymarket snapshots have an unknown intraday stamp. Features use a
  one-day lag so they cannot contain the decision.
- Polymarket outcomes after 2025 are checked only against market
  resolution, not an official source.
- Trade prices proxy for quotes. Markouts include spread capture, and costs
  are assumed (0.5–1¢ per share), not measured from order books.
- Results are for research. They are not investment advice.
