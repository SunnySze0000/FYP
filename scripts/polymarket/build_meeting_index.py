#!/usr/bin/env python3
"""Build a meeting inventory and token mapping from completed per-market exports."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from collect_history import atomic_json
from collect_pilot import write_csv


def checksums(directory):
    rows = [hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.relative_to(directory).as_posix()
            for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
    (directory / "SHA256SUMS").write_text("\n".join(rows) + "\n")


def build(root, source, event_id):
    with source.open() as handle:
        local = {r["market_id"]:r for r in csv.DictReader(handle) if r["event_id"] == event_id}
    if not local or len({r["meeting_month"] for r in local.values()}) != 1:
        raise ValueError("Missing event or inconsistent meeting month")
    inventory, tokens, wallets, transactions, sampled_transactions = [], [], set(), set(), set()
    for market_id, meta in sorted(local.items()):
        directory = root / ("market_" + market_id)
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["market_id"] != market_id or not manifest["exhausted_api_cursor"]:
            raise ValueError("Market ID mismatch or unfinished served API pagination")
        with (directory / "market_tokens.csv").open() as handle:
            mapping = list(csv.DictReader(handle))
        if len(mapping) != 2 or any(r["event_id"] != event_id or r["rate_outcome"] != meta["outcome"] for r in mapping):
            raise ValueError("Invalid local event/token mapping")
        tokens.extend(mapping)
        count = 0
        with gzip.open(directory / "wallet_trades.csv.gz", "rt", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["market_id"] != market_id or row["event_id"] != event_id:
                    raise ValueError("Trade belongs to another event/market")
                count += 1
                wallets.add(row["wallet_address"])
                transactions.add(row["transaction_hash"])
        if count != manifest["clean_rows"]:
            raise ValueError("Export row count differs from manifest")
        report = json.loads((directory / "verification" / "report.json").read_text())
        sampled_transactions.update(r["transaction_hash"] for r in report["transactions"])
        inventory.append({"event_id":event_id, "meeting_month":meta["meeting_month"],
                          "market_id":market_id, "rate_outcome":meta["outcome"],
                          "condition_id":mapping[0]["condition_id"], "participant_rows":count,
                          "unique_wallets":manifest["unique_wallets"], "unique_transactions":manifest["unique_transactions"],
                          "minimum_timestamp_utc":manifest["minimum_timestamp_utc"],
                          "maximum_timestamp_utc":manifest["maximum_timestamp_utc"],
                          "rejected_rows":manifest["rejected_rows"],
                          "duplicate_fingerprint_rows":manifest["duplicate_fingerprint_rows"],
                          "exhausted_api_cursor":True, "sample_transactions":report["sample_transactions"],
                          "sample_api_rows":report["sample_api_rows"],
                          "matched_api_rows":report["status_counts"].get("matched_unique",0),
                          "local_fills_without_unique_api_match":report["chain_fill_status_counts"].get("no_unique_api_match",0),
                          "market_directory":"../market_"+market_id})
        if market_id != "906973":
            text = f"""# {meta['meeting_month']} Fed: {meta['outcome']}

This is the cleaned API participant dataset for market **{market_id}**, event **{event_id}**.
See the [shared CSV dictionary](../SCHEMA.md) for every column, unit, join key, and verification file.
See the [meeting inventory](../event_{event_id}/README.md) to find the other outcome markets.

| Measure | Result |
|---|---:|
| Accepted participant records | {count:,} |
| Wallet addresses | {manifest['unique_wallets']:,} |
| Transaction hashes | {manifest['unique_transactions']:,} |
| Rejected records | {manifest['rejected_rows']:,} |
| Rows with repeated fingerprints, retained | {manifest['duplicate_fingerprint_rows']:,} |
| Earliest trade, UTC | {manifest['minimum_timestamp_utc']} |
| Latest trade, UTC | {manifest['maximum_timestamp_utc']} |
| Sample transactions | {report['sample_transactions']} |
| Sample API rows / unique chain matches | {report['sample_api_rows']} / {report['status_counts'].get('matched_unique',0)} |
| Local chain fills without unique API match | {report['chain_fill_status_counts'].get('no_unique_api_match',0)} |

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
"""
            (directory / "README.md").write_text(text)
            checksums(directory)
    if len({r["condition_id"] for r in tokens}) != len(local) or len({r["token_id"] for r in tokens}) != 2*len(local):
        raise ValueError("Conditions/tokens overlap unexpectedly between markets")
    out = root / ("event_" + event_id)
    out.mkdir(exist_ok=True)
    write_csv(out / "market_inventory.csv",list(inventory[0]),inventory)
    write_csv(out / "market_tokens.csv",list(tokens[0]),tokens)
    summary = {"event_id":event_id, "meeting_month":next(iter(local.values()))["meeting_month"],
               "markets":len(local), "participant_rows":sum(r["participant_rows"] for r in inventory),
               "unique_wallets_across_markets":len(wallets), "unique_transactions_across_markets":len(transactions),
               "sample_transaction_checks":sum(r["sample_transactions"] for r in inventory),
               "unique_sample_transactions_across_markets":len(sampled_transactions),
               "sample_api_rows":sum(r["sample_api_rows"] for r in inventory),
               "matched_api_rows":sum(r["matched_api_rows"] for r in inventory),
               "rejected_rows":sum(r["rejected_rows"] for r in inventory),
               "all_served_api_cursors_exhausted":True,
               "notes":["Wallet/transaction counts are set unions; per-market counts overlap.",
                        "Participant rows include both sides and retained duplicate candidates; their sum is not market volume.",
                        "Different markets were collected separately, not as a synchronized chain snapshot.",
                        "Receipt verification is sampled. The fixed three-year API window and 0.01-share floor limit coverage."]}
    atomic_json(out / "summary.json",summary)
    table = "\n".join(f"| [{r['market_id']}]({r['market_directory']}/README.md) | {r['rate_outcome']} | {r['participant_rows']:,} | {r['unique_wallets']:,} | {r['matched_api_rows']}/{r['sample_api_rows']} |" for r in inventory)
    (out / "README.md").write_text(f"""# Fed meeting {summary['meeting_month']}: all {len(local)} outcome markets

Event `{event_id}` links the five market questions in the team's probability CSV.
Each market has one condition and two YES/NO tokens. [CSV dictionary](../SCHEMA.md).

| Market | Fed outcome | Participant rows | Wallets | Sample API matches |
|---|---|---:|---:|---:|
{table}

Combined: **{summary['participant_rows']:,} participant rows**, **{len(wallets):,} distinct addresses**,
and **{len(transactions):,} distinct transactions**. All {len(local)} served API cursors are exhausted.
There are **{summary['matched_api_rows']}/{summary['sample_api_rows']} matched sampled API rows**
across {summary['sample_transaction_checks']} market/transaction checks.

## Files

- `market_inventory.csv`: one row per market, with coverage counts, UTC dates, condition ID,
  sample-check counts and a relative directory link. `participant_rows` counts accepted records;
  `local_fills_without_unique_api_match` counts supported local fills lacking a unique API match.
- `market_tokens.csv`: the combined {len(tokens)}-row event/market/condition/YES-NO mapping; shared schema.
- `summary.json`: union address/transaction counts, additive row/check counts, and limitations.
- `SHA256SUMS`: hashes of these meeting-index files.

{('[Wallet activity and candidate discovery](wallet_discovery/README.md): combined outcome activity and a pre-cutoff exploratory shortlist.' if (out / 'wallet_discovery' / 'README.md').exists() else '')}

{('[Earlier candidate meeting histories](prior_history/README.md): independent prior-meeting coverage and explicit zero states.' if (out / 'prior_history' / 'README.md').exists() else '')}

{('[Four-wallet decision review](decision_review/README.md): pre-cutoff flows, retrospective diagnostics and a probability-evaluation protocol.' if (out / 'decision_review' / 'README.md').exists() else '')}

Trade CSVs remain in their individual market folders; the index does not duplicate them.
Per-market wallet and transaction counts overlap and must not be added to estimate distinct
participants. One transaction may involve multiple markets. Gross participant notional is not
market volume. API size filtering and sampled verification mean chain completeness is not established.
The original 25 bp cut snapshot is preserved; the other four were collected afterward.
Wallet diagnostics remain exploratory; probability adjustment requires separate validation.
""")
    checksums(out)
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id",default="101772")
    parser.add_argument("--dataset-root",type=Path,default=Path("datasets/polymarket"))
    parser.add_argument("--input",type=Path,default=Path("datasets/forward_probabilities.csv"))
    args = parser.parse_args()
    build(args.dataset_root,args.input,args.event_id)
