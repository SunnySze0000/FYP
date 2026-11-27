"""Price look-ups, trade markouts (H2) and the copy-trading backtest (H3)."""

from __future__ import annotations

import numpy as np
import pandas as pd


class PriceBook:
    """Last known YES price of each market at any moment.

    Built from every observation available: the downloaded price series *and* the YES-terms
    price of every trade, so the look-up is as fresh as the data allows.
    """

    def __init__(self, prices: pd.DataFrame, trades: pd.DataFrame | None = None):
        parts = [prices[["market_id", "ts", "yes_price"]].astype({"market_id": str})]
        if trades is not None:
            parts.append(pd.DataFrame({"market_id": trades["market_id"].astype(str).to_numpy(),
                                       "ts": trades["ts"].to_numpy(), "yes_price": trades["yes_price"].to_numpy()}))
        series = pd.concat(parts, ignore_index=True).sort_values(["market_id", "ts"], kind="stable")
        self._series = {m: (g["ts"].to_numpy(), g["yes_price"].to_numpy())
                        for m, g in series.groupby("market_id", sort=False)}

    def at(self, market_ids, ts) -> np.ndarray:
        """Price at or before each ``ts`` (NaN before the first observation)."""
        market_ids = np.asarray(market_ids, str)
        ts = np.asarray(ts, "int64")
        out = np.full(len(ts), np.nan)
        for market, rows in pd.Series(market_ids).groupby(market_ids).indices.items():
            if market not in self._series:
                continue
            times, values = self._series[market]
            position = np.searchsorted(times, ts[rows], side="right") - 1
            found = position >= 0
            out[rows[found]] = values[position[found]]
        return out


def add_markouts(trades: pd.DataFrame, markets: pd.DataFrame, book: PriceBook, horizons_s) -> pd.DataFrame:
    """``markout_<h>`` = yes_dir * (YES price h seconds later - trade price), in probability points.

    If the market closes before ``ts + h`` the resolution (0 or 1) is used. ``markout_res`` is
    the markout to resolution, i.e. the trade's edge per share.
    """
    info = markets.set_index("market_id")
    market_ids = trades["market_id"].astype(str)
    close = market_ids.map(info["close_ts"]).to_numpy("int64")
    outcome = market_ids.map(info["outcome_yes"]).to_numpy(float)
    direction = trades["yes_dir"].to_numpy(float)
    price = trades["yes_price"].to_numpy()
    out = trades.copy()
    for horizon in horizons_s:
        target = trades["ts"].to_numpy("int64") + int(horizon)
        future = book.at(market_ids.to_numpy(), np.minimum(target, close))
        future = np.where(target >= close, outcome, future)
        out[f"markout_{horizon}"] = direction * (future - price)
    out["markout_res"] = direction * (outcome - price)
    return out


def copy_backtest(signals: pd.DataFrame, markets: pd.DataFrame, book: PriceBook, delay_s: int, cost: float,
                  band: tuple[float, float]) -> pd.DataFrame:
    """Follow each signal ``delay_s`` later at the then price plus ``cost``; hold to resolution.

    Returns one row per executed copy with the entry price paid and the return per $1.
    """
    info = markets.set_index("market_id")
    market_ids = signals["market_id"].astype(str).to_numpy()
    entry_ts = signals["ts"].to_numpy("int64") + int(delay_s)
    close = pd.Series(market_ids).map(info["close_ts"]).to_numpy("int64")
    outcome = pd.Series(market_ids).map(info["outcome_yes"]).to_numpy(float)
    yes_now = book.at(market_ids, entry_ts)
    direction = signals["yes_dir"].to_numpy()
    paid = np.where(direction > 0, yes_now, 1 - yes_now) + cost      # price of the token bought
    won = np.where(direction > 0, outcome, 1 - outcome)
    ok = (entry_ts < close) & np.isfinite(yes_now) & (yes_now >= band[0]) & (yes_now <= band[1]) & (paid < 1)
    result = pd.DataFrame({
        "market_id": market_ids, "signal_ts": signals["ts"].to_numpy(), "entry_ts": entry_ts,
        "yes_dir": direction, "entry_price": paid, "won": won,
        "edge_per_share": won - paid, "return_per_dollar": won / paid - 1,
    })[ok]
    return result.reset_index(drop=True)


def first_per_hour(frame: pd.DataFrame) -> pd.DataFrame:
    """One signal per wallet, market and hour: repeated fills of one decision count once."""
    keyed = frame.assign(_hour=frame["ts"] // 3600)
    return keyed.drop_duplicates(["wallet", "market_id", "_hour"]).drop(columns="_hour")
