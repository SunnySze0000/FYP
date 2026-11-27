"""Raw API trade records -> canonical trade rows."""

from __future__ import annotations

import pandas as pd

from walletlens.data.schema import TRADE_COLUMNS, tx_key


def normalize_trade_records(records: list[dict], market: dict) -> tuple[pd.DataFrame, dict]:
    """Map Data API ``/v2/trades`` records of one market to ``TRADE_COLUMNS``.

    Returns the table and a dict counting rejected records by reason.
    """
    tokens = {str(market["yes_token"]): "YES", str(market["no_token"]): "NO"}
    condition = str(market.get("condition_id", "")).lower()
    rows, rejected = [], {}

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for record in records:
        try:
            token = tokens.get(str(record.get("token_id") or record.get("asset")))
            wallet = str(record.get("proxy_wallet") or record.get("proxyWallet") or "").lower()
            side = str(record.get("side", "")).upper()
            price = float(record["price"])
            shares = float(record["size"])
            ts = int(record["timestamp"])
            record_condition = str(record.get("condition_id") or record.get("conditionId") or condition).lower()
        except (KeyError, TypeError, ValueError):
            reject("unparseable")
            continue
        if token is None:
            reject("unknown_token")
        elif record_condition != condition:
            reject("other_condition")
        elif not wallet.startswith("0x"):
            reject("no_wallet")
        elif side not in ("BUY", "SELL"):
            reject("bad_side")
        elif not 0 < price < 1 or shares <= 0:
            reject("bad_price_or_size")
        else:
            tx = record.get("transaction_hash") or record.get("transactionHash") or ""
            rows.append((market["market_id"], ts, wallet, token, side, price, shares, tx_key(tx)))
    frame = pd.DataFrame(rows, columns=TRADE_COLUMNS)
    # Identical records are kept: one wallet can fill several identical orders in one transaction.
    return frame, rejected
