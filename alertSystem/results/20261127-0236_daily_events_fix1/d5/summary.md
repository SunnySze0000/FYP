## D5 · Daily resolution

**Question.** Is a once-a-day summary still informative?

**Verdict: PASS.** Day level: on days a related market moves ≥ 10 points, related assets' daily move exceeds unrelated by +0.23× (CI +0.16 to +0.30, 397 markets); without crypto-price markets +0.11× (CI +0.04 to +0.17).

| metric | value |
|---|---|
| main.mean | 0.2268 |
| main.low | 0.1575 |
| main.high | 0.2981 |
| main.n | 397 |
| main.groups | 397 |
| main.p_two_sided | 0 |
| without_crypto_price_markets.mean | 0.1059 |
| without_crypto_price_markets.low | 0.0434 |
| without_crypto_price_markets.high | 0.1689 |
| without_crypto_price_markets.n | 329 |
| without_crypto_price_markets.groups | 329 |
| without_crypto_price_markets.p_two_sided | 0.0005 |

- Probability sampled at each asset's daily close (16:00 ET stocks, 00:00 UTC crypto).
- Pass rule: CI > 0. Not required to build; decides the daily digest.
