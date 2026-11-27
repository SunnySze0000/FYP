# 12 · Do linked jumps add information beyond the VIX? (pre-registration)

*Written 2026-11-27 16:20 HKT, before running.*

**Question.** On some days options already price extra volatility: the VIX is high before a big scheduled event.
If our linked jumps only happen on such days, the alert tells a trader nothing the VIX didn't. So: does a linked
jump still predict a bigger move in the holding after controlling for what the VIX said beforehand?

**Data**
- Holdings: the 19 non-crypto US research assets.
- Hours: trading hours from Nov 2024 (when the Polymarket jump data starts) to Nov 2026.
- Outcome: |hourly return| ÷ the holding's average at that hour of day (1 = normal).

**Regression (OLS)** of the outcome on:
- **linked jump**: 1 if a linked bet jumped in this hour (for the first bar of a session, overnight since the last close);
- **unrelated jump**: the same, for bets not linked to the holding;
- **VIX level** before the hour (log, previous VIX bar);
- **recent volatility**: the holding's mean outcome over its previous 24 trading hours;
- hour-of-day and holding fixed effects.

95% CIs come from a bootstrap that resamples whole days (1,000 draws).

**Models**
- **M0** linked jump + fixed effects only;
- **M1** M0 + VIX level + recent volatility, i.e. what the market and the holding's own recent history already
  said before the hour (*the main test*);
- **M2** M1 + the VIX's own move in the same hour, a strict check: is the effect more than "the whole market got jumpy"?
- **Overnight** M1 on first-of-session bars only.

**Pass (main):** in M1, the linked-jump coefficient > 0 with CI > 0, and greater than the unrelated-jump
coefficient (CI of the difference > 0).

**Reading:**
- M1 passes → EventLens adds information beyond the VIX and recent volatility.
- M1 fails → the alert mostly repeats what was already priced.
- M2 is reported for context: if it stays positive, the effect is specific to the holding, not a market-wide move.

**Limitation.** The VIX prices S&P 500 volatility only. There is no implied volatility for each holding (e.g. oil
or gold options), so for non-equity holdings the control is incomplete.

## Results (2026-11-27 16:25, `results/20261127-1620_vix_control/vix_control.json`)

66,861 holding-hours from 19 holdings (Nov 2024 – Nov 2026); 1 = a normal move for that hour.

| Model | Linked jump | Unrelated jump | Linked − unrelated |
|---|---|---|---|
| M0: no controls | +0.25 (CI +0.18 to +0.33) | +0.18 | +0.07 (CI −0.00 to +0.14) |
| **M1: + VIX level + recent volatility** | **+0.17 (CI +0.10 to +0.24)** | +0.13 | **+0.04 (CI −0.03 to +0.11)** |
| M2: + the VIX's own move that hour | +0.17 (CI +0.10 to +0.24) | +0.12 | +0.05 (CI −0.02 to +0.11) |
| Overnight → first hour (M1) | +0.10 (CI −0.00 to +0.21) | +0.00 | +0.10 (CI −0.03 to +0.23) |

**Verdict: FAIL** (pre-registered rule: linked CI > 0 **and** linked > unrelated with CI > 0). The first half
passes; the second does not.

### What this means
1. **The jumps do carry information beyond the VIX.** Even knowing the VIX level and the holding's recent
   volatility beforehand, hours with a linked jump move about **17% more** than expected (CI +10% to +24%).
   About a third of the raw effect (+0.25 → +0.17) was "already priced" by the VIX and recent volatility; two
   thirds was not.
2. **But at this level the effect is mostly "news is happening", not "news about your holding".** Hours with
   *unrelated* jumps also move more (+0.13). The extra for the holding's *own* topics (+0.04) is not
   distinguishable from zero here. Jumps cluster in busy news hours, so linked and unrelated jumps often
   happen together.
3. **Overnight is the most holding-specific case:** linked +0.10 against unrelated +0.00, but the sample is
   smaller and the CI just touches 0.
4. **This weakens claims about specificity, not the risk signal.** The earlier V1/D1 tests compared linked vs
   placebo assets *for the same jump* and found a clear difference. This test asks a harder question (any
   hour, with all unrelated jumps as a control and the VIX controlled), and the specific part shrinks to a
   small, uncertain edge.

### Consequences for the product
- An alert is honestly described as **"event news is moving markets right now, and this one is linked to your
  holding"**. The general "news hour" signal is solid beyond the VIX. The claim that this holding will be hit
  harder than others is weak at the hourly level.
- Keep the overnight / next-open feature (D4), but test it again with more data before calling it holding-specific.
- **Limitation:** the VIX is S&P 500 implied volatility only. Oil, gold, rates and China holdings have their own
  option markets (OVX, GVZ, MOVE…), which were not available here.
