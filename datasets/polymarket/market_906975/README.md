# 2026-06 Fed: 25 bps increase

This is the cleaned API participant dataset for market **906975**, event **101772**.
See the [shared CSV dictionary](../SCHEMA.md) for every column, unit, join key, and verification file.
See the [meeting inventory](../event_101772/README.md) to find the other outcome markets.

| Measure | Result |
|---|---:|
| Accepted participant records | 106,377 |
| Wallet addresses | 5,871 |
| Transaction hashes | 44,217 |
| Rejected records | 0 |
| Rows with repeated fingerprints, retained | 314 |
| Earliest trade, UTC | 2025-12-11T08:03:11+00:00 |
| Latest trade, UTC | 2026-06-17T20:35:47+00:00 |
| Sample transactions | 4 |
| Sample API rows / unique chain matches | 16 / 16 |
| Local chain fills without unique API match | 0 |

`wallet_trades.csv.gz` contains the full cleaned trade table; `wallet_activity.csv` summarizes
each address; `market_tokens.csv` maps the market to its condition and YES/NO tokens.
`manifest.json` records request settings, collection timestamps and page coverage.
`verification/` contains sampled API rows, decoded Polygon fills, log audit, both comparison
directions and a report. `SHA256SUMS` checks this snapshot's files.

The served API cursor is exhausted, with a 0.01-share minimum filter. This is not complete
chain history. Only sampled rows are checked; remaining rows are `not_checked`. Unknown or
other-market receipt logs are retained and distinguished from local-market API gaps.
Participant notionals must not be summed as market volume. Repeated fingerprints are retained.
This snapshot contains no wallet scores, full holdings or adjusted probabilities.
