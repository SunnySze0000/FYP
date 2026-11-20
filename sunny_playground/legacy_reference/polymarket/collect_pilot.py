#!/usr/bin/env python3
"""Small, standard-library-only Polymarket/Polygon collection pilot."""
import argparse
import csv
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    for attempt in range(4):
        try:
            request = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "EventLens-research-pilot/1"})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < 3:
                delay = error.headers.get("Retry-After", "")
                time.sleep(min(float(delay), 10) if delay.isdigit() else 2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {error.code}; response not collected") from None
        except (URLError, TimeoutError):
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError("Network request failed; endpoint details omitted") from None


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def write_csv(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def array(value):
    return json.loads(value) if isinstance(value, str) else value


def clean_trades(raw, market, mapping):
    """Preserve multiplicity; quarantine invalid rows rather than guessing."""
    clean, rejected = [], []
    for page, row_index, record in raw:
        try:
            token = str(record["token_id"])
            outcome = mapping[token]
            wallet = record["proxy_wallet"].lower()
            tx = record["transaction_hash"].lower()
            if not re.fullmatch(r"0x[0-9a-f]{40}", wallet):
                raise ValueError("invalid wallet")
            if not re.fullmatch(r"0x[0-9a-f]{64}", tx):
                raise ValueError("invalid transaction hash")
            if record["condition_id"].lower() != market["conditionId"].lower():
                raise ValueError("condition mismatch")
            side = record["side"].upper()
            if side not in ("BUY", "SELL") or outcome not in ("Yes", "No"):
                raise ValueError("unsupported side/outcome")
            price, size = Decimal(str(record["price"])), Decimal(str(record["size"]))
            if not price.is_finite() or not size.is_finite() or not 0 <= price <= 1 or size <= 0:
                raise ValueError("invalid price/size")
            timestamp = int(record["timestamp"])
            fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            support = (side == "BUY") == (outcome == "Yes")
            clean.append({
                "source_page": page, "source_row": row_index,
                "record_fingerprint": fingerprint,
                "timestamp_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                "event_id": market["local_event_id"], "market_id": str(market["id"]),
                "meeting_month": market["local_meeting_month"],
                "rate_outcome": market["local_rate_outcome"],
                "condition_id": record["condition_id"].lower(), "token_id": token,
                "token_outcome": outcome.upper(), "wallet_address": wallet,
                "side": side, "shares": str(size), "price": str(price),
                "notional_usd": str(size * price),
                "signed_yes_shares": str(size if support else -size),
                "transaction_hash": tx, "chain_verification": "not_checked",
            })
        except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError, OSError) as error:
            rejected.append({"source_page": page, "source_row": row_index,
                             "reason": str(error), "record": record})
    counts = Counter(r["record_fingerprint"] for r in clean)
    for record in clean:
        record["same_fingerprint_count"] = counts[record["record_fingerprint"]]
    return clean, rejected


def pilot(args):
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    out = root / ("market_" + args.market_id + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    out.mkdir()
    raw_dir = out / "raw"
    raw_dir.mkdir()
    with Path(args.input).open() as handle:
        local = [r for r in csv.DictReader(handle) if r["market_id"] == args.market_id]
    if not local:
        raise ValueError("market_id not found in input CSV")
    for field in ("event_id", "meeting_month", "outcome"):
        if len({r[field] for r in local}) != 1:
            raise ValueError(f"inconsistent input {field}")
    market = fetch("https://gamma-api.polymarket.com/markets/" + args.market_id)
    save_json(raw_dir / "market.json", market)
    if str(market["id"]) != args.market_id:
        raise ValueError("Gamma market_id mismatch")
    tokens, labels = array(market["clobTokenIds"]), array(market["outcomes"])
    if len(tokens) != len(labels) or len(set(tokens)) != len(tokens) or set(labels) != {"Yes", "No"}:
        raise ValueError("unexpected token mapping")
    mapping = dict(zip(map(str, tokens), labels))
    market.update(local_event_id=local[0]["event_id"], local_meeting_month=local[0]["meeting_month"], local_rate_outcome=local[0]["outcome"])
    write_csv(out / "market_tokens.csv", ["event_id", "market_id", "meeting_month", "rate_outcome", "condition_id", "token_id", "token_outcome"], [
        dict(event_id=local[0]["event_id"], market_id=args.market_id, meeting_month=local[0]["meeting_month"], rate_outcome=local[0]["outcome"], condition_id=market["conditionId"], token_id=token, token_outcome=label.upper()) for token, label in mapping.items()])
    params = {"condition": market["conditionId"], "limit": args.page_size, "taker_only": "false"}
    raw, cursors, pages = [], set(), []
    next_cursor = None
    for page in range(1, args.max_pages + 1):
        response = fetch("https://data-api.polymarket.com/v2/trades?" + urlencode(params))
        collected = utc_now()
        save_json(raw_dir / f"trades_page_{page:04d}.json", response)
        records = response["data"]
        if not isinstance(records, list):
            raise ValueError("unexpected trades envelope")
        raw.extend((page, i, r) for i, r in enumerate(records, 1))
        pages.append({"page": page, "rows": len(records), "collected_at_utc": collected})
        next_cursor = response["pagination"]["next_cursor"]
        if not next_cursor:
            break
        if next_cursor in cursors:
            raise ValueError("repeated pagination cursor")
        cursors.add(next_cursor)
        params["cursor"] = next_cursor
    clean, rejected = clean_trades(raw, market, mapping)
    fields = list(clean[0]) if clean else ["source_page", "source_row", "transaction_hash"]
    write_csv(out / "wallet_trades.csv", fields, clean)
    save_json(out / "rejected_records.json", rejected)
    manifest = {"collected_at_utc": utc_now(), "market_id": args.market_id,
                "source": "Polymarket Data API v2 indexed trades", "taker_only": False,
                "page_size": args.page_size, "pages": pages,
                "exhausted_api_cursor": next_cursor is None,
                "next_cursor": next_cursor, "raw_rows": len(raw), "clean_rows": len(clean),
                "rejected_rows": len(rejected), "unique_wallets": len({r['wallet_address'] for r in clean}),
                "duplicate_fingerprint_rows": sum(r['same_fingerprint_count'] > 1 for r in clean),
                "minimum_timestamp_utc": min((r['timestamp_utc'] for r in clean), default=None),
                "maximum_timestamp_utc": max((r['timestamp_utc'] for r in clean), default=None),
                "coverage_note": "Cursor exhaustion covers served API records only. Market queries serve a fixed three-year window, ignore start/end, and apply the API minimum-size filter. Historical chain completeness is not established.",
                "cleaning_note": "Identical-looking rows retained; fingerprints are diagnostics, not canonical fill IDs. Maker/taker rows must not be summed as market volume. Signed flow is an exposure change, not full holdings."}
    save_json(out / "manifest.json", manifest)
    print(json.dumps({"output": str(out.resolve()), **{k:manifest[k] for k in ['raw_rows','clean_rows','rejected_rows','unique_wallets','exhausted_api_cursor']}}, indent=2))


def receipt(args):
    endpoint = os.environ.get("ALCHEMY_POLYGON_RPC_URL")
    if not endpoint:
        raise ValueError("Set ALCHEMY_POLYGON_RPC_URL locally first")
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", args.tx):
        raise ValueError("invalid transaction hash")
    def rpc(method, params):
        result = fetch(endpoint, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in result:
            raise RuntimeError("RPC returned an error; check your network/plan")
        return result["result"]
    if rpc("eth_chainId", []) != "0x89":
        raise ValueError("Endpoint is not Polygon PoS mainnet (chain ID 137)")
    value = rpc("eth_getTransactionReceipt", [args.tx])
    if value is None:
        raise ValueError("Receipt unavailable")
    if value["transactionHash"].lower() != args.tx.lower():
        raise ValueError("receipt transaction hash mismatch")
    out = Path(args.output) / args.tx.lower()
    out.mkdir(parents=True, exist_ok=False)
    save_json(out / "receipt.json", value)
    block = rpc("eth_getBlockByHash", [value["blockHash"], False])
    save_json(out / "block.json", block)
    timestamp = datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc).isoformat()
    rows = []
    for log in value["logs"]:
        rows.append({"chain_id": 137, "timestamp_utc": timestamp,
                     "block_number": int(log["blockNumber"], 16), "block_hash": log["blockHash"].lower(),
                     "transaction_hash": log["transactionHash"].lower(), "log_index": int(log["logIndex"], 16),
                     "contract_address": log["address"].lower(), "topic0": log["topics"][0] if log["topics"] else "",
                     "topics_json": json.dumps(log["topics"]), "data_hex": log["data"],
                     "removed": log.get("removed", False), "receipt_status": int(value["status"], 16)})
    fields = list(rows[0]) if rows else ["transaction_hash", "log_index", "data_hex"]
    write_csv(out / "receipt_logs.csv", fields, rows)
    save_json(out / "manifest.json", {"collected_at_utc": utc_now(), "source": "Alchemy Polygon RPC",
                                     "transaction_hash": args.tx.lower(), "logs": len(rows),
                                     "note": "Logs flattened, not ABI-decoded. A receipt alone does not verify API trade amounts or wallet attribution."})
    print(json.dumps({"output": str(out.resolve()), "logs": len(rows)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("pilot", help="Collect a bounded sample and clean it")
    p.add_argument("--market-id", default="906973")
    p.add_argument("--input", default="datasets/forward_probabilities.csv")
    p.add_argument("--output", default="tmp/polymarket")
    p.add_argument("--page-size", type=int, default=50)
    p.add_argument("--max-pages", type=int, default=2)
    p.set_defaults(run=pilot)
    r = commands.add_parser("receipt", help="Fetch and flatten one Polygon receipt")
    r.add_argument("--tx", required=True)
    r.add_argument("--output", default="tmp/polymarket/receipts")
    r.set_defaults(run=receipt)
    args = parser.parse_args()
    if args.command == "pilot" and (not 1 <= args.page_size <= 1000 or args.max_pages < 1 or not args.market_id.isdigit()):
        parser.error("Use a numeric market ID, page size 1–1000, and positive max-pages")
    try:
        args.run(args)
    except (RuntimeError, ValueError, KeyError) as error:
        parser.exit(1, f"Collection stopped: {error}\n")


if __name__ == "__main__":
    main()
