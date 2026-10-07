# Polymarket Fed wallet dataset

Start with [the June meeting inventory](event_101772/README.md) and
[the shared CSV dictionary](SCHEMA.md). The exports cover **all five June 2026 Fed outcome
markets** in the team's probability CSV: 50+ bp decrease, 25 bp decrease, no change,
25 bp increase, and 50+ bp increase. Each question has separate YES/NO tokens.

| File / directory | Use |
|---|---|
| `event_101772/market_inventory.csv` | Per-market record counts, dates, conditions and sample-check coverage |
| `event_101772/market_tokens.csv` | Combined mapping for five conditions and ten YES/NO tokens |
| `event_101772/summary.json` | Combined record counts and distinct address/transaction counts |
| `market_<id>/wallet_trades.csv.gz` | Full cleaned participant records for that market |
| `market_<id>/wallet_activity.csv` | Per-wallet descriptive activity for that market |
| `market_<id>/verification/` | Small readable tables comparing sampled API records with Polygon fills |
| `market_<id>/SHA256SUMS` | Integrity checks for that shared market snapshot |

See the inventory for measured coverage. The original 25 bp cut snapshot is preserved;
the other four were collected afterward. The exports contain served API history with
sampled Polygon verification, not a complete chain archive or smart-wallet scores.
Per-market wallet and transaction counts overlap; the meeting summary uses set unions.

## Read the data without collecting it again

From the repository root, using only Python's standard library:

```python
import csv
import gzip

with gzip.open("datasets/polymarket/market_906973/wallet_trades.csv.gz", "rt", newline="") as f:
    trades = csv.DictReader(f)
    print(next(trades))
```

Keep IDs as strings, particularly 256-bit token IDs. All timestamps have explicit UTC offsets.
See the [CSV dictionary](SCHEMA.md) for units, row meanings, and join keys.
The original 25 bp cut CSV is approximately 50 MB uncompressed and 8.84 MB compressed; sizes vary by market.

## Reproduce collection and cleaning

Python 3 is sufficient for the public API collector; no API key or additional Python package
is required. Run from the repository root:

```sh
python3 -B scripts/polymarket/collect_history.py
```

The collector reads `datasets/forward_probabilities.csv`, fetches Gamma market/token metadata,
and follows Data API v2 cursors with `taker_only=false`, 1,000 records per page, and a
0.01-share minimum filter. Outputs go to `tmp/polymarket/history_market_906973/`.

Raw pages are atomically saved with request cursors and collection times. Rerun the same
command to resume missing pages. It rejects configuration changes within an existing run.
`--max-pages` is a safety cap; only `exhausted_api_cursor=true` means the served cursor ended.
To collect a fresh snapshot, use a new `--output` directory. Existing runs reuse frozen metadata
and cached pages. API responses may change, so a fresh collection need not be byte-identical.

Cleaning validates market/condition/token mappings, wallet and transaction formats, BUY/SELL,
price and share ranges; normalizes addresses and UTC timestamps; calculates decimal amounts;
and quarantines invalid rows. Repeated fingerprints are flagged and retained, not deduplicated.
The checkpoint, raw responses, rejected-record file, and full local exports stay under ignored `tmp/`.

## Reproduce sampled Polygon checks and export

Install the official Alchemy CLI (`@alchemy/cli`) separately and ensure `alchemy` is on PATH.
Supply your own Polygon API key locally. In zsh, this avoids putting its literal value in history:

```sh
read -rs 'ALCHEMY_API_KEY?Paste your Alchemy API key: '
export ALCHEMY_API_KEY
python3 -B scripts/polymarket/verify_history.py --sample-count 8 \
  --export-dir datasets/polymarket/market_906973
unset ALCHEMY_API_KEY
```

For a different history directory, also pass `--history-dir PATH`. Verification checks Polygon
chain ID 137 and selects transactions nearest eight evenly spaced UTC time targets, including
the earliest/latest available trades. Receipt and block responses are cached locally.
The decoder supports the configured CTF V1/V2 exchange layouts; unknown logs remain in the audit.

Matching checks wallet, token, side, shares, price, and block timestamp. Share/price tolerance is
0.000001; timestamps must agree exactly. Multiple API rows claiming one log are ambiguous.
Reverse reconciliation also records decoded fills without a unique API match.
Only sampled API rows receive verification labels; other rows remain `not_checked`.

Export replaces files in the requested destination. Use another `--export-dir` when preserving
this committed snapshot. Re-exporting collection alone resets local verification labels;
rerun verification before packaging. After intentionally replacing the shared snapshot,
refresh its documented counts and `SHA256SUMS` before committing.

## Reproduce the four additional markets and meeting index

Use explicit market IDs and separate local directories. The same resume and coverage rules apply:

```sh
for market in 906972 906974 906975 906976; do
  python3 -B scripts/polymarket/collect_history.py --market-id "$market" \
    --output "tmp/polymarket/history_market_$market" --max-pages 2000
done
```

With your Alchemy key exported as above, verify and package each new market:

```sh
for market in 906972 906974 906975 906976; do
  python3 -B scripts/polymarket/verify_history.py \
    --history-dir "tmp/polymarket/history_market_$market" --sample-count 4 \
    --export-dir "datasets/polymarket/market_$market"
done
python3 -B scripts/polymarket/build_meeting_index.py
```

The index builder validates all five completed exports against the team's event/market list,
writes the meeting inventory and combined token mapping, computes union counts, and creates
README/checksum files for the new market folders. It preserves the original `market_906973/`
snapshot. The original market has eight sampled transaction checks; the four additions use
four each. Inspect mismatch/ambiguity statuses and reverse-check gaps rather than assuming
all future runs will agree. Fills outside a market's two-token mapping are separately labeled.

## Combine activity and shortlist candidates

The [wallet discovery guide](event_101772/wallet_discovery/README.md) contains the combined
wallet/outcome table and 20 candidates. Selection uses only trades strictly before
`2026-05-31T00:00:00+00:00`, with two groups: ten broadly active across 3+ outcomes and ten
focused on 1-2 outcomes. Eligibility and ranking are activity-based, not performance scores.
The full-history activity table is descriptive and separate from pre-cutoff selection inputs.

Run locally without network access or keys:

```sh
python3 -B scripts/polymarket/discover_wallets.py
```

See the discovery README for thresholds, every output column, input hashes and limitations.
Historical timestamps are filtered retrospectively; these are not contemporaneously archived
API snapshots. Earlier independent meetings are needed before evaluating wallet skill.

## Check candidates' earlier Fed histories

The [prior-history guide](event_101772/prior_history/README.md) reports the 20 candidates'
served records for the seven earlier meetings in the team's existing CSV. Each candidate/meeting
pair has an explicit row, including zero observed activity. Counts distinguish all served trades
from trades before a declared cutoff one day before Gamma's meeting endDate.

```sh
python3 -B scripts/polymarket/collect_prior_history.py
```

The queries use public wallet+condition filters, a UTC end bound before candidate selection,
and resumable cursors. They require no API key. Current resolved labels and historical closure
times are recorded separately from the unverified original resolution timestamps. These histories
establish whether case-study records exist; they do not establish profit, holdings or predictive skill.

## Source and method references

The reusable scripts are under `scripts/polymarket/`:

| Script | Responsibility |
|---|---|
| `collect_history.py` | Resumable public API collection, cleaning, wallet activity, coverage manifest |
| `verify_history.py` | Alchemy CLI receipt/block collection, sampled reconciliation, compressed export |
| `decode_receipt.py` | Supported V1/V2 fill decoding and participant matching |
| `build_meeting_index.py` | Validate exported markets, summarize meeting coverage and generate new README/checksum files |
| `discover_wallets.py` | Aggregate wallet/outcome activity and build an auditable retrospective candidate shortlist |
| `collect_prior_history.py` | Collect candidates' earlier team Fed trades and report independent meeting coverage |
| `collect_pilot.py` | Shared validation/CSV helpers and the original bounded-pilot commands; use the history workflow above for this dataset |

- [Gamma market metadata](https://gamma-api.polymarket.com/markets/906973)
- [Data API v2 schema](https://data-api.polymarket.com/v2/openapi.json)
- [Polymarket contracts](https://docs.polymarket.com/resources/contracts)
- [Pinned historical fill ABI](https://github.com/Polymarket/ctf-exchange/blob/ed5c7708b7be3aa98bf5f0c6602b57cc498e2ef4/src/exchange/interfaces/ITrading.sol)
- [Pinned historical settlement/fee logic](https://github.com/Polymarket/ctf-exchange/blob/ed5c7708b7be3aa98bf5f0c6602b57cc498e2ef4/src/exchange/mixins/Trading.sol)
- [Pinned V2 fill ABI](https://github.com/Polymarket/ctf-exchange-v2/blob/ccc0596074f4dfd62c944fbca4de252893b82b4b/src/exchange/mixins/Events.sol)

The collected exports cover five of the 43 team markets. Wallet scores, full holdings,
position lifecycle decoding, and adjusted probabilities are future work. Eligibility
and scores must use only information available before each forecast cutoff.
