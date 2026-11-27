"""D2 / D3 · Per-holding wallet checks, run every time a holding is added.

For one holding, on its own history (research trades in its linked markets, hours after the cluster fit date):
  C0 surge   market makers' $ flow far above its trailing 48 h level       (W7, pooled +9.0%)
  C2 surge   burst traders' $ flow far above its trailing 48 h level       (W7, pooled +6.3%)
  cross      many wallets trading 2+ linked markets in the same hour       (W9b, pooled +20.7%)
-> is the holding's next-hour |return| larger than usual after the signal? A signal is shown for the holding
only if it has >= 20 past signal hours and a positive effect; the number shown is shrunk toward the pooled
research effect so a few lucky hours cannot produce a big claim.
The same signal functions run on live trades in the app (live_flags), so research and app agree.
"""

from __future__ import annotations

import threading

import numpy as np
import pandas as pd

from walletlens import io, logs
from walletlens.data.schema import add_yes_terms
from walletlens.monitor.holdings import active_groups, mentions
from walletlens.topics.events.collect import DTYPES, groups_for

log = logs.get("monitor.holding_wallets")
GAP = 900
SIGNALS = {"C0": {"name": "Market makers surging", "pooled": 0.090},
           "C2": {"name": "Burst traders surging", "pooled": 0.063},
           "cross": {"name": "Wallets moving several linked bets at once", "pooled": 0.207}}
MIN_HOURS, SHRINK_K = 20, 50


def window_signals(trades: pd.DataFrame, window_ends: np.ndarray) -> dict[str, np.ndarray]:
    """Signal flags for one-hour windows ending at each of ``window_ends`` (sorted, hourly spaced with gaps
    allowed). Trailing levels use the previous 48 hourly windows on the same hourly grid."""
    if not len(window_ends):
        return {k: np.zeros(0, bool) for k in SIGNALS}
    offset = int(window_ends[0] % 3600)
    w0 = (int(window_ends[0]) - offset) // 3600 - 60
    n = (int(window_ends[-1]) - offset) // 3600 - w0 + 1
    t = trades
    w = ((t["ts"].to_numpy("int64") - offset - 1) // 3600 + 1) - w0          # window ending at offset+(w0+w)*3600
    keep = (w >= 0) & (w < n)
    t, w = t[keep], w[keep]
    usd = t["notional"].to_numpy(float)
    out = {}
    for cluster in ("C0", "C2"):
        flow = np.bincount(w, weights=usd * (t["cluster_id"].to_numpy() == cluster), minlength=n)
        lf = np.log1p(flow)
        trail = pd.Series(lf).shift(1).rolling(48, min_periods=12).mean().to_numpy()
        out[cluster] = (lf - trail >= 2.0) & (flow >= 1_000)
    frame = pd.DataFrame({"w": w, "wallet": t["wallet"].to_numpy(), "market": t["market_id"].to_numpy()})
    per = frame.drop_duplicates().groupby(["w", "wallet"]).size()
    multi = per[per >= 2].reset_index()
    cross = np.bincount(multi["w"], minlength=n).astype(float) if len(multi) else np.zeros(n)
    lc = np.log1p(cross)
    trail = pd.Series(lc).shift(1).rolling(48, min_periods=12).mean().to_numpy()
    out["cross"] = (lc - trail >= 1.0) & (cross >= 3)
    idx = (window_ends.astype(np.int64) - offset) // 3600 - w0
    return {k: v[idx] for k, v in out.items()}


class ResearchStore:
    """Research trades and markets, loaded once (lazily) for per-holding checks."""

    def __init__(self, root):
        self.root, self._lock, self._loaded = root, threading.Lock(), False

    def load(self):
        with self._lock:
            if self._loaded:
                return self
            folder = self.root / "data" / "processed" / "events"
            self.markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)
            self.markets["glist"] = self.markets["question"].map(groups_for)
            trades = add_yes_terms(io.read_table(folder / "trades.pkl.gz"))
            lookup = pd.read_csv(self.root / "data" / "app" / "wallet_clusters.csv")
            clusters = dict(zip(lookup["wallet"].str.lower(), lookup["cluster_id"]))
            trades = trades[trades["notional"] >= 250]
            self.trades = pd.DataFrame({"market_id": trades["market_id"].astype(str).to_numpy(),
                                        "ts": trades["ts"].to_numpy("int64"), "wallet": trades["wallet"].str.lower().to_numpy(),
                                        "notional": trades["notional"].to_numpy(float)})
            self.trades["cluster_id"] = self.trades["wallet"].map(clusters).fillna("none")
            self.split_ts = int(self.markets["close_ts"].median())
            self._loaded = True
            log.info("research store: %d markets, %d trades", len(self.markets), len(self.trades))
            return self

    def linked_markets(self, profile: dict) -> set[str]:
        groups = {g for g, ok in active_groups(profile).items() if ok}
        terms = profile.get("terms") or []
        ids = set()
        for m in self.markets.itertuples(index=False):
            if groups.intersection(m.glist) or (terms and mentions(m.question, terms)):
                ids.add(m.market_id)
        return ids


def check(profile: dict, bars: list[tuple[int, float]], store: ResearchStore) -> dict:
    store.load()
    linked = store.linked_markets(profile)
    out = {"linked_research_markets": len(linked), "signals": {}}
    if len(linked) < 3 or len(bars) < 200:
        out["note"] = "not enough history"
        return out
    ends = np.array([b[0] for b in bars], dtype=np.int64)
    closes = np.array([b[1] for b in bars], dtype=float)
    same = np.r_[False, np.diff(ends) == 3600]
    r = np.abs(np.r_[np.nan, np.diff(np.log(closes))])
    ok = same & np.isfinite(r) & (ends - 3600 >= store.split_ts)
    ends, r = ends[ok], r[ok]
    if len(ends) < 100:
        out["note"] = "not enough history after the cluster fit date"
        return out
    hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    starts = ends - 3600
    flags = window_signals(store.trades[store.trades["market_id"].isin(linked)], starts - GAP)
    for key, spec in SIGNALS.items():
        f = flags[key]
        n = int(f.sum())
        eff = float(np.nanmean(y[f]) - np.nanmean(y[~f])) if n else None
        shown = (n * eff + SHRINK_K * spec["pooled"]) / (n + SHRINK_K) if eff is not None else None
        out["signals"][key] = {"name": spec["name"], "hours": n, "effect": eff, "shown_effect": shown,
                               "pass": bool(n >= MIN_HOURS and eff is not None and eff > 0)}
    return out


def live_flags(trades: list[dict], clusters: dict, now: float, hours: int = 24) -> dict[str, list[int]]:
    """For live trades in a holding's linked markets: which of the last ``hours`` whole-hour windows (and the
    current hour) fired each signal. Returns signal -> list of window-end timestamps that fired."""
    if not trades:
        return {k: [] for k in SIGNALS}
    frame = pd.DataFrame(trades)
    frame["wallet"] = frame["wallet"].str.lower()
    frame["cluster_id"] = frame["wallet"].map(clusters).fillna("none")
    top = int(now // 3600 * 3600)
    ends = np.array([top - k * 3600 for k in range(hours, 0, -1)] + [top], dtype=np.int64)
    flags = window_signals(frame.rename(columns={"usd": "notional", "market": "market_id"}), ends)
    current = window_signals(frame.rename(columns={"usd": "notional", "market": "market_id"}),
                             np.array([int(now) - k * 3600 for k in range(48, -1, -1)], dtype=np.int64))
    out = {k: [int(e) for e, f in zip(ends[:-1], v[:-1]) if f] for k, v in flags.items()}
    for k in out:
        if current[k][-1]:
            out[k].append(int(now))
    return out
