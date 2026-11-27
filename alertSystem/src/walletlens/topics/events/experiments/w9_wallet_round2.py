"""W9 · Wallet insights round 2: five holding-level wallet signals (docs/06_round3_research.md).

Each signal is computed per holding over all markets linked to it, and tested like W7: next-hour (W9d:
next-day) |return| vs normal, pooled with a day bootstrap, >= 50% of holdings positive, beats a placebo
built from unlinked markets, survives dropping jump hours. 99% intervals (Bonferroni x 5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import daily_book
from walletlens.topics.events.experiments.w7_cluster_holding import _bootstrap, _links
from walletlens.topics.events.wallet_context import WalletContext

GAP = 900
LEVEL = 1 - 0.05 / 5
DRAWS = 1000
SIGNALS = ("W9a_breadth", "W9b_cross_market", "W9c_mm_withdraw", "W9e_concentration")


def _trailing(values: np.ndarray, n: int, min_periods: int = 12) -> np.ndarray:
    return pd.Series(values).shift(1).rolling(n, min_periods=min_periods).mean().to_numpy()


def hourly_signals(t: pd.DataFrame, offset: int, w0: int, n: int) -> pd.DataFrame:
    """Signals per hourly window w (window ends at offset + (w0 + w) * 3600 - GAP)."""
    w = ((t["ts"].to_numpy("int64") + GAP - offset - 1) // 3600 + 1) - w0
    t = t.assign(w=w)
    t = t[(t["w"] >= 0) & (t["w"] < n)]
    gross = np.bincount(t["w"], weights=t["notional"], minlength=n)
    c0 = np.bincount(t["w"], weights=t["notional"] * (t["cluster_id"] == "C0"), minlength=n)
    wallets = t.drop_duplicates(["w", "wallet"])
    breadth = np.bincount(wallets["w"], minlength=n).astype(float)
    per_wallet = t.drop_duplicates(["w", "wallet", "market_id"]).groupby(["w", "wallet"]).size()
    cross = per_wallet[per_wallet >= 2].reset_index()
    cross_n = np.bincount(cross["w"], minlength=n).astype(float) if len(cross) else np.zeros(n)
    by_wallet = t.groupby(["w", "wallet"])["notional"].sum()
    top = by_wallet.groupby(level=0).max()
    top_share = np.zeros(n)
    top_share[top.index.to_numpy()] = top.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        top_share = np.where(gross > 0, top_share / gross, 0.0)
        c0_share = np.where(gross > 0, c0 / gross, np.nan)
    lb = np.log1p(breadth)
    lc = np.log1p(cross_n)
    c0_trail = pd.Series(c0_share).shift(1).rolling(48, min_periods=12).mean().to_numpy()
    g_trail = _trailing(gross, 48)
    return pd.DataFrame({
        "W9a_breadth": (lb - _trailing(lb, 48) >= 1) & (breadth >= 10),
        "W9b_cross_market": (lc - _trailing(lc, 48) >= 1) & (cross_n >= 3),
        "W9c_mm_withdraw": (c0_trail > 0.05) & (c0_share <= c0_trail / 3) & (gross >= g_trail) & (gross > 0),
        "W9e_concentration": (top_share >= 0.5) & (gross >= 5_000),
    })


def run(ctx: WalletContext) -> ExperimentResult:
    trades = ctx.tagged[["market_id", "ts", "wallet", "notional", "cluster_id"]]
    links = _links(ctx.markets)
    all_ids = set(trades["market_id"].unique())
    # jump hours per market (as in W7)
    jumps = {}
    for market_id, g in ctx.prices.sort_values("ts").groupby("market_id"):
        ts, p = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        grid = np.arange(ts[0] // 3600 * 3600 + 3600, ts[-1] + 1, 3600)
        i, j = np.searchsorted(ts, grid, side="right") - 1, np.searchsorted(ts, grid - 3600, side="right") - 1
        jumps[market_id] = grid[(j >= 0) & (np.abs(p[i] - p[np.maximum(j, 0)]) >= ctx.cfg.shock_points)]
    tmin, tmax = int(trades["ts"].min()), int(trades["ts"].max())
    rows = []
    for asset, bars in ctx.hourly.sort_values("end_ts").groupby("symbol"):
        linked = links.get(asset, set()) & all_ids
        if len(linked) < 3:
            continue
        end, close = bars["end_ts"].to_numpy("int64"), bars["close"].to_numpy(float)
        start = end - 3600
        offset = int(pd.Series(start % 3600).mode().iloc[0])
        w0 = (tmin - offset) // 3600 - 60
        n = (tmax - offset) // 3600 - w0 + 4
        same = np.r_[False, end[1:] - end[:-1] == 3600]
        r = np.r_[np.nan, np.log(close[1:] / close[:-1])]
        widx = (start - offset) // 3600 - w0                   # window ending at start - GAP
        valid = same & np.isfinite(r) & (widx >= 0) & (widx < n) & ((start - offset) % 3600 == 0)
        frame = pd.DataFrame({"asset": asset, "start": start[valid], "absr": np.abs(r[valid])})
        k = widx[valid]
        lk = hourly_signals(trades[trades["market_id"].isin(linked)], offset, w0, n)
        pl = hourly_signals(trades[~trades["market_id"].isin(linked)], offset, w0, n)
        for s in SIGNALS:
            frame[f"lk_{s}"], frame[f"pl_{s}"] = lk[s].to_numpy()[k], pl[s].to_numpy()[k]
        jt = np.sort(np.concatenate([jumps.get(m, np.array([], dtype=np.int64)) for m in linked]))
        s_ = frame["start"].to_numpy()
        frame["jump_hour"] = np.searchsorted(jt, s_ + 3600, side="right") > np.searchsorted(jt, s_ - 4500, side="right")
        rows.append(frame)
    panel = pd.concat(rows, ignore_index=True)
    panel["hod"], panel["day"] = (panel["start"] // 3600) % 24, panel["start"] // 86_400
    norm = panel[panel["start"] < ctx.split_ts].groupby(["asset", "hod"])["absr"].mean().rename("norm")
    panel = panel.join(norm, on=["asset", "hod"])
    panel = panel[panel["norm"] > 0].assign(y=lambda f: f["absr"] / f["norm"])

    results = [_evaluate(panel[panel["start"] >= ctx.split_ts], s, ctx) for s in SIGNALS]
    results.append(_daily(ctx, trades, links, all_ids))
    table = pd.DataFrame(results)
    passed = table.loc[table["pass"], "signal"].tolist()
    headline = ("Passed: " + ", ".join(passed) + ". " if passed else "None of the five signals passes. ") + "; ".join(
        f"{r.signal} {r.effect:+.3f} (CI {r.low:+.3f} to {r.high:+.3f}, {r.share_positive:.0%} of {r.holdings_tested} holdings)"
        for r in table.itertuples())
    return ExperimentResult(
        id="w9", title="Wallet insights round 2", verdict="pass" if passed else "fail", headline=headline,
        question="Which holding-level wallet signals come before bigger moves in the holding, across most holdings?",
        metrics={"rows": table.to_dict("records")}, tables={"summary": table},
        notes=["Outcome: next-hour (W9d next-day) |return| relative to normal (1.0 = normal); hours after 2026-01-01."])


def _evaluate(frame: pd.DataFrame, s: str, ctx, unit: str = "hour") -> dict:
    flag, placebo = f"lk_{s}", f"pl_{s}"
    rng = np.random.default_rng(ctx.cfg.seed)
    diff = lambda f, c: f.loc[f[c], "y"].mean() - f.loc[~f[c], "y"].mean()
    boot = _bootstrap(frame, flag, rng, DRAWS)
    pboot = _bootstrap(frame, placebo, np.random.default_rng(ctx.cfg.seed), DRAWS)
    lo, hi = np.quantile(boot, [(1 - LEVEL) / 2, 1 - (1 - LEVEL) / 2])
    per = []
    for _, g in frame.groupby("asset"):
        if g[flag].sum() >= 20:
            per.append(diff(g, flag) > 0)
    share = float(np.mean(per)) if per else np.nan
    nojump = diff(frame[~frame["jump_hour"]], flag) if "jump_hour" in frame else np.nan
    checks = {"pooled_ci_above_0": bool(lo > 0), "half_of_holdings": bool(share >= 0.5),
              "beats_placebo": bool(np.quantile(boot - pboot, (1 - LEVEL) / 2) > 0),
              "survives_without_jumps": bool(nojump > 0) if np.isfinite(nojump) else True}
    return {"signal": s, "effect": diff(frame, flag), "low": lo, "high": hi, "signal_hours": int(frame[flag].sum()),
            "placebo_effect": diff(frame, placebo), "effect_without_jumps": nojump, "holdings_tested": len(per),
            "share_positive": share, "checks": checks, "pass": all(checks.values())}


def _daily(ctx, trades, links, all_ids) -> dict:
    book = daily_book(ctx.daily)
    rows = []
    t_ts = trades["ts"].to_numpy("int64")
    large = trades["notional"].to_numpy() >= 5_000
    for asset, (ends, closes) in book.series.items():
        linked = links.get(asset, set()) & all_ids
        if len(linked) < 3:
            continue
        is_l = trades["market_id"].isin(linked).to_numpy()
        frame = []
        for side, mask in (("lk", is_l & large), ("pl", ~is_l & large)):
            ts, usd = t_ts[mask], trades["notional"].to_numpy()[mask]
            order = np.argsort(ts)
            ts, c = ts[order], np.r_[0, np.cumsum(usd[order])]
            cut = ends - GAP
            flow = c[np.searchsorted(ts, cut, side="right")] - c[np.searchsorted(ts, cut - 86_400, side="right")]
            lf = np.log1p(flow)
            frame.append(pd.Series((lf - _trailing(lf, 7, 3) >= 1) & (flow >= 5_000), name=f"{side}_W9d_daily"))
        r_next = np.r_[np.log(closes[1:] / closes[:-1]), np.nan]
        gap_ok = np.r_[ends[1:] - ends[:-1] <= 4 * 86_400, False]
        df = pd.concat(frame, axis=1).assign(asset=asset, start=ends, absr=np.abs(r_next))[gap_ok & np.isfinite(r_next)]
        rows.append(df)
    panel = pd.concat(rows, ignore_index=True)
    panel["day"] = panel["start"] // 86_400
    norm = panel[panel["start"] < ctx.split_ts].groupby("asset")["absr"].mean().rename("norm")
    panel = panel.join(norm, on="asset").assign(y=lambda f: f["absr"] / f["norm"])
    return _evaluate(panel[panel["start"] >= ctx.split_ts], "W9d_daily", ctx)
