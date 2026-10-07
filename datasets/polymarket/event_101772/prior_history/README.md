# Candidate wallets: earlier Fed meeting history

This checks the existing 20-wallet shortlist against seven earlier team meetings: July,
September, October and December 2025; January, March and April 2026. [Candidate guide](../wallet_discovery/README.md).
Source: Gamma metadata and Polymarket Data API v2, with wallet+condition filters and UTC
trade timestamps strictly before `2026-05-31T00:00:00+00:00`. All wallet query cursors are exhausted.

Collected **120,000 accepted records** across 28 earlier markets. Of these,
**118,521** precede the per-meeting analysis cutoff.
**15 candidates** have observed pre-decision activity
in at least three earlier meetings. This is a history-review grouping, not a validated skill threshold.

| Candidate | Address (shortened) | Earlier meetings before decision cutoff | Pre-decision records | History review band |
|---|---|---:|---:|---|
| 1 | `0x1e9851cf…6345` | 3 | 4,480 | 3plus_prior_meetings |
| 2 | `0xec829eda…6eaa` | 3 | 3,907 | 3plus_prior_meetings |
| 3 | `0xe8dd7741…ec86` | 7 | 35,610 | 3plus_prior_meetings |
| 4 | `0x60fd421f…89a9` | 2 | 2,534 | 1to2_prior_meetings |
| 5 | `0x6c378973…d40f` | 2 | 799 | 1to2_prior_meetings |
| 6 | `0x21ffd2b7…0d71` | 7 | 7,517 | 3plus_prior_meetings |
| 7 | `0xbc54e696…680f` | 7 | 6,938 | 3plus_prior_meetings |
| 8 | `0xd32ce89f…a4c2` | 4 | 6,813 | 3plus_prior_meetings |
| 9 | `0xa3ad70cf…6866` | 5 | 13,055 | 3plus_prior_meetings |
| 10 | `0x7ac42386…4f44` | 3 | 1,095 | 3plus_prior_meetings |
| 11 | `0xd4b5cdba…fd07` | 0 | 0 | no_observed_pre_decision_history |
| 12 | `0xa8b7f8b3…ee3c` | 7 | 2,131 | 3plus_prior_meetings |
| 13 | `0xde242261…25a8` | 3 | 1,178 | 3plus_prior_meetings |
| 14 | `0x4bac379d…02b1` | 5 | 30,331 | 3plus_prior_meetings |
| 15 | `0xc124bd6e…25cb` | 4 | 118 | 3plus_prior_meetings |
| 16 | `0xa3af760e…b7a6` | 2 | 536 | 1to2_prior_meetings |
| 17 | `0xb661ed6e…aa83` | 4 | 173 | 3plus_prior_meetings |
| 18 | `0x80302a5a…7b74` | 1 | 57 | 1to2_prior_meetings |
| 19 | `0x095dcfb1…52cf` | 3 | 1,135 | 3plus_prior_meetings |
| 20 | `0xa815f590…9cbe` | 3 | 114 | 3plus_prior_meetings |

## Which earlier meetings have records?

✓ means at least one served trade before the declared decision cutoff; — means none observed.
This marks participation only. Exact trade counts are in `candidate_meeting_matrix.csv`.

| Candidate | 2025-07 | 2025-09 | 2025-10 | 2025-12 | 2026-01 | 2026-03 | 2026-04 |
|---|---|---|---|---|---|---|---|
| 1 | — | — | — | — | ✓ | ✓ | ✓ |
| 2 | — | — | — | — | ✓ | ✓ | ✓ |
| 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4 | — | — | — | — | — | ✓ | ✓ |
| 5 | — | — | — | — | — | ✓ | ✓ |
| 6 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 8 | — | — | — | ✓ | ✓ | ✓ | ✓ |
| 9 | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 10 | — | — | — | — | ✓ | ✓ | ✓ |
| 11 | — | — | — | — | — | — | — |
| 12 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 13 | — | — | — | — | ✓ | ✓ | ✓ |
| 14 | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 15 | ✓ | — | — | — | ✓ | ✓ | ✓ |
| 16 | — | — | — | — | — | ✓ | ✓ |
| 17 | — | — | — | ✓ | ✓ | ✓ | ✓ |
| 18 | — | — | — | — | — | — | ✓ |
| 19 | — | — | — | — | ✓ | ✓ | ✓ |
| 20 | — | ✓ | — | — | — | ✓ | ✓ |

## Files and row meanings

- `candidate_history_summary.csv`: one row per candidate. `queried_prior_meetings` is the search
  universe size; `meetings_with_any_served_trade` includes late trades, while
  `meetings_with_pre_decision_activity` counts independent meetings with at least one earlier
  trade. `pre_decision_meeting_months` is a semicolon list. Trade-row totals include retained
  duplicate candidates. `history_review_band` groups 0, 1-2, or 3+ observed meetings; it is not a
  skill score. `verified_original_resolution_timestamps=0`, `skill_score_available=False`.
- `candidate_meeting_activity.csv`: 20 × 7 = 140 candidate/meeting rows, including explicit zeros.
  Counts distinct transactions, days and markets within the pre-decision window, gross participant
  notional and duplicate-candidate rows; also records first/last served trade times, closure and
  current-resolution evidence flags. Counts across multiple outcome markets are one meeting.
- `candidate_meeting_matrix.csv`: 20 rows, with candidate/address/group and `pre_decision_meetings`;
  each `rows_YYYY_MM` column is the number of pre-decision participant records for that meeting.
- `prior_wallet_trades.csv.gz`: cleaned candidate participant records using the [trade schema](../../SCHEMA.md).
  Adds `source_query`, Gamma `market_end_date_utc`, `market_closed_at_utc`, `decision_cutoff_utc`,
  `before_decision_cutoff`, and `before_market_close`. Snapshot keys are wallet + source_query +
  source_page + source_row. All `chain_verification` values are `not_checked`.
- `prior_market_tokens.csv`: 56 token rows linking 28 markets to seven events, YES/NO labels,
  end/closure/decision times, current final YES outcomes and team labels. Final labels agree;
  they are audit metadata, not candidate-selection features. Metadata acquisition times are retained.
- `coverage.json`: original query condition lists, per-page timestamps/counts, raw/accepted/rejected
  totals and cursor exhaustion for all 40 wallet/condition-group queries.
- `report.json`: counts, source shortlist hash, filters, meeting-count distribution and limitations.
- `SHA256SUMS`: integrity checks for these outputs.

## Evidence boundaries

Gamma currently reports each market resolved with final prices of 0/1. Its `closedTime` precedes
the May 31 selection cutoff, but it does not supply an independently verified original resolution
timestamp here. We therefore call these **earlier closed meetings with current resolved labels**,
not proof that every resolution was finalized or every API record available at that historical time.

Participation before a decision cutoff is a more useful starting point than simply trading a
winning token afterward. We set that cutoff to **Gamma endDate minus 24 hours** for each event,
validate it is consistent across its markets, and exclude trades at/after it from the history counts.
This is a declared conservative convention, not an exact announcement-time reconstruction.
Presence in several prior meetings makes case-study investigation feasible; it does not prove
correct decisions, independence of addresses, profit or skill. Trade-flow records do not reconstruct
holdings or account for transfers, splits, merges and redemptions.

Zero means no served records for these queried markets under these filters. It does not mean the
wallet never traded other markets or had no on-chain activity. The 0.01-share floor and API coverage
still apply. New prior records have not been Polygon-verified. Raw metadata, responses, rejected rows
and resume checkpoints remain in ignored `tmp/polymarket/prior_candidate_history/`.

## Reproduce

From the repository root, no Polymarket API key is required:

```sh
python3 -B scripts/polymarket/collect_prior_history.py
```

Use `--workers` to control concurrent wallets; `--max-pages` caps pages per condition group.
Saved metadata/query pages are reused and validated on reruns. Use another `--raw` directory
for a fresh acquisition; exports are replaced and checksums refreshed. The script does not
change the shortlist or the original five June datasets, and produces no performance score.
