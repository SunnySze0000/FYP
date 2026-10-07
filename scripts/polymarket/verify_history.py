#!/usr/bin/env python3
"""Deterministically sample history across time and reconcile Alchemy CLI receipts."""
import argparse
import csv
import gzip
import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from collect_history import atomic_json
from collect_pilot import write_csv, utc_now
from decode_receipt import decode, reconcile


def reverse_reconcile(fills, comparisons):
    matched = Counter((r["transaction_hash"], str(r["matched_log_index"])) for r in comparisons if r["status"] == "matched_unique")
    return [{"transaction_hash":r["transaction_hash"], "log_index":r["log_index"],
             "market_id":r["market_id"], "token_id":r["token_id"], "shares":r["shares"],
             "unique_api_matches":matched[(r["transaction_hash"],str(r["log_index"]))],
             "status":"matched_api_row" if matched[(r["transaction_hash"],str(r["log_index"]))] else "outside_local_market_mapping" if not r["market_id"] else "no_unique_api_match"}
            for r in fills]


def cli(*command):
    result = subprocess.run(["alchemy", "--json", "--no-interactive", "-n", "polygon-mainnet", "--timeout", "30000", "evm", *command], capture_output=True, text=True)
    if result.returncode:
        # Do not propagate CLI diagnostics that could contain credential-bearing URLs.
        raise RuntimeError("Alchemy CLI failed; no response accepted")
    return json.loads(result.stdout)


def verify(root, count, export_dir=None):
    if not os.environ.get("ALCHEMY_API_KEY"):
        raise ValueError("Set ALCHEMY_API_KEY in your environment")
    if cli("rpc", "ethChainId", "--params", "[]") != "0x89":
        raise ValueError("Alchemy response is not Polygon mainnet")
    manifest = json.loads((root / "manifest.json").read_text())
    if not manifest["exhausted_api_cursor"]:
        raise ValueError("Finish served API pagination before selecting the history sample")
    with (root / "wallet_trades.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    with (root / "market_tokens.csv").open() as handle:
        mapping = {r["token_id"]:r for r in csv.DictReader(handle)}
    by_tx = {}
    for row in rows:
        by_tx.setdefault(row["transaction_hash"], row)
    transactions = sorted(by_tx.values(), key=lambda r:(r["timestamp_utc"], r["transaction_hash"]))
    earliest, latest = [datetime.fromisoformat(r["timestamp_utc"]).timestamp() for r in (transactions[0], transactions[-1])]
    selected = []
    for index in range(count):
        target = earliest + (latest-earliest) * index / max(1,count-1)
        candidate = min(transactions, key=lambda r:(abs(datetime.fromisoformat(r["timestamp_utc"]).timestamp()-target),r["transaction_hash"]))
        if candidate["transaction_hash"] not in {r["transaction_hash"] for r in selected}:
            selected.append(candidate)
    out = root / "verification"
    out.mkdir(exist_ok=True)
    atomic_json(out / "sample_plan.json", {"method":"Nearest available transaction to equally spaced UTC time targets, with earliest/latest included", "requested_transactions":count, "transactions":[{"transaction_hash":r["transaction_hash"],"api_timestamp_utc":r["timestamp_utc"]} for r in selected]})
    fills_all, audits_all, comparisons_all, sample_reports = [], [], [], []
    for selected_row in selected:
        tx = selected_row["transaction_hash"]
        raw = out / "raw" / tx
        raw.mkdir(parents=True, exist_ok=True)
        receipt_path, block_path = raw / "receipt.json", raw / "block.json"
        if not receipt_path.exists():
            atomic_json(receipt_path, cli("receipt", tx))
        receipt = json.loads(receipt_path.read_text())
        if receipt["transactionHash"].lower() != tx:
            raise ValueError("Receipt transaction mismatch")
        if not block_path.exists():
            atomic_json(block_path, cli("rpc", "ethGetBlockByHash", "--params", json.dumps([receipt["blockHash"], False])))
        block = json.loads(block_path.read_text())
        if block["hash"].lower() != receipt["blockHash"].lower():
            raise ValueError("Block/receipt mismatch")
        timestamp = datetime.fromtimestamp(int(block["timestamp"],16), timezone.utc).isoformat()
        fills, audits = decode(receipt, timestamp, mapping)
        for audit in audits:
            audit["transaction_hash"] = tx
        comparisons = reconcile(rows, fills, tx)
        for comparison in comparisons:
            api = next(r for r in rows if r["source_page"] == comparison["source_page"] and r["source_row"] == comparison["source_row"])
            comparison["api_timestamp_utc"] = api["timestamp_utc"]
            comparison["block_timestamp_utc"] = timestamp
            comparison["timestamp_agrees"] = api["timestamp_utc"] == timestamp
            if not comparison["timestamp_agrees"] and comparison["status"] == "matched_unique":
                comparison["status"] = "timestamp_mismatch"
        fills_all.extend(fills)
        audits_all.extend(audits)
        comparisons_all.extend(comparisons)
        report = {"transaction_hash":tx,"timestamp_utc":timestamp,"receipt_status":int(receipt["status"],16),"receipt_logs":len(audits),"decoded_fills":len(fills),"api_rows":len(comparisons),"status_counts":dict(Counter(r["status"] for r in comparisons)),"exchange_versions":sorted({r["exchange_version"] for r in fills})}
        sample_reports.append(report)
        print(json.dumps(report), flush=True)
    for name, data in [("exchange_fills.csv", fills_all),("log_audit.csv",audits_all),("api_reconciliation.csv",comparisons_all)]:
        write_csv(out/name, list(data[0]) if data else ["transaction_hash"], data)
    reverse = reverse_reconcile(fills_all,comparisons_all)
    write_csv(out / "chain_to_api_reconciliation.csv",list(reverse[0]) if reverse else ["transaction_hash"],reverse)
    statuses = {(r["source_page"],r["source_row"]):r["status"] for r in comparisons_all}
    for row in rows:
        row["chain_verification"] = statuses.get((row["source_page"],row["source_row"]),"not_checked")
    write_csv(root / "wallet_trades.csv",list(rows[0]),rows)
    checked_rows = [r for r in rows if r["chain_verification"] != "not_checked"]
    write_csv(out / "sampled_api_rows.csv",list(rows[0]),checked_rows)
    atomic_json(out / "report.json", {"verified_at_utc":utc_now(),"sample_transactions":len(selected),"sample_api_rows":len(checked_rows),"status_counts":dict(Counter(r["status"] for r in comparisons_all)),"chain_fill_status_counts":dict(Counter(r["status"] for r in reverse)),"transactions":sample_reports,"limitations":["Deterministic time-spread sample, not a statistical completeness test or chain-wide collection.","Only configured CTF V1/V2 fill layouts supported; other logs remain in the audit.","Participant notionals exclude fees; preserve raw integer amounts and transaction/log keys.","Unsampled rows remain not_checked. Matching fields does not prove wallet skill."]})
    if export_dir:
        export_dir.mkdir(parents=True, exist_ok=True)
        temporary = export_dir / "wallet_trades.csv.gz.partial"
        with (root / "wallet_trades.csv").open("rb") as source, temporary.open("wb") as target:
            with gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        temporary.replace(export_dir / "wallet_trades.csv.gz")
        for name in ("market_tokens.csv", "wallet_activity.csv", "manifest.json"):
            shutil.copyfile(root / name, export_dir / name)
        for name in ("sample_plan.json", "sampled_api_rows.csv", "exchange_fills.csv", "log_audit.csv", "api_reconciliation.csv", "chain_to_api_reconciliation.csv", "report.json"):
            target = export_dir / "verification" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(out / name, target)
        print("Shareable dataset exported to " + str(export_dir.resolve()), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", default="tmp/polymarket/history_market_906973")
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--export-dir", type=Path, help="Optionally package compressed full CSV, wallet activity, mapping and sample audit")
    args = parser.parse_args()
    if args.sample_count < 2:
        parser.error("sample-count must be at least 2")
    verify(Path(args.history_dir), args.sample_count, args.export_dir)
