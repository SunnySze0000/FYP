# Polymarket Fed wallet dataset

Start with [the collected dataset and CSV dictionary](market_906973/README.md).
This snapshot covers **one binary market**: whether the Fed would cut rates by 25 bps
at its June 2026 meeting (market `906973`). It connects the team's probability CSV to
public wallet trades and sampled Polygon settlement records.

| File | Use |
|---|---|
| `market_906973/wallet_trades.csv.gz` | Full cleaned participant trade table; decompress or read gzip directly |
| `market_906973/wallet_activity.csv` | Browse wallet activity and identify candidates for later analysis |
| `market_906973/market_tokens.csv` | Join market/event IDs to condition and YES/NO token IDs |
| `market_906973/manifest.json` | Collection counts, dates, request settings, and page coverage |
| `market_906973/verification/` | Small readable CSVs showing sampled API/chain agreement and an observed gap |
| `market_906973/SHA256SUMS` | Integrity checks for the shared snapshot files |

The snapshot has **112,598 participant rows**, **7,213 addresses**, and **43,891 transactions**,
from December 11, 2025 through June 17, 2026, UTC. Eight sampled transactions yielded
17 uniquely matched API rows and one additional tiny on-chain fill absent from the API.
This is served API history, not a complete chain archive or a smart-wallet score.

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
See the [CSV dictionary](market_906973/README.md) for units, row meanings, and join keys.
The main CSV is approximately 50 MB uncompressed and 8.84 MB compressed.

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

## Source and method references

The reusable scripts are under `scripts/polymarket/`:

| Script | Responsibility |
|---|---|
| `collect_history.py` | Resumable public API collection, cleaning, wallet activity, coverage manifest |
| `verify_history.py` | Alchemy CLI receipt/block collection, sampled reconciliation, compressed export |
| `decode_receipt.py` | Supported V1/V2 fill decoding and participant matching |
| `collect_pilot.py` | Shared validation/CSV helpers and the original bounded-pilot commands; use the history workflow above for this dataset |

- [Gamma market metadata](https://gamma-api.polymarket.com/markets/906973)
- [Data API v2 schema](https://data-api.polymarket.com/v2/openapi.json)
- [Polymarket contracts](https://docs.polymarket.com/resources/contracts)
- [Pinned historical fill ABI](https://github.com/Polymarket/ctf-exchange/blob/ed5c7708b7be3aa98bf5f0c6602b57cc498e2ef4/src/exchange/interfaces/ITrading.sol)
- [Pinned historical settlement/fee logic](https://github.com/Polymarket/ctf-exchange/blob/ed5c7708b7be3aa98bf5f0c6602b57cc498e2ef4/src/exchange/mixins/Trading.sol)
- [Pinned V2 fill ABI](https://github.com/Polymarket/ctf-exchange-v2/blob/ccc0596074f4dfd62c944fbca4de252893b82b4b/src/exchange/mixins/Events.sol)

The current collector covers a single market, not all 43 team markets. Wallet scores, full
holdings, position lifecycle decoding, and adjusted probabilities are future work. Eligibility
and scores must use only information available before each forecast cutoff.
