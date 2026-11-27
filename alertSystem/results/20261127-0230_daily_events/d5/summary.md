## D5 · Daily resolution

**Question.** Is a once-a-day summary still informative?

**Verdict: PASS.** Day level: on days a related market moves ≥ 10 points, related assets' daily move exceeds unrelated by +0.23× (CI +0.16 to +0.29, 412 markets); without crypto-price markets +0.10× (CI +0.04 to +0.16).

| metric | value |
|---|---|
| main.mean | 0.2262 |
| main.low | 0.1626 |
| main.high | 0.295 |
| main.n | 412 |
| main.groups | 412 |
| main.p_two_sided | 0 |
| without_crypto_price_markets.mean | 0.1018 |
| without_crypto_price_markets.low | 0.03775 |
| without_crypto_price_markets.high | 0.1631 |
| without_crypto_price_markets.n | 339 |
| without_crypto_price_markets.groups | 339 |
| without_crypto_price_markets.p_two_sided | 0.001 |

- Probability sampled at each asset's daily close (16:00 ET stocks, 00:00 UTC crypto).
- Pass rule: CI > 0. Not required to build; decides the daily digest.
