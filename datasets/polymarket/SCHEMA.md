# Polymarket wallet CSV dictionary

## Four-wallet decision diagnostics

`event_101772/decision_review/` has three derived tables. Full method and column
interpretation are in its [guide](event_101772/decision_review/README.md).
`outcome_flows.csv` has one wallet/meeting/market/window row, including explicit
zero activity, four BUY/SELL × YES/NO share totals, signed YES-direction flow,
gross shares, a pre-cutoff daily quote, final label and score numerator.
`meeting_decisions.csv` aggregates markets once per wallet/meeting/window;
`wallet_diagnostics.csv` averages scored meetings equally per wallet/window.
Scores and share totals use decimals. IDs and addresses remain strings. Empty
scores signify abstention with an explicit `status`; empty directional descriptions
mean no flow with that sign. Booleans use `True`/`False`.

`netting_ratio` is absolute net flow divided by gross traded shares. The
`flow_alignment_score` divides the sum of net-flow × (result − quote) by gross
shares. It describes trade-flow association; it is not a probability, return,
holding, proper forecast score or validated skill measure. `positive_score_meetings`
counts positive diagnostics, not profitable meetings. Both `validated_smart_wallet`
and `production_weight_available` are false. These earlier records have
`chain_verification=not_checked`.

The schema is shared by the `market_<id>/` exports. Counts and coverage are recorded separately
in each market README and manifest. IDs are strings, timestamps are UTC, and decimal values
should be read without converting 256-bit token IDs to floating point.

## `wallet_trades.csv.gz`: 20 columns

One row is an **API participant record**. The API includes both maker and taker records.
One transaction can have multiple fills and one economic match can generate multiple records.
The table is a gzip-compressed CSV, not a different table format.

| Column | Type / unit | Meaning |
|---|---|---|
| `source_page` | integer, 1-based | Page in this frozen collection run |
| `source_row` | integer, 1-based | Record within that raw page |
| `record_fingerprint` | SHA-256 string | Hash of the original API record; diagnostic, not a canonical fill ID |
| `timestamp_utc` | ISO 8601 UTC | Trade timestamp converted from API Unix seconds |
| `event_id` | string ID | Polymarket event grouping for the meeting |
| `market_id` | string ID | Binary market/question; join to the existing probability CSV |
| `meeting_month` | `YYYY-MM` | Meeting month |
| `rate_outcome` | string | Fed policy outcome: `25 bps decrease` |
| `condition_id` | 0x-prefixed string | On-chain condition for resolution; not the API market ID |
| `token_id` | decimal string | 256-bit position-token ID; never parse as a floating-point number |
| `token_outcome` | `YES` / `NO` | Whether this token supports/opposes this market's question |
| `wallet_address` | lowercase 0x address | Participant/proxy wallet from the API; an address is not necessarily one person |
| `side` | `BUY` / `SELL` | Participant's action on the identified token |
| `shares` | positive decimal | Gross outcome-token shares traded |
| `price` | decimal, 0–1 | Gross collateral price per share |
| `notional_usd` | decimal | `shares × price`, in USD-denominated collateral units; excludes fees |
| `signed_yes_shares` | signed decimal | Positive for BUY YES / SELL NO; negative for SELL YES / BUY NO |
| `transaction_hash` | lowercase 0x string | Polygon settlement transaction; not a unique participant/fill key |
| `chain_verification` | status string | Verification status, including `matched_unique`, `not_checked`, mismatches, or ambiguity |
| `same_fingerprint_count` | positive integer | Number of accepted rows with the same fingerprint across the whole snapshot |

`(source_page, source_row)` identifies an API record within this snapshot. It is not stable
across fresh API collections. Repeated fingerprints are preserved because identical-looking
records can represent valid distinct fills; flagged rows have not been deduplicated.
When combining market folders, use `(market_id, source_page, source_row)` as the snapshot record key.

`notional_usd` is participant gross notional. Do not sum both participants to claim market
volume. `signed_yes_shares` measures trade-flow direction, not reconstructed holdings or
probability. NO-token sales can increase YES-relative exposure without a YES purchase.

## `market_tokens.csv`: 2 rows per market, 7 columns

One row per YES/NO token. Both rows refer to the same Fed question.

| Column | Meaning |
|---|---|
| `event_id`, `market_id` | API event and market IDs, stored as strings |
| `meeting_month`, `rate_outcome` | Meeting and policy-outcome label from the team's probability CSV |
| `condition_id` | Gamma condition identifier for the market |
| `token_id`, `token_outcome` | Gamma token ID paired with its YES/NO label |

Join trades to this table on `token_id`, and to the existing probability CSV on
`market_id` (the repository path is `datasets/forward_probabilities.csv`). The existing
probability CSV has many dates per market, so joining only on `market_id` will repeat each trade
for every date. For daily analysis, first choose a UTC date/cutoff and aggregate the intended
wallet cohort, then join on `market_id` and observation date. Keep the policy outcome distinct
from YES/NO: each market table contains only its own question; the meeting mapping includes all collected questions.

## `wallet_activity.csv`: one row per wallet per market, 10 columns

One descriptive row per wallet address in the accepted trade table.

| Column | Meaning |
|---|---|
| `wallet_address` | Lowercase wallet identifier |
| `first_trade_utc`, `last_trade_utc` | First and last observed trade in this market snapshot |
| `participant_rows` | Accepted API record count, including repeated-fingerprint candidates |
| `buy_yes_shares`, `sell_yes_shares` | Gross YES shares bought/sold, summed separately |
| `buy_no_shares`, `sell_no_shares` | Gross NO shares bought/sold, summed separately |
| `gross_participant_notional_usd` | Sum of that wallet's gross API notionals, excluding fees |
| `unique_transactions` | Distinct transaction hashes for that address |

These are activity summaries, not profit, full holdings, independent-person counts, or wallet
scores. Transfers, splits, merges, redemptions, and conversions are not reconstructed.
Wallet activity sums include unverified records and retained duplicate candidates.

## Verification CSVs

Counts vary by market; consult each market's `verification/report.json`.

| File | Row meaning |
|---|---|
| `sampled_api_rows.csv` | Sampled API records, with the main trade schema |
| `api_reconciliation.csv` | API-to-chain comparison per sampled API record |
| `chain_to_api_reconciliation.csv` | Chain-to-API comparison per decoded fill |
| `exchange_fills.csv` | Supported decoded exchange fill events |
| `log_audit.csv` | Every log in the sampled receipts |

### `api_reconciliation.csv`

`source_page`, `source_row` link back to the main CSV. `transaction_hash`, `wallet_address`,
`token_id`, and `side` identify the participant being compared. `api_shares`, `api_price` are
API values; `matched_log_index` identifies the uniquely matched event in that transaction.
`candidate_fill_count` counts wallet/token/side candidates; `matching_fill_count` also checks
shares and price within 0.000001. `status` records agreement, ambiguity, or mismatch.
`api_timestamp_utc`, `block_timestamp_utc`, and `timestamp_agrees` preserve the exact time check.
A `matched_unique` label requires exact timestamp agreement and one unambiguously claimed log.

### `chain_to_api_reconciliation.csv`

`transaction_hash` + `log_index` identify the fill. `market_id`, `token_id`, `shares` describe it.
`unique_api_matches` counts uniquely reconciled API rows for that event. `status` is
`matched_api_row`, `no_unique_api_match`, or `outside_local_market_mapping`.
The last label records fills for tokens outside the selected market; it is not an API gap for that market. A missing match can reflect the size filter, an unmapped market, or a reconciliation limitation; inspect the fill before interpreting it.

### `exchange_fills.csv`

| Columns | Meaning / units |
|---|---|
| `chain_id`, `timestamp_utc` | Polygon 137 and its block's UTC timestamp |
| `transaction_hash`, `block_number`, `block_hash`, `log_index` | Chain provenance; transaction hash plus log index is the canonical event key on this chain |
| `contract_address`, `event_name`, `exchange_version` | Emitting exchange, `OrderFilled`, and supported CTF V1/V2 layout |
| `order_hash` | Order identifier from the event |
| `wallet_address`, `event_maker_address` | Order owner from the event; these agree, including for a taker order |
| `event_taker_address` | Raw event counterparty field; can be the exchange, not necessarily a trader wallet |
| `execution_role` | `taker_order` when identified by an `OrdersMatched` summary, otherwise `maker_order` |
| `token_id`, `token_outcome`, `rate_outcome`, `condition_id`, `market_id` | Token linked to the local mapping; unsupported/unmapped tokens would leave mapping fields blank |
| `side` | Decoded BUY/SELL |
| `shares_raw`, `collateral_raw`, `fee_raw` | Exact unsigned on-chain integer amounts, stored as decimal strings |
| `shares`, `gross_notional_usd`, `price` | Scaled shares/collateral and their ratio; gross amounts exclude fees |
| `fee_asset`, `fee_token_id` | `outcome_token` and its ID for V1 BUY fees; `collateral` and asset sentinel `0` otherwise |
| `fee_shares`, `fee_usd` | Fee in its actual asset unit; inapplicable field is blank, not zero |
| `amount_decimals` | Six-decimal scaling used for these supported assets |
| `builder`, `metadata` | V2 event bytes32 fields; blank for V1 |

V1 BUY fees are deducted from outcome shares. V1 SELL and supported V2 fees use collateral.
Do not interpret every fee integer as dollars. The transaction sender may be a relayer;
wallet attribution comes from decoded events. `OrdersMatched` is a summary, not another fill.
Unknown events and contracts are not guessed into trades. Layouts follow pinned official source;
deployed bytecode has not been independently verified.

### `log_audit.csv`

`transaction_hash`, `log_index`, `contract_address`, and `topic0` retain log identity.
`classification` is `OrderFilled_decoded`, `OrdersMatched_summary_not_extra_trade`,
`not_decoded`, or `removed_log`. These labels describe decoder coverage, not invalidity.
