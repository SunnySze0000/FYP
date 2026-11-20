"""Load raw files into tidy, typed DataFrames.

Loaders only parse and type data. They never fill, rescale or drop rows for
analytical reasons; that is the job of `validation` and `features`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from eventlens.config import Paths, get_paths
from eventlens.data.taxonomy import normalise_label, representative_move

WALLET_TRADE_COLUMNS = [
    "timestamp_utc", "market_id", "meeting_month", "rate_outcome",
    "token_outcome", "wallet_address", "side", "shares", "price",
    "notional_usd", "signed_yes_shares", "transaction_hash",
]


def load_probabilities(paths: Paths | None = None) -> pd.DataFrame:
    """Daily Polymarket probabilities, one row per (date, market).

    `date` is the UTC snapshot timestamp as a naive datetime.
    """
    paths = paths or get_paths()
    frame = pd.read_csv(paths.probabilities_csv)
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None)
    frame["outcome"] = frame["outcome"].map(normalise_label)
    frame["move_bp"] = frame["outcome"].map(representative_move)
    frame["market_probability"] = pd.to_numeric(frame["market_probability"])
    return frame.sort_values(["date", "meeting_month", "outcome"]).reset_index(drop=True)


def load_prices(paths: Paths | None = None, tickers: list[str] | None = None) -> pd.DataFrame:
    """Daily closes with log returns, one row per (ticker, trading date).

    Reads the team file plus any Yahoo collector output under raw/yahoo.
    """
    paths = paths or get_paths()
    team = _read_team_prices(paths.prices_csv)
    yahoo_files = sorted(paths.yahoo.glob("*.csv")) if paths.yahoo.exists() else []
    yahoo = [_read_yahoo_prices(path) for path in yahoo_files]
    # A ticker comes from exactly one source, so adjusted and unadjusted
    # closes are never spliced into one return series.
    yahoo_tickers = {frame["ticker"].iloc[0] for frame in yahoo if not frame.empty}
    frames = [team.loc[~team["ticker"].isin(yahoo_tickers)], *yahoo]
    prices = pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"])
    if tickers:
        prices = prices.loc[prices["ticker"].isin(tickers)]
    prices["log_return"] = prices.groupby("ticker")["close"].transform(
        lambda close: np.log(close).diff()
    )
    return prices.reset_index(drop=True)


def _read_team_prices(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["date", "ticker", "close"])
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None).dt.normalize()
    return frame


def _read_yahoo_prices(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["date", "ticker", "adj_close"])
    frame = frame.rename(columns={"adj_close": "close"})
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def load_wallet_trades(paths: Paths | None = None) -> pd.DataFrame:
    """All participant trade records for the June 2026 Fed event (5 markets).

    Adds YES-equivalent fields so YES and NO token trades are comparable:
    `yes_price` (price of the YES side implied by the trade) and `direction`
    (+1 if the trade increases YES exposure, -1 otherwise).
    """
    paths = paths or get_paths()
    files = sorted(paths.fed_wallets.glob("market_*/wallet_trades.csv.gz"))
    if not files:
        raise FileNotFoundError(f"No wallet trade files under {paths.fed_wallets}")
    frame = pd.concat(
        (pd.read_csv(path, usecols=WALLET_TRADE_COLUMNS, dtype={"market_id": str}) for path in files),
        ignore_index=True,
    )
    return _add_yes_equivalents(frame)


def load_prior_wallet_trades(paths: Paths | None = None) -> pd.DataFrame:
    """Earlier-meeting trades of the 20 candidate wallets (7 meetings)."""
    paths = paths or get_paths()
    path = paths.fed_wallets / "event_101772" / "prior_history" / "prior_wallet_trades.csv.gz"
    frame = pd.read_csv(
        path,
        usecols=WALLET_TRADE_COLUMNS + ["decision_cutoff_utc", "before_decision_cutoff"],
        dtype={"market_id": str},
    )
    frame["decision_cutoff_utc"] = pd.to_datetime(frame["decision_cutoff_utc"], utc=True)
    return _add_yes_equivalents(frame)


def _add_yes_equivalents(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame["rate_outcome"] = frame["rate_outcome"].map(normalise_label)
    is_yes = frame["token_outcome"].str.upper().eq("YES")
    frame["yes_price"] = np.where(is_yes, frame["price"], 1.0 - frame["price"])
    frame["direction"] = np.sign(frame["signed_yes_shares"]).astype(int)
    return frame.sort_values("timestamp_utc").reset_index(drop=True)
