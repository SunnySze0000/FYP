# V4 · Same-hour test on the cleanest links only

*Pre-registered 2026-11-27 16:50 HKT, before running.*

## Question

Doc 13 found that a holding moves +7% more than other holdings in the same hour when one of its linked bets
jumps. If the link is real, the effect should be **stronger on the cleanest links** (the event acts on the
holding directly) than on loose links (the event acts through the wider market). If it is not stronger, the
+7% may be general event noise rather than the link itself. M1 (learned links) needs this answer: it tells us
whether tighter links are worth learning.

## Clean vs loose (fixed before the run)

| Group | Clean (direct channel) | Loose (indirect) |
|---|---|---|
| rates | TLT, IEF, SHY | UUP, XLF |
| macro | – | SPY, TLT, GLD, IWM |
| trade_china | FXI, KWEB | EEM, SPY |
| energy_mideast | USO, XLE | GLD |
| war_europe | ITA, EZU | USO, GLD |
| ai_tech | NVDA, SMH | QQQ, MSFT |

us_politics and crypto stay out, as in doc 13. A holding-hour is **clean** if at least one clean-linked bet
jumped; otherwise **loose** if at least one loose-linked bet jumped.

## Design

Same as doc 13: outcome = |return| ÷ the holding's mean for that hour of day; same-hour and same-holding fixed
effects; recent 24 h volatility as a control; day-cluster bootstrap (1,000 draws).

## Pass rules

1. **Primary:** clean effect > 0, 95% CI above 0.
2. **Secondary:** clean − loose > 0, 95% CI above 0.
3. Reported, no rule: the same split overnight and intraday.

Outcome → product: if 1 and 2 pass, links get a "direct / indirect" label and M1 trains on direct links first.
If 1 passes but 2 fails, both kinds stay, with no label. If 1 fails, the link list needs review before M1.

## Result (run 2026-11-27 16:55 HKT, `results/20261127-1650_clean_links/`)

| Hours | Clean links | Loose links | Clean − loose |
|---|---|---|---|
| All (14,401 holding-hours; 1,956 clean, 1,481 loose) | **+10.6%** (CI +4.0 to +17.5) | +1.9% (CI −4.4 to +8.5) | +8.7% (CI −0.3 to +17.6) |
| Overnight → open | **+15.9%** (CI +5.2 to +27.0) | +6.6% (CI −2.5 to +15.7) | +9.2% (CI −3.5 to +22.0) |
| Intraday | +5.9% (CI −2.1 to +13.8) | −2.6% (CI −11.0 to +5.5) | +8.4% (CI −3.2 to +20.1) |

- **Rule 1 (clean > 0): PASS.** Clean links give +10.6%, more than the +7% of all links together.
- **Rule 2 (clean > loose): FAIL, narrowly.** The gap is +8.7 points, but the CI just touches zero.
- Loose links on their own show no effect in any split. The doc 13 effect comes almost entirely from clean links.

**Implication.** The link itself matters: a direct channel (oil bet → USO/XLE, Fed bet → bonds, China bet →
FXI/KWEB, AI bet → NVDA/SMH, Ukraine bet → ITA/EZU) carries the signal; indirect links add little. As
pre-registered, both kinds stay in the product with no label (rule 2 failed), but the dashboard sorts direct
links first, and M1 should treat "direct channel" as its target. More data (V5) would decide rule 2.
