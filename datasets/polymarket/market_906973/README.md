# June 2026 Fed 25 bp cut: wallet trade snapshot

This folder is the shareable dataset. For collection commands and source links, see
[the parent guide](../README.md). No collection or Alchemy key is needed to read these files.

## Scope and measured coverage

| Item | Value |
|---|---|
| Fed decision outcome (`rate_outcome`) | `25 bps decrease` |
| Meeting | June 2026 |
| Event / market | `101772` / `906973` |
| Token outcomes | YES and NO for this one question |
| Collection date | October 6, 2026, UTC |
| Trade timestamps | `2025-12-11T08:03:11+00:00` to `2026-06-17T21:12:58+00:00` |
| API pages / accepted participant rows | 113 / 112,598 |
| Rejected rows | 0 |
| Wallet addresses / transaction hashes | 7,213 / 43,891 |
| YES / NO participant rows | 44,081 / 68,517 |
| BUY / SELL participant rows | 71,362 / 41,236 |
| Rows with repeated fingerprints, retained | 844 |
| Sampled transactions / matched API rows | 8 / 17 |
| Decoded fills / audited logs in those receipts | 18 / 164 |

All served API cursors were exhausted. The condition feed uses a fixed three-year window,
ignores start/end date filters, and has a minimum 0.01-share filter. A decoded SELL YES maker
fill of **0.003332 shares** in the March 2 sampled transaction is absent from the API table,
consistent with that filter. Thus cursor exhaustion does not establish complete on-chain history.

Only 17 participant rows are `matched_unique`; 112,581 remain `not_checked`. These checks
measure agreement for sampled transactions, not wallet skill or completeness.

## `wallet_trades.csv.gz`: 112,598 rows, 20 columns

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
| `chain_verification` | status string | `matched_unique` or `not_checked` in this snapshot; reruns may flag mismatches/ambiguity |
| `same_fingerprint_count` | positive integer | Number of accepted rows with the same fingerprint across the whole snapshot |

`(source_page, source_row)` identifies an API record within this snapshot. It is not stable
across fresh API collections. Repeated fingerprints are preserved because identical-looking
records can represent valid distinct fills; the 844 flagged rows have not been deduplicated.

`notional_usd` is participant gross notional. Do not sum both participants to claim market
volume. `signed_yes_shares` measures trade-flow direction, not reconstructed holdings or
probability. NO-token sales can increase YES-relative exposure without a YES purchase.

## `market_tokens.csv`: 2 rows, 7 columns

One row per YES/NO token. Both rows refer to the same Fed question.

| Column | Meaning |
|---|---|
| `event_id`, `market_id` | API event and market IDs, stored as strings |
| `meeting_month`, `rate_outcome` | Meeting and policy-outcome label from the team's probability CSV |
| `condition_id` | Gamma condition identifier for the market |
| `token_id`, `token_outcome` | Gamma token ID paired with its YES/NO label |

Join trades to this table on `token_id`, and to `../../forward_probabilities.csv` on
`market_id` (the actual repository path is `datasets/forward_probabilities.csv`). The existing
probability CSV has many dates per market, so joining only on `market_id` will repeat each trade
for every date. For daily analysis, first choose a UTC date/cutoff and aggregate the intended
wallet cohort, then join on `market_id` and observation date. Keep the policy outcome distinct
from YES/NO: this table does not contain the other June outcomes such as no change or a 50 bp cut.

## `wallet_activity.csv`: 7,213 rows, 10 columns

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

| File | Row meaning / count |
|---|---|
| `sampled_api_rows.csv` | 17 checked rows with the same schema as the main trade table |
| `api_reconciliation.csv` | 17 API rows matched against decoded fill candidates |
| `chain_to_api_reconciliation.csv` | 18 decoded fills checked in the reverse direction; one has no unique API match |
| `exchange_fills.csv` | 18 supported `OrderFilled` events across the sampled transactions |
| `log_audit.csv` | All 164 logs from those receipts, including summaries and non-fill events |

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
`matched_api_row` or `no_unique_api_match`. The latter exposes the 0.003332-share gap.

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

## JSON metadata and integrity

- `manifest.json`: collection request settings, per-page acquisition times/counts, cursor exhaustion,
  accepted/rejected counts, date range, address/transaction counts, and limitations.
- `verification/sample_plan.json`: deterministic time-spread sampling method and transaction list.
- `verification/report.json`: acquisition/check time, transaction-level log/fill/API counts,
  match results, reverse-check gap, and limitations.
- `SHA256SUMS`: hashes of the shared files, relative to this directory. To check on macOS,
  run `shasum -a 256 -c SHA256SUMS` from this folder.

Original API pages, receipts, blocks, and rejected-record outputs are retained locally under
ignored `tmp/`; they are not bundled here. The committed CSVs include derived provenance and
sample transaction identifiers so teammates can inspect or repeat checks with their own endpoint.
