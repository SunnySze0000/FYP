"""Canonical tables shared by the collector, the research and the app.

``markets``  one row per binary market
``trades``   one row per *participant record* (a fill appears once for each wallet in it)
``prices``   YES-token price series

Conventions
-----------
* Times are integer Unix seconds (UTC).
* Every trade is expressed in **YES terms**: ``yes_price`` is the implied YES probability
  and ``yes_dir`` is +1 when the wallet gains if YES wins (BUY YES or SELL NO), else -1.
  A trade's profit if held to resolution is ``yes_dir * shares * (outcome - yes_price)``.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

MARKET_COLUMNS = [
    "market_id", "condition_id", "question", "category", "group_id", "yes_token", "no_token",
    "start_ts", "end_ts", "close_ts", "outcome_yes", "volume_usd", "resolution_source",
]
TRADE_COLUMNS = ["market_id", "ts", "wallet", "token", "side", "price", "shares", "tx"]
PRICE_COLUMNS = ["market_id", "ts", "yes_price"]

CATEGORY_KEYWORDS = {
    "economics": ("fed ", "fed?", "interest rate", "cpi", "inflation", "gdp", "recession", "jobs report",
                  "unemployment", "fomc", "rate cut", "tariff"),
    "crypto": ("bitcoin", "btc", "ethereum", "eth ", "solana", "crypto", "xrp", "doge", "token"),
    "politics": ("election", "president", "senate", "house", "governor", "trump", "biden", "vote",
                 "prime minister", "parliament", "mayor", "democrat", "republican", "nominee", "cabinet"),
    "geopolitics": ("war", "ceasefire", "russia", "ukraine", "israel", "iran", "china", "nato", "strike"),
    "sports": (" vs ", " vs.", "nba", "nfl", "mlb", "nhl", "premier league", "champions league",
               "world cup", "super bowl", "win the", "ufc", "f1 ", "grand prix", "open "),
    "tech_business": ("openai", "apple", "google", "nvidia", "tesla", "ceo", "ipo", "earnings",
                      "ai ", "gpt", "spacex", "microsoft", "meta "),
    "culture": ("oscar", "grammy", "album", "movie", "box office", "spotify", "time person", "eurovision"),
}


def categorise(question: str) -> str:
    text = f" {question.lower()} "
    for category, words in CATEGORY_KEYWORDS.items():
        if any(word in text for word in words):
            return category
    return "other"


def tx_key(transaction_hash: str) -> int:
    """64-bit key for a transaction hash: saves memory, collisions are negligible."""
    text = (transaction_hash or "").lower()
    if text.startswith("0x") and len(text) >= 17:
        return int(text[2:17], 16)
    return int(hashlib.sha1(text.encode()).hexdigest()[:15], 16)


def compact_trades(frame: pd.DataFrame) -> pd.DataFrame:
    """Memory-friendly dtypes for the trades table."""
    out = frame[TRADE_COLUMNS].copy()
    out["market_id"] = out["market_id"].astype(str).astype("category")
    out["wallet"] = out["wallet"].str.lower().astype("category")
    out["token"] = out["token"].str.upper().astype("category")
    out["side"] = out["side"].str.upper().astype("category")
    out["ts"] = out["ts"].astype("int64")
    out["price"] = out["price"].astype("float64")
    out["shares"] = out["shares"].astype("float64")
    out["tx"] = out["tx"].astype("int64")
    return out.sort_values(["market_id", "ts"], kind="stable").reset_index(drop=True)


def add_yes_terms(trades: pd.DataFrame) -> pd.DataFrame:
    """Add ``yes_price``, ``yes_dir`` and ``notional`` (USD paid or received)."""
    is_yes = (trades["token"] == "YES").to_numpy()
    is_buy = (trades["side"] == "BUY").to_numpy()
    price = trades["price"].to_numpy()
    trades = trades.copy()
    trades["yes_price"] = np.where(is_yes, price, 1.0 - price)
    trades["yes_dir"] = np.where(is_yes == is_buy, 1, -1).astype("int8")
    trades["notional"] = trades["shares"].to_numpy() * price
    return trades


def validate_markets(markets: pd.DataFrame) -> list[str]:
    problems = []
    missing = [c for c in MARKET_COLUMNS if c not in markets]
    if missing:
        problems.append(f"missing columns {missing}")
        return problems
    if markets["market_id"].duplicated().any():
        problems.append("duplicate market_id")
    bad = ~markets["outcome_yes"].isin([0, 1])
    if bad.any():
        problems.append(f"{int(bad.sum())} markets without a 0/1 outcome")
    return problems


def validate_trades(trades: pd.DataFrame) -> list[str]:
    problems = []
    if ((trades["price"] <= 0) | (trades["price"] >= 1)).any():
        problems.append("prices outside (0, 1)")
    if (trades["shares"] <= 0).any():
        problems.append("non-positive share sizes")
    if not set(trades["token"].astype(str).unique()) <= {"YES", "NO"}:
        problems.append("unknown token labels")
    if not set(trades["side"].astype(str).unique()) <= {"BUY", "SELL"}:
        problems.append("unknown sides")
    return problems
