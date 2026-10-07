# Fed meeting 2026-06: all 5 outcome markets

Event `101772` links the five market questions in the team's probability CSV.
Each market has one condition and two YES/NO tokens. [CSV dictionary](../SCHEMA.md).

| Market | Fed outcome | Participant rows | Wallets | Sample API matches |
|---|---|---:|---:|---:|
| [906972](../market_906972/README.md) | 50+ bps decrease | 141,769 | 10,860 | 11/11 |
| [906973](../market_906973/README.md) | 25 bps decrease | 112,598 | 7,213 | 17/17 |
| [906974](../market_906974/README.md) | No change | 176,039 | 9,926 | 8/8 |
| [906975](../market_906975/README.md) | 25 bps increase | 106,377 | 5,871 | 16/16 |
| [906976](../market_906976/README.md) | 50+ bps increase | 59,182 | 6,294 | 9/9 |

Combined: **595,965 participant rows**, **30,404 distinct addresses**,
and **247,968 distinct transactions**. All 5 served API cursors are exhausted.
There are **61/61 matched sampled API rows**
across 24 market/transaction checks.

## Files

- `market_inventory.csv`: one row per market, with coverage counts, UTC dates, condition ID,
  sample-check counts and a relative directory link. `participant_rows` counts accepted records;
  `local_fills_without_unique_api_match` counts supported local fills lacking a unique API match.
- `market_tokens.csv`: the combined 10-row event/market/condition/YES-NO mapping; shared schema.
- `summary.json`: union address/transaction counts, additive row/check counts, and limitations.
- `SHA256SUMS`: hashes of these meeting-index files.

Trade CSVs remain in their individual market folders; the index does not duplicate them.
Per-market wallet and transaction counts overlap and must not be added to estimate distinct
participants. One transaction may involve multiple markets. Gross participant notional is not
market volume. API size filtering and sampled verification mean chain completeness is not established.
The original 25 bp cut snapshot is preserved; the other four were collected afterward.
Wallet scoring and probability adjustment remain separate next steps.
