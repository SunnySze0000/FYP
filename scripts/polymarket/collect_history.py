#!/usr/bin/env python3
"""Resume a single market's served trade history from atomic raw page checkpoints."""
import argparse
import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from collect_pilot import array, clean_trades, fetch, utc_now, write_csv


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def collect(args):
    root = Path(args.output)
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    config = {"market_id": args.market_id, "page_size": args.page_size,
              "taker_only": False, "filter_type": "TOKENS", "filter_amount": "0.01"}
    config_path = root / "config.json"
    if config_path.exists():
        if json.loads(config_path.read_text()) != config:
            raise ValueError("Existing run configuration differs; use another output directory")
    else:
        atomic_json(config_path, config)
    with Path(args.input).open() as handle:
        local = [r for r in csv.DictReader(handle) if r["market_id"] == args.market_id]
    if not local or any(len({r[f] for r in local}) != 1 for f in ("event_id", "meeting_month", "outcome")):
        raise ValueError("Missing or inconsistent local market metadata")
    market_path = raw_dir / "market.json"
    if not market_path.exists():
        atomic_json(market_path, fetch("https://gamma-api.polymarket.com/markets/" + args.market_id))
    market = json.loads(market_path.read_text())
    tokens, labels = array(market["clobTokenIds"]), array(market["outcomes"])
    if str(market["id"]) != args.market_id or len(tokens) != 2 or len(set(tokens)) != 2 or set(labels) != {"Yes", "No"}:
        raise ValueError("Unexpected Gamma ID/token mapping")
    mapping = dict(zip(map(str, tokens), labels))
    market.update(local_event_id=local[0]["event_id"], local_meeting_month=local[0]["meeting_month"], local_rate_outcome=local[0]["outcome"])
    cursor, seen, raw, pages = None, set(), [], []
    exhausted = False
    for page in range(1, args.max_pages + 1):
        path = raw_dir / f"trades_page_{page:05d}.json"
        if path.exists():
            envelope = json.loads(path.read_text())
            if envelope["request_cursor"] != cursor:
                raise ValueError("Saved page cursor does not follow previous page")
        else:
            params = {"condition": market["conditionId"], "limit": args.page_size,
                      "taker_only": "false", "filter_type": "TOKENS", "filter_amount": "0.01"}
            if cursor:
                params["cursor"] = cursor
            response = fetch("https://data-api.polymarket.com/v2/trades?" + urlencode(params))
            if not isinstance(response.get("data"), list) or "next_cursor" not in response.get("pagination", {}):
                raise ValueError("Unexpected trade page envelope")
            envelope = {"collected_at_utc": utc_now(), "request_cursor": cursor, "response": response}
            atomic_json(path, envelope)
        response = envelope["response"]
        records = response["data"]
        raw.extend((page, index, row) for index, row in enumerate(records, 1))
        pages.append({"page": page, "rows": len(records), "collected_at_utc": envelope["collected_at_utc"]})
        cursor = response["pagination"]["next_cursor"]
        exhausted = not cursor
        atomic_json(root / "checkpoint.json", {"pages": len(pages), "raw_rows": len(raw), "next_cursor": cursor, "exhausted_api_cursor": exhausted})
        if page % 10 == 0 or exhausted:
            print(f"Pages {page}; participant rows {len(raw)}; cursor exhausted {exhausted}", flush=True)
        if exhausted:
            break
        if cursor in seen:
            raise ValueError("Repeated API cursor")
        seen.add(cursor)
    clean, rejected = clean_trades(raw, market, mapping)
    write_csv(root / "wallet_trades.csv", list(clean[0]) if clean else ["source_page", "source_row"], clean)
    write_csv(root / "market_tokens.csv", ["event_id", "market_id", "meeting_month", "rate_outcome", "condition_id", "token_id", "token_outcome"], [
        dict(event_id=local[0]["event_id"], market_id=args.market_id, meeting_month=local[0]["meeting_month"], rate_outcome=local[0]["outcome"], condition_id=market["conditionId"], token_id=t, token_outcome=o.upper()) for t, o in mapping.items()])
    atomic_json(root / "rejected_records.json", rejected)
    wallets = {}
    for row in clean:
        wallet = wallets.setdefault(row["wallet_address"], {
            "wallet_address":row["wallet_address"], "first_trade_utc":row["timestamp_utc"],
            "last_trade_utc":row["timestamp_utc"], "participant_rows":0, "transactions":set(),
            "buy_yes_shares":Decimal(0), "sell_yes_shares":Decimal(0),
            "buy_no_shares":Decimal(0), "sell_no_shares":Decimal(0),
            "gross_participant_notional_usd":Decimal(0)})
        wallet["first_trade_utc"] = min(wallet["first_trade_utc"],row["timestamp_utc"])
        wallet["last_trade_utc"] = max(wallet["last_trade_utc"],row["timestamp_utc"])
        wallet["participant_rows"] += 1
        wallet["transactions"].add(row["transaction_hash"])
        wallet[row["side"].lower()+"_"+row["token_outcome"].lower()+"_shares"] += Decimal(row["shares"])
        wallet["gross_participant_notional_usd"] += Decimal(row["notional_usd"])
    activity = []
    for address in sorted(wallets):
        wallet = wallets[address]
        wallet["unique_transactions"] = len(wallet.pop("transactions"))
        activity.append({k:str(v) if isinstance(v,Decimal) else v for k,v in wallet.items()})
    write_csv(root / "wallet_activity.csv",list(activity[0]) if activity else ["wallet_address"],activity)
    report = {**config, "exported_at_utc": utc_now(), "pages": pages, "raw_rows": len(raw),
              "clean_rows": len(clean), "rejected_rows": len(rejected),
              "unique_wallets": len({r["wallet_address"] for r in clean}),
              "unique_transactions": len({r["transaction_hash"] for r in clean}),
              "duplicate_fingerprint_rows": sum(r["same_fingerprint_count"] > 1 for r in clean),
              "minimum_timestamp_utc": min((r["timestamp_utc"] for r in clean), default=None),
              "maximum_timestamp_utc": max((r["timestamp_utc"] for r in clean), default=None),
              "side_counts": dict(Counter(r["side"] for r in clean)),
              "token_outcome_counts": dict(Counter(r["token_outcome"] for r in clean)),
              "next_cursor": cursor, "exhausted_api_cursor": exhausted,
              "coverage_note": "Served API history only: condition queries use a three-year window; minimum-size filter is 0.01 shares. Cursor exhaustion does not establish chain completeness.",
              "cleaning_note": "Participant records preserved, including repeated fingerprints. Do not sum both participants as market volume. Signed flow is not full holdings."}
    atomic_json(root / "manifest.json", report)
    print(json.dumps({k:v for k,v in report.items() if k != "pages"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-id", default="906973")
    parser.add_argument("--input", default="datasets/forward_probabilities.csv")
    parser.add_argument("--output", default="tmp/polymarket/history_market_906973")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 1000 or args.max_pages < 1:
        parser.error("page-size must be 1..1000 and max-pages positive")
    collect(args)
