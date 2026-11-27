# 06 · Round 3 research: W9, W10, M1, M2, M3 (pre-registration)

*Written 2026-11-27 11:35 HKT, before any of these tests were run. Pass rules are fixed here. Common rules:*

- *Out of sample: models and clusters are fitted on data before 2026-01-01 (`split_ts`), and judged on data after it.*
- *Every holding-level insight must generalise. It must be positive in ≥ 50% of holdings with enough data,
  not only in specific market–asset pairs (user requirement).*
- *Wallet signals use a 15-minute data-delay gap and the corrected whole-word links. US-politics links are excluded (D6).*
- *Holding outcome = next-hour |return| ÷ the asset's average |return| at that hour of day (1.0 = normal).*

## W9 · Wallet insights round 2 (5 directions, Bonferroni × 5 → 99% intervals)

Each signal is computed per holding and hour over all markets linked to the holding. The test is the same as
W7. Pass (all required):

1. Pooled effect CI > 0.
2. Positive in ≥ 50% of holdings with ≥ 20 signal hours.
3. Linked minus placebo (unlinked markets) CI > 0.
4. Still > 0 without jump hours.

| ID | Signal | Fires when |
|---|---|---|
| W9a | **Breadth surge** | distinct wallets trading the linked markets, log ≥ 1 above trailing-48h mean, ≥ 10 wallets |
| W9b | **Cross-market wallets** | wallets trading ≥ 2 different linked markets in the hour, ≥ 3 such wallets and log ≥ 1 above trailing mean |
| W9c | **Market makers withdraw** | C0's share of linked $ flow ≤ ⅓ of its trailing-48h share while total flow ≥ its trailing mean |
| W9d | **Daily large-wallet build-up** | 24-hour $5k+ gross flow in linked markets, log ≥ 1 above trailing-7-day mean → *next-day* \|return\| ÷ asset mean daily \|return\| |
| W9e | **Concentration** | top wallet's share of linked $ flow ≥ 50% with flow ≥ $5k (one big player dominating) |

## M1 · Learned bet-to-asset links (own text model, no LLM)

- **Labels:** for every candidate market × each of the 26 assets, the asset's shock-hour |return| ÷ normal |return|
  (watched hours; pairs with ≥ 1 shock), minus 1.
- **Model:** TF-IDF of the question (words + word pairs + character 3–5-grams). One ridge regression per asset,
  trained on markets that closed before `split_ts`, weighted by the number of shocks.
- **Links:** the model's top 3 assets per market, if their prediction is above the 75th percentile of
  training predictions for that asset.
- **Baseline:** keyword links (current product).
- **Test markets:** those closing after `split_ts`.
- **Metric:** mean excess of linked pairs minus mean excess of unlinked pairs, per market, bootstrapped by market.

**Pass (adopt the model):**
- (a) the model-link effect CI > 0;
- (b) its effect ≥ the keyword effect (point estimate);
- (c) it covers ≥ as many test markets with ≥ 1 link.

**Also reported:** the union of keyword and model links (keyword ∪ model), and the paired difference with its CI.

## M2 · Predicting how big a holding's move will be

- **Data:** shock rows (watched, linked pairs).
- **Target:** |asset return in the shock hour| ÷ the asset's normal |return|.
- **Features:**
  - |Δp| of the jump
  - topic group
  - asset
  - hour of day (UTC) and whether the bar is the first of the US session
  - log market volume
  - the asset's trailing-24-bar mean |return| ÷ normal (recent volatility)
  - the market's trailing-24h probability volatility
- **Model:** gradient boosting (sklearn HistGradientBoosting, median loss), plus 10% and 90% quantile models
  for a range.
- **Baseline:** each asset's fixed mean ratio from training (current product).
- **Train/test:** train before `split_ts`, test after.

**Pass:**
- (a) GBM mean absolute error < baseline, with the paired CI of the difference < 0 (bootstrap by market);
- (b) the 10–90% range covers 70–90% of test outcomes.

## W10 · Supervised wallet model (low priority)

- **Data:** for each wallet, features from trades before `split_ts`:
  - trade count, active days, markets
  - mean and median size, share of $5k+ trades
  - two-sidedness, buy share
  - realised 1-hour markout (the price change in the trade's direction 1 hour later)
  - cluster
- **Target:** the wallet's mean 1-hour markout on trades after `split_ts` (≥ 5 later trades).
- **Model:** gradient boosting. Wallets are ranked by prediction.

**Pass:** later trades by the top-decile wallets have a mean markout greater than both (i) all wallets and
(ii) the W5 rule ($5k+ trades), with CI > 0 for both differences (bootstrap by wallet).

## M3 · Direction model (deprioritised)

- **Data:** linked shock rows.
- **Target:** the sign of the asset's return in the shock hour, relative to the market's sign (i.e., "does
  the asset move the way the pair moved before?").
- **Model:** gradient boosting classifier. Features: those of M2, plus the pair's training-period co-movement
  sign and the signed large-wallet flow in the shock hour.

**Pass:** the out-of-sample hit rate CI lower bound > 52%, and above the simple V2 rule's test-period hit rate.

# Results (run 2026-11-27 11:40–12:05 on the research data; hours or markets after 2026-01-01)

| Test | Verdict | Result |
|---|---|---|
| **W9b Cross-market wallets** | **pass** | Next-hour move **+20.7%** vs normal (99% CI +7.7 to +34.9); positive in **15 of 18 holdings (83%)**; placebo +6.3%; without jump hours +18.3%. Without the crypto assets: +15.2% (CI +0.5 to +33.1), 11 of 14 holdings (79%). |
| W9a Breadth surge | fail | +8.9% (CI −0.2 to +18.2), 68% of holdings; does not beat placebo |
| W9c Market makers withdraw | fail | +5.7% (CI −4.8 to +17.1), 68% of holdings |
| W9d Daily large-wallet build-up | fail | −1.3% next-day (CI −13.7 to +8.9), 32% of holdings |
| W9e Concentration | fail | +1.9% (CI −4.7 to +8.5), 55% of holdings |
| M1 Learned links | fail | On test markets, keyword links score +0.207 (CI +0.103 to +0.306, 143 markets) and the text model +0.150 (CI +0.012 to +0.294, 109 markets). The model is worse *and* covers fewer markets; it learns noise from about 600 training markets (e.g. "Strait of Hormuz" → COIN). Model − keyword: −0.070 (CI −0.219 to +0.079). |
| M2 Move size | fail | Model error 0.964 vs fixed per-asset median 0.913 (worse; CI of difference +0.007 to +0.100). The 10–90% range covered 68%. Rank correlation 0.16; only hour of day mattered much. |
| W10 Supervised wallet model | fail | Later trades of the top-decile wallets: 1-hour markout +0.13 points, vs +0.15 for all wallets (diff −0.03, CI −0.19 to +0.11). It beats the $5k+ trade rule (+0.19, CI +0.03 to +0.31), but not wallets in general. |
| M3 Direction | fail | Hit rate 49.6% (CI 46.2–52.8%) vs 50.0% for the simple co-movement rule. Direction stays unpredictable. |

**Conclusions**
- **New product feature:** the *cross-market wallets* signal (W9b), the strongest wallet-to-holding result so far.
  It fires when several wallets trade more than one of a holding's linked bets in the same hour. The next
  hour's move then runs about 15–21% larger than normal, across most holdings. It is added as dashboard task D3,
  with the same per-holding check as D2.
- **Keep keyword links (M1)** and the **fixed "× normal" size (M2)**. Simple machine-learning models do not beat
  them on this amount of data. For D1 (portfolio import), the per-holding history check (layer 3) is the safeguard.
  A text model would need far more labelled markets, or an LLM, which is parked by user decision.
- **Wallet-level prediction (W10) and direction (M3) stay closed.** This agrees with E2–E4, W1, W4 and V2/V4.
