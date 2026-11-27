"""W7 · Cluster surge -> holding risk (pre-registered in docs/04_wallet_directions.md).

When one wallet cluster suddenly trades far more than usual in the markets linked to a holding, is the
holding's next-hour move bigger than usual? Pooled over holdings, per cluster; generality = positive in
>= 50% of holdings with >= 20 surge hours.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.config import ASSET_GROUPS
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import WalletContext

Q = 900                       # quarter-hour buckets
GAP_Q = 1                     # 15-minute data-delay gap
WINDOW_Q = 4                  # one-hour flow window
TRAIL_H = 48
SURGE_Z, SURGE_MIN_USD = 2.0, 1_000
CATEGORIES = ("C0", "C1", "C2", "all", "large")
CLUSTERS = ("C0", "C1", "C2")
LEVEL = 1 - 0.05 / 3
DRAWS = 1000
WEAK = {"us_politics"}


def _links(markets: pd.DataFrame) -> dict[str, set[str]]:
    links: dict[str, set[str]] = {}
    for m in markets.itertuples(index=False):
        for g in str(m.groups).split("|"):
            if g and g not in WEAK:
                for a in ASSET_GROUPS.get(g, ()):
                    links.setdefault(a, set()).add(m.market_id)
    return links


def _quarter_flows(trades: pd.DataFrame, q0: int, n: int) -> dict[str, dict[str, np.ndarray]]:
    """Per market and category: dollars traded per quarter-hour bucket (dense arrays)."""
    t = trades[["market_id", "ts", "notional", "cluster_id"]].copy()
    t["q"] = (t["ts"].to_numpy("int64") // Q - q0).astype(np.int64)
    t["large"] = trades["notional"].to_numpy() >= 5_000
    out: dict[str, dict[str, np.ndarray]] = {}
    for market_id, g in t.groupby("market_id"):
        flows = {}
        for cat in CATEGORIES:
            part = g if cat == "all" else g[g["large"]] if cat == "large" else g[g["cluster_id"] == cat]
            flows[cat] = np.bincount(part["q"].to_numpy(), weights=part["notional"].to_numpy(), minlength=n)[:n]
        out[market_id] = flows
    return out


def _surge_z(series: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hourly flow ending at each quarter index k and its log excess over the trailing 48 hours."""
    c = np.concatenate([[0.0], np.cumsum(series)])
    hour = c[WINDOW_Q:] - c[:-WINDOW_Q]                       # flow in quarters (k-3..k), indexed by k-3
    hour = np.concatenate([np.zeros(WINDOW_Q - 1), hour])     # index k -> window ending at quarter k
    log = np.log1p(hour)
    trail = np.full_like(log, np.nan)
    for r in range(WINDOW_Q):                                 # previous 48 hours = same residue, lags 1..48
        sub = pd.Series(log[r::WINDOW_Q])
        trail[r::WINDOW_Q] = sub.shift(1).rolling(TRAIL_H, min_periods=12).mean().to_numpy()
    return hour, log - trail


def _bootstrap(frame: pd.DataFrame, flag: str, rng, draws: int) -> np.ndarray:
    days = frame["day"].to_numpy()
    uniq, inv = np.unique(days, return_inverse=True)
    y, f = frame["y"].to_numpy(), frame[flag].to_numpy()
    sy_s = np.bincount(inv, weights=y * f, minlength=len(uniq))
    n_s = np.bincount(inv, weights=f.astype(float), minlength=len(uniq))
    sy_o = np.bincount(inv, weights=y * ~f, minlength=len(uniq))
    n_o = np.bincount(inv, weights=(~f).astype(float), minlength=len(uniq))
    out = np.empty(draws)
    for i in range(draws):
        w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        out[i] = (w @ sy_s) / max(w @ n_s, 1) - (w @ sy_o) / max(w @ n_o, 1)
    return out


def build_panel(ctx: WalletContext) -> pd.DataFrame:
    markets = ctx.markets
    trades = ctx.tagged
    links = _links(markets)
    q0 = int(trades["ts"].min()) // Q - 400
    n = int(trades["ts"].max()) // Q - q0 + 8
    flows = _quarter_flows(trades, q0, n)
    all_ids = set(flows)

    prices = ctx.prices.sort_values("ts")
    jumps = {}
    for market_id, g in prices.groupby("market_id"):
        ts, p = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        grid = np.arange(ts[0] // 3600 * 3600 + 3600, ts[-1] + 1, 3600)
        idx = np.searchsorted(ts, grid, side="right") - 1
        prev = np.searchsorted(ts, grid - 3600, side="right") - 1
        ok = prev >= 0
        dp = np.where(ok, p[idx] - p[np.maximum(prev, 0)], 0)
        jumps[market_id] = grid[np.abs(dp) >= ctx.cfg.shock_points]

    rows = []
    hourly = ctx.hourly.sort_values("end_ts")
    for asset, bars in hourly.groupby("symbol"):
        linked = links.get(asset, set()) & all_ids
        if len(linked) < 3:
            continue
        unlinked = all_ids - linked
        end, close = bars["end_ts"].to_numpy("int64"), bars["close"].to_numpy(float)
        start = end - 3600
        same = np.r_[False, end[1:] - end[:-1] == 3600]
        r = np.r_[np.nan, np.log(close[1:] / close[:-1])]
        k = (start - GAP_Q * Q) // Q - q0 - 1                  # quarter index of the flow window's last bucket
        valid = same & np.isfinite(r) & (k >= 0) & (k < n)
        frame = pd.DataFrame({"asset": asset, "start": start[valid], "absr": np.abs(r[valid])})
        kk = k[valid]
        for side, ids in (("lk", linked), ("pl", unlinked)):
            for cat in CATEGORIES:
                total = np.zeros(n)
                for m in ids:
                    total += flows[m][cat]
                hour, z = _surge_z(total)
                frame[f"{side}_{cat}"] = (z[kk] >= SURGE_Z) & (hour[kk] >= SURGE_MIN_USD)
        jt = np.sort(np.concatenate([jumps.get(m, np.array([], dtype=np.int64)) for m in linked])) if linked else np.array([])
        s = frame["start"].to_numpy()
        lo, hi = np.searchsorted(jt, s - 4500, side="right"), np.searchsorted(jt, s + 3600, side="right")
        frame["jump_hour"] = hi > lo
        rows.append(frame)
    panel = pd.concat(rows, ignore_index=True)
    panel["hod"] = (panel["start"] // 3600) % 24
    panel["day"] = panel["start"] // 86_400
    early = panel[panel["start"] < ctx.split_ts]
    norm = early.groupby(["asset", "hod"])["absr"].mean().rename("norm")
    panel = panel.join(norm, on=["asset", "hod"])
    panel = panel[panel["norm"] > 0]
    panel["y"] = panel["absr"] / panel["norm"]
    return panel


def _effect(frame, flag):
    s, o = frame.loc[frame[flag], "y"], frame.loc[~frame[flag], "y"]
    return (s.mean() - o.mean()) if len(s) and len(o) else np.nan, int(len(s))


def run(ctx: WalletContext) -> ExperimentResult:
    panel = build_panel(ctx)
    rng = np.random.default_rng(ctx.cfg.seed)
    late = panel[panel["start"] >= ctx.split_ts]
    rows, per_asset, checks = [], [], {}
    for cat in CATEGORIES:
        flag, placebo = f"lk_{cat}", f"pl_{cat}"
        eff, n = _effect(late, flag)
        boot = _bootstrap(late, flag, rng, DRAWS)
        lo, hi = np.quantile(boot, [(1 - LEVEL) / 2, 1 - (1 - LEVEL) / 2])
        pl_eff, pl_n = _effect(late, placebo)
        diff_boot = boot - _bootstrap(late, placebo, np.random.default_rng(ctx.cfg.seed), DRAWS)
        dlo = np.quantile(diff_boot, (1 - LEVEL) / 2)
        nojump, _ = _effect(late[~late["jump_hour"]], flag)
        early_eff, early_n = _effect(panel[panel["start"] < ctx.split_ts], flag)
        assets = []
        for asset, g in late.groupby("asset"):
            e, k = _effect(g, flag)
            if k >= 20:
                assets.append({"category": cat, "asset": asset, "effect": e, "surge_hours": k})
        share = float(np.mean([a["effect"] > 0 for a in assets])) if assets else np.nan
        per_asset += assets
        row = {"category": cat, "effect": eff, "low": lo, "high": hi, "surge_hours": n, "placebo_effect": pl_eff,
               "linked_minus_placebo_low": dlo, "effect_without_jump_hours": nojump,
               "holdings_tested": len(assets), "share_positive": share, "early_period_effect": early_eff,
               "early_surge_hours": early_n}
        if cat in CLUSTERS:
            row["checks"] = {"pooled_ci_above_0": bool(lo > 0), "half_of_holdings": bool(share >= 0.5),
                             "beats_placebo": bool(dlo > 0), "survives_without_jumps": bool(nojump > 0)}
            row["pass"] = all(row["checks"].values())
            checks[cat] = row["pass"]
        rows.append(row)
    table = pd.DataFrame(rows)
    passed = [c for c, ok in checks.items() if ok]
    verdict = "pass" if passed else "fail"
    names = {"C0": "market makers", "C1": "patient traders", "C2": "burst traders"}
    def line(r):
        return (f"{r['category']}: {r['effect']:+.3f} (CI {r['low']:+.3f} to {r['high']:+.3f}), "
                f"{r['share_positive']:.0%} of {r['holdings_tested']} holdings positive")
    headline = ("Passed: " + ", ".join(names[c] for c in passed) + ". " if passed else "No cluster passes. ") + \
        "; ".join(line(r) for r in rows if r["category"] in CLUSTERS)
    return ExperimentResult(
        id="w7", title="Cluster surge → holding risk", verdict=verdict, headline=headline,
        question="Does a sudden surge by one wallet cluster in a holding's linked markets come before a bigger next-hour move in the holding?",
        metrics={"rows": table.to_dict("records"), "panel_rows": int(len(panel)), "test_rows": int(len(late))},
        tables={"summary": table, "per_holding": pd.DataFrame(per_asset)},
        notes=["Outcome = next-hour |return| / asset's average |return| at that hour of day (1.0 = normal).",
               "Main test uses hours after the cluster fit date (out of sample); 98.3% intervals (Bonferroni, 3 clusters)."])
