"""Wallet features for the event-risk monitor (wallet directions W1-W5, docs/04_wallet_directions.md).

Every trade in the event markets is tagged with the type of wallet that made it, using only
information available at the time of the trade:

* ``whale``     the trade itself is worth at least ``whale_trade_usd``
* ``skilled``   the wallet is in the top 10% of shrunk edge over event markets that closed earlier
* ``new``       the wallet's first trade in these markets was less than ``new_wallet_days`` ago
* ``frequent``  the wallet had already made at least ``frequent_wallet_trades`` trades here
* ``retail``    none of the four above
* ``linked``    the wallet belongs to a same-owner (sniper) group found by the team's pipeline
* ``filtered_out`` the wallet's entity fails the team's hard rules (bots, dust, one-off wallets)

Behaviour clusters from the team's pipeline (frozen KMeans fitted on the earlier half) are added as
``cluster_id`` and treated as further types by W5.

``FlowBook`` then answers "how much net YES money did each type put in between t0 and t1" for any
market and window, which every W-experiment uses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens import logs
from walletlens.analytics.calibration import FairValue
from walletlens.analytics.skill import SkillTimeline, wallet_market_edges
from walletlens.config import EventsConfig
from walletlens.data.schema import add_yes_terms

log = logs.get("events.wallets")
TYPES = ("whale", "skilled", "new", "frequent", "retail", "linked", "filtered_out")


def tag_trades(trades: pd.DataFrame, markets: pd.DataFrame, cfg: EventsConfig,
               pipeline: pd.DataFrame | None = None) -> pd.DataFrame:
    trades = add_yes_terms(trades).sort_values("ts", kind="stable").reset_index(drop=True)
    trades["market_id"] = trades["market_id"].astype(str)
    trades["wallet"] = trades["wallet"].astype(str)
    trades["signed"] = trades["yes_dir"] * trades["notional"]
    first_seen = trades.groupby("wallet")["ts"].transform("min")
    trades["new"] = (trades["ts"] - first_seen) < cfg.new_wallet_days * 86_400
    trades["frequent"] = trades.groupby("wallet").cumcount() >= cfg.frequent_wallet_trades
    trades["whale"] = trades["notional"] >= cfg.whale_trade_usd
    resolved = markets[["market_id", "outcome_yes", "close_ts", "group_id"]].copy()
    wm = wallet_market_edges(trades, resolved, FairValue(), min_notional=10)
    timeline = SkillTimeline(wm, k=5, min_markets=3, top_fraction=0.10)
    trades["skilled"] = timeline.lookup(trades["wallet"], trades["ts"])["top"].to_numpy()
    trades["retail"] = ~(trades["whale"] | trades["skilled"] | trades["new"] | trades["frequent"])
    if pipeline is not None and len(pipeline):
        info = pipeline.set_index("wallet")
        trades["linked"] = trades["wallet"].map(info["entity_size"]).fillna(1).to_numpy() > 1
        trades["filtered_out"] = ~trades["wallet"].map(info["eligible"]).fillna(False).astype(bool).to_numpy()
        trades["cluster_id"] = trades["wallet"].map(info["cluster_id"]).fillna("unclustered").to_numpy()
    else:
        trades["linked"] = False
        trades["filtered_out"] = False
        trades["cluster_id"] = "unclustered"
    shares = {t: float(trades[t].mean()) for t in TYPES}
    log.info("tagged %d trades; share by type %s", len(trades), {k: round(v, 3) for k, v in shares.items()})
    return trades


class FlowBook:
    """Cumulative sums per market so any (t0, t1] window is two look-ups."""

    def __init__(self, tagged: pd.DataFrame):
        self.books = {}
        self.clusters = sorted(c for c in tagged["cluster_id"].unique() if c != "unclustered")
        for market, part in tagged.groupby("market_id", sort=False):
            part = part.sort_values("ts")
            columns = {"all": part["signed"].to_numpy(), "gross": part["notional"].to_numpy()}
            for cluster in part["cluster_id"].unique():
                if cluster != "unclustered":
                    flag = (part["cluster_id"] == cluster).to_numpy()
                    columns[cluster] = np.where(flag, part["signed"].to_numpy(), 0.0)
            for kind in TYPES:
                flag = part[kind].to_numpy()
                columns[kind] = np.where(flag, part["signed"].to_numpy(), 0.0)
                columns[kind + "_gross"] = np.where(flag, part["notional"].to_numpy(), 0.0)
            cumulative = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in columns.items()}
            wallet_codes = pd.factorize(part["wallet"])[0]
            self.books[market] = (part["ts"].to_numpy("int64"), cumulative, wallet_codes)

    def window(self, market: str, t0, t1) -> pd.DataFrame:
        """Net and gross dollars per type, and distinct wallets, for windows (t0, t1]."""
        t0, t1 = np.asarray(t0, "int64"), np.asarray(t1, "int64")
        if market not in self.books:
            return pd.DataFrame(index=range(len(t0)))
        times, cumulative, wallets = self.books[market]
        lo = np.searchsorted(times, t0, side="right")
        hi = np.searchsorted(times, t1, side="right")
        out = {k: v[hi] - v[lo] for k, v in cumulative.items()}
        for cluster in self.clusters:
            out.setdefault(cluster, np.zeros(len(t0)))
        out["wallets"] = np.array([len(np.unique(wallets[a:b])) for a, b in zip(lo, hi)])
        out["trades"] = hi - lo
        return pd.DataFrame(out)


def price_at(times: np.ndarray, values: np.ndarray, at) -> np.ndarray:
    position = np.searchsorted(times, np.asarray(at, "int64"), side="right") - 1
    out = np.full(len(position), np.nan)
    ok = position >= 0
    out[ok] = values[position[ok]]
    return out


def market_hours(prices: pd.DataFrame, flows: FlowBook, shock_points: float, gap_s: int = 0) -> pd.DataFrame:
    """Hourly panel per market: probability change, wallet flows of the hour, what happened next.

    ``gap_s`` > 0 ends the flow window that many seconds before the hour (robustness check: flows that
    could only show up in the *next* price snapshot are left out).
    """
    rows = []
    for market, part in prices.sort_values("ts").groupby("market_id"):
        if market not in flows.books:
            continue
        times, values = part["ts"].to_numpy("int64"), part["yes_price"].to_numpy(float)
        grid = np.arange(times[0] // 3600 * 3600 + 3600, times[-1] - 24 * 3600, 3600, dtype="int64")
        if len(grid) < 48:
            continue
        p = price_at(times, values, grid)
        prev = price_at(times, values, grid - 3600)
        nxt = price_at(times, values, grid + 3600)
        p6 = price_at(times, values, grid + 6 * 3600)
        p24 = price_at(times, values, grid + 24 * 3600)
        window = flows.window(market, grid - 3600, grid - gap_s)
        frame = pd.DataFrame({"market_id": market, "ts": grid, "p": p, "dp": p - prev, "dp_next": nxt - p,
                              "cont_6h": p6 - p, "cont_24h": p24 - p})
        rows.append(pd.concat([frame, window.add_prefix("f_")], axis=1))
    panel = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if len(panel):
        panel["shock"] = panel["dp"].abs() >= shock_points
        panel["shock_next"] = panel["dp_next"].abs() >= shock_points
        panel["dir"] = np.sign(panel["dp"])
    return panel
