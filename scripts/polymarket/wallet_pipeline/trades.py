"""Load and normalize participant trades; infer taker role where identifiable."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["timestamp_utc", "event_id", "market_id", "rate_outcome", "token_outcome", "wallet_address",
           "side", "shares", "price", "notional_usd", "transaction_hash", "same_fingerprint_count"]


def load_market_exports(root: Path, market_ids, cutoff=None) -> pd.DataFrame:
    """Concatenate ``datasets/polymarket/market_<id>/wallet_trades.csv.gz``.

    Only trades strictly before ``cutoff`` (UTC) are kept when it is given.
    """
    frames = [pd.read_csv(root / "datasets" / "polymarket" / f"market_{mid}" / "wallet_trades.csv.gz",
                          dtype=str, usecols=COLUMNS) for mid in market_ids]
    return normalize(pd.concat(frames, ignore_index=True), cutoff)


def normalize(trades: pd.DataFrame, cutoff=None) -> pd.DataFrame:
    data = trades.copy()
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    if cutoff is not None:
        data = data.loc[data["timestamp_utc"].lt(pd.Timestamp(cutoff))]
    data["wallet_address"] = data["wallet_address"].str.lower()
    for column in ("shares", "price", "notional_usd"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    side, token = data["side"].str.upper(), data["token_outcome"].str.upper()
    if not (side.isin(["BUY", "SELL"]) & token.isin(["YES", "NO"])).all():
        raise ValueError("Unsupported side/token_outcome")
    data["direction"] = np.where((side == "BUY") == (token == "YES"), 1, -1)  # YES-equivalent
    data["yes_price"] = np.where(token == "YES", data["price"], 1.0 - data["price"])
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    data["second"] = (data["timestamp_utc"] - epoch) // pd.Timedelta(seconds=1)  # resolution-safe
    data["taker_role"] = infer_taker(data)
    return data.reset_index(drop=True)


def infer_taker(data: pd.DataFrame, tolerance: float = 1e-6) -> pd.Series:
    """1 = taker, 0 = maker, NaN = unknown.

    In a fill transaction the taker's shares equal the makers' total. With 3+
    wallets that identifies the taker uniquely; with 2 wallets both sides are
    equal and the role is unknown.
    """
    per = data.groupby(["transaction_hash", "wallet_address"])["shares"].sum()
    frame = per.rename("w_shares").reset_index()
    tx = frame.groupby("transaction_hash")["w_shares"].agg(total="sum", n="size")
    frame = frame.join(tx, on="transaction_hash")
    rest = frame["total"] - frame["w_shares"]
    is_taker = (frame["w_shares"] - rest).abs() <= tolerance * frame["total"].clip(lower=1)
    role = np.where(frame["n"] >= 3, is_taker.astype(float), np.nan)
    role = pd.Series(role, index=pd.MultiIndex.from_frame(frame[["transaction_hash", "wallet_address"]]))
    keys = pd.MultiIndex.from_frame(data[["transaction_hash", "wallet_address"]])
    return pd.Series(role.reindex(keys).to_numpy(), index=data.index)
