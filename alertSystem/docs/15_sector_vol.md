# V3 · Controls with sector volatility gauges

*Pre-registered 2026-11-27 17:15 HKT, before any gauge data was downloaded.*

## Question

Doc 12 showed that the VIX explains much of the raw linked-jump effect. Doc 13 then compared holdings in the same
hour, which removes anything common to all holdings (the VIX included), and found +7% for linked holdings
(+12% overnight). One gap is left: **sector-specific fear**. An oil bet may jump at the same moment the oil
volatility gauge jumps, and the gauge, not the bet, may carry the news. V3 adds each holding's own gauge as a
control.

## Gauges (Yahoo, 60-minute bars, 730 days)

| Gauge | Holdings it controls |
|---|---|
| ^OVX (oil) | USO, XLE |
| ^GVZ (gold) | GLD |
| ^MOVE (Treasury bonds) | TLT, IEF, SHY |
| ^VXFXI (China) | FXI, KWEB, EEM |
| ^VXN (Nasdaq-100) | QQQ, NVDA, SMH, MSFT |

Holdings without a gauge (SPY, IWM, UUP, XLF, ITA, EZU, HYG) are dropped from this test. A gauge with fewer than
1,000 hourly bars is dropped, and the report says so.

## Design

Doc 13 design (same-hour and same-holding fixed effects, outcome = |return| ÷ the holding's mean for that hour,
recent 24 h volatility, day-cluster bootstrap with 1,000 draws), with two extra controls per holding-hour: the
log level of its gauge at the start of the hour, and the absolute log change of its gauge over the hour.

## Pass rules

1. **Primary:** the linked effect with gauge controls is > 0, with a 95% CI above 0.
2. **Overnight:** the same, for the first bar after a gap (the open). Reported; it decides D4's wording.
3. Reported: how much of the linked effect the gauges absorb (with vs without them, on the same rows).

Outcome → product: if rule 1 passes, the claim "beyond the VIX and sector fear" stands. If it fails, the
dashboard says the jump may be telling you what the sector gauge already shows.

## Result (run 2026-11-27 17:15 HKT, `results/20261127-1715_sector_vol/`)

Gauge download: ^OVX 4,804 bars, ^GVZ 4,795, ^VXN 4,794, ^VXFXI 1,761, **^MOVE 955 → dropped** (below the
pre-registered 1,000), so TLT, IEF and SHY are not in this test. Holdings tested: USO, XLE, GLD, FXI, KWEB, EEM,
QQQ, NVDA, SMH, MSFT (6,362 holding-hours).

| Hours | Linked effect, no gauge | Linked effect, with own gauge |
|---|---|---|
| All | +10.9% (CI +3.5 to +18.5) | **+5.4% (CI −2.0 to +12.8)** |
| Overnight → open | – | **+13.4% (CI +1.5 to +26.0)** |
| Intraday | – | −0.5% (CI −11.4 to +8.7) |

The gauges themselves matter a lot: a 1% move in the holding's own gauge in the same hour goes with an
8.1% larger move (CI +6.1 to +10.2).

- **Rule 1 (all hours, with gauges): FAIL.** About half of the linked effect is shared with the sector gauge.
- **Rule 2 (overnight, with gauges): PASS.** The open effect stays at +13%.
- Caveat (noted, not used to rescue rule 1): the gauge's change is measured in the same hour as the move, so
  part of it is the move itself (a gauge is computed from option prices on the same asset). That makes this a
  strict control.

**Implication.** "Watch the open" (D4) stands: overnight bet jumps tell you something the sector gauge does not.
During trading hours, a jump mostly says what the sector's own fear gauge already says. The app must not claim
"beyond sector fear" for intraday alerts. They are already worded as explanations (v1.2), so that stays.
