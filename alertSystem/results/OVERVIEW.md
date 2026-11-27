# Overview of all topics

Generated 2026-11-27 01:59.

Order of preference (docs/00_PLAN.md): **T1 crypto → T2 events → F Polymarket-internal**.

## Connectivity

- Polymarket Gamma: ok
- Polymarket Data API: ok
- Polymarket CLOB: ok
- Yahoo Finance: ok
- Binance data: ok

## Collection


## Research

| topic | run | gate verdicts | decision |
|---|---|---|---|
| polymarket | [20261127-014406_polymarket](20261127-014406_polymarket/summary.md) | e0: descriptive, e1: descriptive, e2: fail, e3: fail, e4: fail, e5: descriptive | Pivot: fair-value / mispricing helper; refine the topic. |
| crypto | [20261127-014406_crypto](20261127-014406_crypto/summary.md) | c0: pass, c1: fail, c2: fail, c3: fail | T1 fails: Polymarket crypto markets do not lead spot. Move to T2 (event shocks -> assets). |
| events | [20261127-014406_events](20261127-014406_events/summary.md) | v0: pass, v1: pass, v2: pass, v3: pass, v4: fail, v5: pass | T2 works as a risk tool: Polymarket shocks move the assets they relate to (event exposure monitor). Shocks also lean on the next hour's direction (weak; see V5): show it as a hint, not a signal. Prices keep moving with net wallet flow; whether *skilled* wallets add to that is checked in V5. |
| wallets | [20261127-014406_wallets](20261127-014406_wallets/summary.md) | w0: pass, w1: fail, w2: pass, w3: pass, w4: fail, w5: pass, w6: fail | Passed: W2 (label jumps likely to stick or revert by who is behind them); W3 (early warning from unusual wallet activity); W5 (highlight the wallet type whose buying leads the price). W6 robustness: not all of them survive the 15-minute gap; only those listed in W6 go into the product. |
