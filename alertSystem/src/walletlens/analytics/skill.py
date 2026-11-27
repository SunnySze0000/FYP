"""Wallet skill: how much better than the (fair) price were a wallet's trades?

Definitions
-----------
For one wallet in one resolved market, with trades in YES terms:

``edge = sum(yes_dir * shares * (outcome - fair(yes_price))) / sum(shares)``

i.e. the average probability points a wallet "beat" fair value by, per share traded.
A wallet's skill at time t averages its per-market edges over markets that **closed
before t** (each market counts once), shrunk towards zero:

``shrunk = mean_edge * n / (n + k)``

so a wallet with one lucky market cannot top the ranking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.calibration import FairValue


def wallet_market_edges(trades: pd.DataFrame, markets: pd.DataFrame, fair: FairValue,
                        min_notional: float = 10.0) -> pd.DataFrame:
    """One row per (wallet, market): size, profit to resolution, and edge vs fair and vs price."""
    info = markets.set_index("market_id")[["outcome_yes", "close_ts", "group_id"]]
    market_ids = trades["market_id"].astype(str)
    y = market_ids.map(info["outcome_yes"]).to_numpy(float)
    yes_price = trades["yes_price"].to_numpy()
    direction = trades["yes_dir"].to_numpy(float)
    shares = trades["shares"].to_numpy()
    frame = pd.DataFrame({
        "wallet": trades["wallet"].astype(str).to_numpy(),
        "market_id": market_ids.to_numpy(),
        "shares": shares,
        "notional": trades["notional"].to_numpy(),
        "pnl": direction * shares * (y - yes_price),
        "edge_num": direction * shares * (y - fair(yes_price)),
        "raw_num": direction * shares * (y - yes_price),
        "buy_longshot": shares * ((direction > 0) & (yes_price < 0.2) | (direction < 0) & (yes_price > 0.8)),
        "first_ts": trades["ts"].to_numpy(),
    })
    grouped = frame.groupby(["wallet", "market_id"], sort=False).agg(
        shares=("shares", "sum"), notional=("notional", "sum"), pnl=("pnl", "sum"),
        edge_num=("edge_num", "sum"), raw_num=("raw_num", "sum"), longshot=("buy_longshot", "sum"),
        trades=("shares", "size"), first_ts=("first_ts", "min")).reset_index()
    grouped["edge"] = grouped["edge_num"] / grouped["shares"]
    grouped["raw_edge"] = grouped["raw_num"] / grouped["shares"]
    grouped["longshot_share"] = grouped["longshot"] / grouped["shares"]
    grouped = grouped.drop(columns=["edge_num", "raw_num", "longshot"])
    grouped = grouped[grouped["notional"] >= min_notional]
    grouped = grouped.join(info, on="market_id")
    return grouped.reset_index(drop=True)


def shrink(mean, n, k: float):
    n = np.asarray(n, float)
    weight = np.divide(n, n + k, out=np.zeros_like(n), where=(n + k) > 0)
    return np.asarray(mean, float) * weight


def skill_table(wallet_markets: pd.DataFrame, k: float, column: str = "edge") -> pd.DataFrame:
    """Skill of every wallet using all rows given (callers filter by time first)."""
    table = wallet_markets.groupby("wallet").agg(
        markets=(column, "size"), mean_edge=(column, "mean"), edge_sd=(column, "std"),
        pnl=("pnl", "sum"), notional=("notional", "sum"), wins=(column, lambda e: int((e > 0).sum())),
        longshot_share=("longshot_share", "mean"), last_close=("close_ts", "max"))
    table["shrunk"] = shrink(table["mean_edge"], table["markets"], k)
    table["roi"] = table["pnl"] / table["notional"].where(table["notional"] > 0)
    return table.sort_values("shrunk", ascending=False)


class SkillTimeline:
    """Point-in-time wallet skill, so a trade is only ever judged with *earlier* information.

    ``lookup(wallets, ts)`` returns each wallet's number of resolved markets and shrunk
    skill using markets that closed strictly before ``ts``, plus the top-tier threshold
    in force at that moment.
    """

    def __init__(self, wallet_markets: pd.DataFrame, k: float, min_markets: int, top_fraction: float,
                 column: str = "edge"):
        self.k, self.min_markets, self.top_fraction = k, min_markets, top_fraction
        rows = wallet_markets[["wallet", "close_ts", column]].sort_values("close_ts", kind="stable")
        per_close = rows.groupby(["wallet", "close_ts"], sort=False)[column].agg(["sum", "size"]).reset_index()
        per_close = per_close.sort_values("close_ts", kind="stable")
        per_close["cum_sum"] = per_close.groupby("wallet")["sum"].cumsum()
        per_close["cum_n"] = per_close.groupby("wallet")["size"].cumsum()
        self.history = per_close[["wallet", "close_ts", "cum_sum", "cum_n"]].reset_index(drop=True)
        self.boundaries, self.thresholds, self.ranked = self._thresholds(per_close)

    def _thresholds(self, per_close: pd.DataFrame):
        state: dict[str, tuple[float, int]] = {}
        boundaries, thresholds, ranked = [], [], []
        for close_ts, part in per_close.groupby("close_ts", sort=True):
            for wallet, cum_sum, cum_n in zip(part["wallet"], part["cum_sum"], part["cum_n"]):
                state[wallet] = (cum_sum, cum_n)
            values = np.array([s / n * n / (n + self.k) for s, n in state.values() if n >= self.min_markets])
            boundaries.append(close_ts)
            ranked.append(len(values))
            thresholds.append(float(np.quantile(values, 1 - self.top_fraction)) if len(values) else np.inf)
        return np.array(boundaries), np.array(thresholds), np.array(ranked)

    def lookup(self, wallets: pd.Series, ts: pd.Series) -> pd.DataFrame:
        """Skill as of each (wallet, ts) using markets closed strictly before ts."""
        query = pd.DataFrame({"wallet": np.asarray(wallets, str), "ts": np.asarray(ts, "int64"),
                              "_row": np.arange(len(wallets))}).sort_values("ts")
        hist = self.history.rename(columns={"close_ts": "ts"}).dropna(subset=["ts"])
        hist = hist.assign(ts=hist["ts"].astype("int64")).sort_values("ts")
        merged = pd.merge_asof(query, hist, on="ts", by="wallet", direction="backward",
                               allow_exact_matches=False).sort_values("_row")
        n = merged["cum_n"].fillna(0).to_numpy()
        mean = np.divide(merged["cum_sum"].fillna(0).to_numpy(), n, out=np.zeros_like(n, float), where=n > 0)
        shrunk = shrink(mean, n, self.k)
        position = np.searchsorted(self.boundaries, merged["ts"].to_numpy(), side="left") - 1
        threshold = np.where(position >= 0, self.thresholds[np.clip(position, 0, None)], np.inf)
        ranked = n >= self.min_markets
        top = ranked & (shrunk >= threshold) & (shrunk > 0)
        return pd.DataFrame({"prior_markets": n, "prior_skill": shrunk, "ranked": ranked, "top": top},
                            index=wallets.index if isinstance(wallets, pd.Series) else None)

    def latest(self) -> pd.DataFrame:
        last = self.history.groupby("wallet").tail(1).set_index("wallet")
        n = last["cum_n"].to_numpy()
        out = pd.DataFrame({"markets": n, "mean_edge": last["cum_sum"].to_numpy() / n}, index=last.index)
        out["shrunk"] = shrink(out["mean_edge"], out["markets"], self.k)
        return out.sort_values("shrunk", ascending=False)
