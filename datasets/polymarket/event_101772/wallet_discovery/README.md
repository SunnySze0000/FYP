# Wallet activity and candidate discovery

Event `101772`: five June Fed outcome markets. [Meeting overview](../README.md).

| File | Row meaning / scope |
|---|---|
| `wallet_market_activity.csv` | 40,164 wallet/market pairs over the full collected history; shows which policy outcomes each address traded |
| `wallet_summary_pre_cutoff.csv` | 23,672 wallets with activity strictly before `2026-05-31T00:00:00+00:00`; selection features and eligibility for all of them |
| `candidate_wallets.csv` | 20 candidates: 10 broad and 10 focused |
| `candidate_outcome_activity.csv` | 67 candidate/market pairs using only pre-cutoff records |
| `report.json` | Input hashes, window counts, filters, ranking rules and limitations |
| `SHA256SUMS` | Integrity checks for these discovery files |

## How selection works

All selection features use trade timestamps **strictly before 2026-05-31T00:00:00+00:00** (default:
before May 31 UTC, so the last included calendar day is May 30). Records at/after the cutoff
appear only in the full-history activity table. Full-history activity is descriptive and is not
an input to the shortlist. We use 441,581 pre-cutoff records and exclude 154,384
later records from selection. No final outcome, realized PnL, profitability or future trading is used.

Require at least 5 active UTC days, 10 distinct transactions, no more than 5% of records flagged
as duplicate candidates, no observed reconciliation issue in pre-cutoff records, and an address
other than the configured exchange contracts or zero address. 1,596 addresses qualify.
These are exploratory usability filters, not statistically validated measures of wallet quality.

The broad group has 3+ outcome markets and is ranked by market count, active days, then transaction
count. The focused group has 1-2 markets and is ranked by active days, then transaction count.
Address ascending breaks ties deterministically. Gross notional and sampled chain-check coverage
are reported but do not rank wallets. `candidate_number` is display order, not a skill score.

| Candidate | Address (shortened) | Group | Markets | Active days | Transactions | Two-sided markets |
|---|---|---|---:|---:|---:|---:|
| 1 | `0x1e9851cf…6345` | Broad | 5 | 111 | 1,437 | 5 |
| 2 | `0xec829eda…6eaa` | Broad | 5 | 109 | 1,403 | 5 |
| 3 | `0xe8dd7741…ec86` | Broad | 5 | 96 | 6,076 | 0 |
| 4 | `0x60fd421f…89a9` | Broad | 5 | 91 | 1,686 | 5 |
| 5 | `0x6c378973…d40f` | Broad | 5 | 90 | 717 | 5 |
| 6 | `0x21ffd2b7…0d71` | Broad | 5 | 86 | 974 | 5 |
| 7 | `0xbc54e696…680f` | Broad | 5 | 85 | 961 | 5 |
| 8 | `0xd32ce89f…a4c2` | Broad | 5 | 82 | 3,396 | 3 |
| 9 | `0xa3ad70cf…6866` | Broad | 5 | 79 | 3,021 | 0 |
| 10 | `0x7ac42386…4f44` | Broad | 5 | 78 | 611 | 5 |
| 11 | `0xd4b5cdba…fd07` | Focused | 1 | 38 | 456 | 1 |
| 12 | `0xa8b7f8b3…ee3c` | Focused | 2 | 36 | 246 | 2 |
| 13 | `0xde242261…25a8` | Focused | 2 | 36 | 180 | 2 |
| 14 | `0x4bac379d…02b1` | Focused | 1 | 34 | 3,836 | 1 |
| 15 | `0xc124bd6e…25cb` | Focused | 2 | 34 | 171 | 2 |
| 16 | `0xa3af760e…b7a6` | Focused | 2 | 27 | 228 | 1 |
| 17 | `0xb661ed6e…aa83` | Focused | 2 | 26 | 304 | 2 |
| 18 | `0x80302a5a…7b74` | Focused | 2 | 26 | 96 | 2 |
| 19 | `0x095dcfb1…52cf` | Focused | 2 | 25 | 335 | 0 |
| 20 | `0xa815f590…9cbe` | Focused | 1 | 25 | 200 | 1 |

## CSV fields and units

The wallet/market tables contain `event_id`, `meeting_month`, `market_id`, `rate_outcome`,
`condition_id`, `wallet_address`; first/last observed UTC trades; `participant_rows`,
`unique_transactions`, `active_days`, `gross_participant_notional_usd`,
`duplicate_candidate_rows`, `duplicate_candidate_fraction`, `chain_matched_rows`,
`chain_not_checked_rows`, `chain_issue_rows`, and `max_rows_in_one_day`.
Transaction/day counts are set unions within the row's scope. Duplicate rows remain counted.

For each category (`buy_yes`, `sell_yes`, `buy_no`, `sell_no`), `_shares` and `_notional_usd`
columns sum gross shares and collateral notional separately. `yes_trade_flow_shares` and
`no_trade_flow_shares` are bought minus sold for that particular token/question, not holdings.
`trades_both_directions_same_token` means BUY and SELL were observed for YES or for NO;
it does not establish arbitrage, market making or manipulation. [Source units](../../SCHEMA.md).

Wallet summaries union transactions and UTC days across markets. `markets_traded`, `market_ids`
and `rate_outcomes` identify the observed policy questions; lists use semicolons. `two_sided_markets`
counts markets with both trade directions for at least one token. `selection_cutoff_utc`,
`eligible`, and `eligibility_notes` make the decision auditable. Exclusion counts in the report
are nonexclusive because a wallet may fail several filters. `chain_issue_rows` counts sampled
records whose status is neither `matched_unique` nor `not_checked`.

Candidates add `candidate_number`, `selection_group`, `group_rank`, `selection_reason` and a
public `wallet_explorer_url`. No real-world identities or wallet-performance scores are inferred.
Use full addresses from the CSV; display addresses above are abbreviated.

## Interpretation and reproduction

These addresses are **candidates for historical investigation**, not proven smart wallets.
Trading multiple questions within June still supplies only one independent meeting. Sustained
activity and two-sided trading can reflect several strategies; high activity is not evidence of skill.
Next, collect earlier resolved-meeting histories and assess sample size before designing scores.
Our October collection is retrospective: this cutoff removes future trade timestamps, but it
does not prove these exact API records were available at the historical cutoff.

From the repository root, no network or API key is needed:

```sh
python3 -B scripts/polymarket/discover_wallets.py
```

`--cutoff` requires an explicit timezone; `--candidate-count` allows 10 through 20.
Rerunning replaces the discovery files and refreshes their checksums and the parent meeting
checksums. Source per-market exports are read-only. All decimal totals use decimal arithmetic;
participant notional is not market volume, and trade flow excludes position lifecycle operations.
