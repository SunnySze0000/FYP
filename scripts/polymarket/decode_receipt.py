#!/usr/bin/env python3
"""Decode supported historical/V2 CTF exchange fills and reconcile an API CSV.

Deliberately narrow: unknown contracts/topics/layouts stay in an audit table.
No wallet inference from transaction.from, and no generic transfer-to-trade conversion.
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from collect_pilot import save_json, write_csv

EXCHANGES = {"0xe111180000d2663c0091e4f400237545b87b996b",
             "0xe2222d279d744050d28e00520010520000310f59"}
FILLED = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
MATCHED = "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c"
SOURCE = "https://github.com/Polymarket/ctf-exchange-v2/blob/ccc0596074f4dfd62c944fbca4de252893b82b4b/src/exchange/mixins/Events.sol"
OLD_EXCHANGES = {"0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e", "0xc5d563a36ae78145c45a50134d48a1215220f80a"}
OLD_FILLED = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
OLD_MATCHED = "0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c"
OLD_SOURCE = "https://github.com/Polymarket/ctf-exchange/blob/ed5c7708b7be3aa98bf5f0c6602b57cc498e2ef4/src/exchange/interfaces/ITrading.sol"
SCALE = Decimal(1000000)


def layout(log):
    contract = log["address"].lower()
    if contract in EXCHANGES:
        return FILLED, MATCHED, "CTF_V2"
    if contract in OLD_EXCHANGES:
        return OLD_FILLED, OLD_MATCHED, "CTF_V1"
    return None, None, "unsupported"


def words(data, count):
    if not data.startswith("0x") or len(data[2:]) != count * 64:
        raise ValueError("unexpected ABI data length")
    return [data[2:][i:i+64] for i in range(0, count*64, 64)]


def address(topic):
    if len(topic) != 66 or topic[2:26] != "0" * 24:
        raise ValueError("invalid indexed address")
    return "0x" + topic[-40:].lower()


def decode(receipt, timestamp, mapping):
    if int(receipt["status"], 16) != 1:
        raise ValueError("failed transaction: no executed trades accepted")
    summaries = set()
    for log in receipt["logs"]:
        filled_topic, matched_topic, version = layout(log)
        if matched_topic and log["topics"] and log["topics"][0] == matched_topic and not log.get("removed"):
            if len(log["topics"]) != 3:
                raise ValueError("unexpected OrdersMatched topics")
            words(log["data"], 4)
            summaries.add((log["address"].lower(), log["topics"][1].lower(), address(log["topics"][2])))
    rows, audit = [], []
    for log in receipt["logs"]:
        topics = log["topics"]
        filled_topic, matched_topic, version = layout(log)
        entry = {"log_index": int(log["logIndex"], 16), "contract_address": log["address"].lower(),
                 "topic0": topics[0] if topics else "", "classification": "not_decoded"}
        if log.get("removed"):
            entry["classification"] = "removed_log"
        elif matched_topic and topics and topics[0] == matched_topic:
            entry["classification"] = "OrdersMatched_summary_not_extra_trade"
        elif filled_topic and topics and topics[0] == filled_topic:
            if len(topics) != 4:
                raise ValueError("unexpected OrderFilled topics")
            w = words(log["data"], 7 if version == "CTF_V2" else 5)
            if version == "CTF_V2":
                side, token, making, taking, fee = [int(v, 16) for v in w[:5]]
            else:
                maker_asset, taker_asset, making, taking, fee = [int(v, 16) for v in w]
                if (maker_asset == 0) == (taker_asset == 0):
                    raise ValueError("unsupported legacy asset pair")
                side = 0 if maker_asset == 0 else 1
                token = taker_asset if side == 0 else maker_asset
            if side not in (0, 1) or making <= 0 or taking <= 0:
                raise ValueError("invalid fill amounts/side")
            shares_raw, collateral_raw = (taking, making) if side == 0 else (making, taking)
            price = Decimal(collateral_raw) / Decimal(shares_raw)
            if not 0 <= price <= 1:
                raise ValueError("fill price outside supported binary range")
            wallet = address(topics[2])
            role = "taker_order" if (log["address"].lower(), topics[1].lower(), wallet) in summaries else "maker_order"
            token_meta = mapping.get(str(token), {})
            rows.append({"chain_id": 137, "timestamp_utc": timestamp,
                         "transaction_hash": receipt["transactionHash"].lower(),
                         "block_number": int(log["blockNumber"], 16), "block_hash": log["blockHash"].lower(),
                         "log_index": int(log["logIndex"], 16), "contract_address": log["address"].lower(),
                         "event_name": "OrderFilled", "exchange_version": version, "order_hash": topics[1].lower(),
                         "wallet_address": wallet, "event_maker_address": wallet,
                         "event_taker_address": address(topics[3]), "execution_role": role,
                         "token_id": str(token), "token_outcome": token_meta.get("token_outcome", ""),
                         "rate_outcome": token_meta.get("rate_outcome", ""),
                         "condition_id": token_meta.get("condition_id", ""),
                         "market_id": token_meta.get("market_id", ""), "side": "BUY" if side == 0 else "SELL",
                         "shares_raw": str(shares_raw), "collateral_raw": str(collateral_raw),
                         "fee_raw": str(fee), "shares": str(Decimal(shares_raw)/SCALE),
                         "gross_notional_usd": str(Decimal(collateral_raw)/SCALE),
                         "price": str(price),
                         "fee_asset": "outcome_token" if version == "CTF_V1" and side == 0 else "collateral",
                         "fee_token_id": str(token) if version == "CTF_V1" and side == 0 else "0",
                         "fee_shares": str(Decimal(fee)/SCALE) if version == "CTF_V1" and side == 0 else "",
                         "fee_usd": "" if version == "CTF_V1" and side == 0 else str(Decimal(fee)/SCALE),
                         "amount_decimals": 6, "builder": "0x"+w[5] if version == "CTF_V2" else "", "metadata": "0x"+w[6] if version == "CTF_V2" else ""})
            entry["classification"] = "OrderFilled_decoded"
        audit.append(entry)
    return rows, audit


def reconcile(api_rows, fills, tx):
    results = []
    for api in api_rows:
        if api["transaction_hash"].lower() != tx:
            continue
        candidates = [r for r in fills if r["wallet_address"] == api["wallet_address"].lower()
                      and r["token_id"] == api["token_id"] and r["side"] == api["side"]]
        exact = [r for r in candidates if abs(Decimal(r["shares"])-Decimal(api["shares"])) <= Decimal("0.000001")
                 and abs(Decimal(r["price"])-Decimal(api["price"])) <= Decimal("0.000001")]
        status = "matched_unique" if len(exact) == 1 else "ambiguous" if len(exact) > 1 else "amount_mismatch" if candidates else "no_fill_candidate"
        results.append({"source_page": api["source_page"], "source_row": api["source_row"],
                        "transaction_hash": tx, "wallet_address": api["wallet_address"],
                        "token_id": api["token_id"], "side": api["side"], "api_shares": api["shares"],
                        "api_price": api["price"], "status": status,
                        "matched_log_index": exact[0]["log_index"] if len(exact)==1 else "",
                        "matching_fill_count": len(exact), "candidate_fill_count": len(candidates)})
    # Prevent two indistinguishable API rows from both claiming one canonical fill.
    claimed = {}
    for result in results:
        if result["status"] == "matched_unique":
            claimed.setdefault(result["matched_log_index"], []).append(result)
    for group in claimed.values():
        if len(group) > 1:
            for result in group:
                result["status"] = "ambiguous_multiple_api_rows"
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--pilot-dir", required=True)
    args = parser.parse_args()
    root, pilot = Path(args.receipt_dir), Path(args.pilot_dir)
    receipt = json.loads((root/"receipt.json").read_text())
    block = json.loads((root/"block.json").read_text())
    if block["hash"].lower() != receipt["blockHash"].lower():
        raise ValueError("receipt/block hash mismatch")
    timestamp = datetime.fromtimestamp(int(block["timestamp"],16), timezone.utc).isoformat()
    with (pilot/"market_tokens.csv").open() as handle:
        mapping = {r["token_id"]:r for r in csv.DictReader(handle)}
    fills, audit = decode(receipt, timestamp, mapping)
    with (pilot/"wallet_trades.csv").open() as handle:
        comparisons = reconcile(list(csv.DictReader(handle)), fills, receipt["transactionHash"].lower())
    out = root / "decoded"
    out.mkdir(exist_ok=False)
    for name, rows, empty in [("exchange_fills.csv",fills,["transaction_hash","log_index"]),
                              ("log_audit.csv",audit,["log_index","classification"]),
                              ("api_reconciliation.csv",comparisons,["transaction_hash","status"])]:
        write_csv(out/name,list(rows[0]) if rows else empty,rows)
    report = {"receipt_logs":len(audit), "decoded_fill_events":len(fills),
              "api_rows_for_transaction":len(comparisons),
              "uniquely_matched_api_rows":sum(r["status"]=="matched_unique" for r in comparisons),
              "event_layout_sources":[SOURCE, OLD_SOURCE], "amount_decimals":6,
              "notes":["Six-decimal scaling validated against this pilot's API amounts; other deployments require their own scale check.",
                       "The event maker field identifies the order owner even for a taker order; OrdersMatched identifies that role.",
                       "OrdersMatched is a summary, not an additional fill. Transfers and lifecycle events remain undecoded in the audit.",
                       "Only receipt-matched API rows are checked. No chain-wide or historical completeness claim.",
                       "Layouts follow pinned official sources; deployed bytecode was not independently verified."]}
    save_json(out/"report.json",report)
    print(json.dumps({"output":str(out.resolve()),**report},indent=2))


if __name__ == "__main__":
    main()
