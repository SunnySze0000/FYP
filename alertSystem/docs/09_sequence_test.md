# 09 · Does the event jump come *before* the stock move? (pre-registration)

*Written 2026-11-27 13:50 HKT, before running. V1 showed that linked assets move more in the **same hour**
as an event jump. Moving together in the same hour does not show which came first. These tests check the
order.*

**Data**
- Watched jumps (≥ 10 points in 1 h, price 1 h earlier between 10% and 90%) from all 1,200 candidate markets,
  using the corrected whole-word links. US-politics links are excluded (weak, D6).
- Linked assets come from the group table; placebo assets are drawn for the same jump, as in V1.
- Outcome: |hourly return| ÷ the asset's average |return| at that hour of day (1.0 = normal).
- To avoid counting one news burst several times, only the **first** jump of a market within any 6-hour
  window is used.
- Bootstrap by market, 2,000 draws, 95% CI.

## S1 · Event-time profile (hours −3 … +3 around the jump hour)
For each jump, take the linked asset's outcome in the jump hour (0) and the 3 hours before and after,
counting only consecutive trading hours. Subtract the same for the placebo assets of that jump.

**Pass (sequence):**
- (a) linked minus placebo at **+1 hour** > 0, with CI > 0. The stock keeps moving more *after* the jump.
- (b) **+1 minus −1** for linked assets > 0, with CI > 0. The excess after the jump is bigger than before it.

## S2 · Overnight jumps → next open (natural experiment)
Here the timing is unambiguous: the stock cannot trade while the event jumps.
- **Jumps:** for stocks and ETFs (not crypto), jumps that happen while the US market is closed, after the last
  bar of a session and before the next session opens.
- **Outcome:** the next session's first-bar |return| (previous close → first hourly close, which includes the
  overnight gap), ÷ the asset's average first-bar |return|.
- **Comparison:** linked minus placebo assets for the same jump.

**Pass:** CI > 0.

## S3 · Direction in sequence
For the +1 hour after the jump, does the asset move in the direction the pair moved in jumps before
2026-01-01? For each topic and asset, the training co-movement sign × the jump's sign is compared with the
sign of the asset's return.

**Pass:** hit rate CI lower bound > 52%. Expected to fail, given V2, V4 and M3.

**Reading:** S1 or S2 passing supports "the jump comes first, the stock follows". Neither proves cause: a
news story can reach Polymarket a little earlier than the stock market.

### Amendment before the final S1 run (13:58)
The first S1 run lined up jumps on the whole-hour grid. Stock bars end at :30, so "−1 h" overlapped the jump
itself, and requiring 7 consecutive bars left only 26 markets. S1 now defines the jump on each asset's own bar
grid, as V1 does (Δp over exactly the asset's bar hour = hour 0). Each lag only needs its own bars to be
consecutive. Pass rules unchanged. The first run's numbers are kept in the results section for the record.

## Results (2026-11-27 14:05; `results/20261127-1400_sequence/`)

Each value is the linked asset's |move| minus the placebo assets' |move|, in units of a normal hour for that
asset (1.0 = one normal hour). Hour 0 is the asset bar in which the event jumped.

| Hour vs jump | −3 | −2 | **−1** | **0** | **+1** | +2 | +3 |
|---|---|---|---|---|---|---|---|
| All (336 markets) | +0.13 | +0.34 | **+0.69** | **+0.45** | +0.06 (CI −0.07 to +0.19) | +0.19 | +0.13 |
| Without crypto bets and assets (227) | +0.15 | +0.36 | **+0.55** | **+0.44** | **+0.18 (CI +0.06 to +0.32)** | +0.22 | +0.12 |

| Test | Verdict | Result |
|---|---|---|
| **S1** after the jump, in trading hours | **fail** | (a) passes only without crypto: +0.18 at +1 h. (b) fails both ways: the linked asset moves **more in the hour before** the jump than after it (after − before: −1.24 overall, −0.46 without crypto). |
| **S2** jump while the market is closed → next open | **pass** | Next session's first-bar move is **+0.28 normal-units larger** for linked vs placebo assets (CI +0.20 to +0.38, 372 jumps); without crypto bets **+0.31** (CI +0.21 to +0.40, 303 jumps). |
| **S3** direction of the next hour | fail | 49.8% (CI 46.4–53.2%), a coin flip, as before. |

*First, misaligned S1 run (whole-hour grid, 26 markets), kept for the record: −1 h +1.01, 0 h +0.47, +1 h +0.24 (CI −0.29 to +0.97).*

### What this means
- **During US trading hours, the stock usually moves first or together with the event, not after it.** The
  biggest excess is in the hour *before* the Polymarket jump. Stocks react to news faster than Polymarket; in
  crypto this is mechanical (BTC moves, so "BTC above $X" bets jump). After the jump there is only a small
  continued excess (+0.18 without crypto). So an intraday jump alert says "this risk is live now", not "a move
  is coming".
- **Outside trading hours the order is forced, and the event does come first.** A linked bet jumping overnight
  or at the weekend is followed by a bigger move at the next open, for the linked holding vs unrelated assets.
  This is the sequential, before-the-stock-move evidence, and it is a product feature.
- Neither shows that the event *causes* the move. The same news reaches both, and Polymarket trades around the
  clock while stocks don't.
- Direction stays unpredictable (S3).
