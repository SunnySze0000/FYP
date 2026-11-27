# 07 · EventLens v1.1: portfolio import and wallet notes (D1, D2, D3)

*Built 2026-11-27. App version `1.1` is stamped on every log row. Rows without a version are from v1.0.*

## D1 · Portfolio import
Users type up to 15 US stock or ETF tickers. For each holding, EventLens builds a **profile**
(`data/app/holdings/<TICKER>.json`). Building takes about 1 minute per holding in the background.

1. **Resolve** the ticker with Yahoo search: name, stock or ETF, sector, industry, exchange. Only US listings
   and crypto are allowed.
2. **Layer 1, direct mention:** the company name (first word or first two words), the ticker (3+ letters, not
   a common word) and a few executives (Musk → TSLA, Saylor → MSTR…), whole-word matched in bet questions.
3. **Layer 2, by topic:** a hand-made ETF table (VOO/IVV/VTI = broad US market, like SPY), or the stock's
   industry, then its sector, mapped to topic groups.
4. **Layer 3, history check:** for each candidate topic, compare the holding's hourly |return| in that topic's
   past jump hours (`data/app/group_jumps.csv`, 3,586 research jumps) with normal hours at the same hour of
   day. Bootstrap by day. The outcome is one of:
   - **confirmed**: 90% CI above 0
   - **likely**: positive but uncertain
   - **not enough history**: fewer than 15 jump hours
   - **dropped**: zero or negative
   - **weak link**: US politics, always (D6)

   Weak links are shown but never raise the holding's level.

**Rejected while building:** letting history *add* links the tables didn't list. Almost every asset then looked
linked to crypto bets (for example SPY, QQQ, EEM, ITA), because jump hours cluster in market-wide busy hours.
History can now only confirm or drop a candidate link.

Check on the 26 research assets: 13 links confirmed, about 1 dropped (USO → Russia/Ukraine), and the rest
likely or too little history. SPY → Fed/rates: +37% in rate-jump hours but only 42 hours, so "likely".

## D2 / D3 · Per-holding wallet notes
Each holding's profile also tests three wallet patterns on its own history: research trades in its linked
markets, hours after the cluster fit date only.
- Market makers (C0) surge: W7, pooled +9%
- Burst traders (C2) surge: W7, pooled +6%
- Wallets trading 2+ linked bets in the same hour: W9b, pooled +21%

A pattern is shown for the holding only with ≥ 20 past cases and a positive effect. The number shown is
shrunk toward the pooled effect (n / (n + 50) weight on the holding's own estimate).

Live, the same `window_signals` code runs on trades in the holding's reliably linked markets. An active
pattern shows as a note on the holding card and in the "Wallet patterns" block. It is context, not an alert.
Notes are logged to `data/app/notes.jsonl` and scored against the holding's next-hour move.

**Known gap:** the per-holding check has no placebo (pooled W7 and W9b had one). The shrinkage and the ≥ 20-case
minimum stand in for it; the live notes log is the real check.

## Backfill: the laptop no longer has to run nonstop
Each scan logs every jump, early-warning score and wallet note of the **last 24 hours** at its true hour,
skipping anything already logged. Starting EventLens at least once a day keeps the V1 record complete.
