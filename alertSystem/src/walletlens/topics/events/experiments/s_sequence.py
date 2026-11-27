"""S1-S3 · Does the event jump come before the stock move? (docs/09_sequence_test.md)"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.config import ASSET_GROUPS
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import WATCH_AGE, WATCH_HIGH, WATCH_LOW, DailyContext, hourly_book
from walletlens.topics.events.panel import placebo_assets

LAGS = range(-3, 4)
DRAWS = 2000
CRYPTO = {"BTC-USD", "ETH-USD"}


def jumps(ctx: DailyContext, gap_h: int = 6) -> pd.DataFrame:
    """First watched 10-point jump of each market within any 6-hour window (hour grid; ts = end of jump hour)."""
    rows = []
    for market_id, g in ctx.all_prices.sort_values("ts").groupby("market_id"):
        ts, p = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        grid = np.arange(ts[0] // 3600 * 3600 + 3600, ts[-1] + 1, 3600)
        now = p[np.searchsorted(ts, grid, side="right") - 1]
        j = np.searchsorted(ts, grid - 3600, side="right") - 1
        prev = np.where(j >= 0, p[np.maximum(j, 0)], np.nan)
        hit = (prev >= WATCH_LOW) & (prev <= WATCH_HIGH) & (grid - 3600 - ts[0] >= WATCH_AGE) & (np.abs(now - prev) >= ctx.cfg.shock_points)
        last = -10**12
        for t, dp in zip(grid[hit], (now - prev)[hit]):
            if t - last >= gap_h * 3600:
                rows.append({"market_id": market_id, "ts": int(t), "dp": float(dp)})
            last = t
    out = pd.DataFrame(rows)
    groups = ctx.all_markets.set_index("market_id")["groups"]
    out["groups"] = out["market_id"].map(groups)
    return out.dropna(subset=["groups"])


def _assets(groups: str, market_id: str, pool: list[str]) -> tuple[list[str], list[str]]:
    mapped = sorted({a for g in groups.split("|") if g != "us_politics" for a in ASSET_GROUPS.get(g, ())})
    return mapped, placebo_assets(market_id, set(mapped), pool) if mapped else []


def _boot(values: pd.Series, keys: pd.Series, rng) -> tuple[float, float, float]:
    frame = pd.DataFrame({"v": values.to_numpy(), "k": keys.to_numpy()}).dropna()
    if len(frame) < 10:
        return np.nan, np.nan, np.nan
    per = frame.groupby("k")["v"].agg(["sum", "count"])
    s, c = per["sum"].to_numpy(), per["count"].to_numpy()
    boots = [(s[i].sum() / c[i].sum()) for i in (rng.integers(0, len(s), len(s)) for _ in range(DRAWS))]
    return float(frame["v"].mean()), float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))


def run(ctx: DailyContext, exclude: tuple = ()) -> ExperimentResult:
    rng = np.random.default_rng(ctx.cfg.seed)
    book = hourly_book(ctx.hourly)
    pool = sorted(s for s in book.series if s in {a for v in ASSET_GROUPS.values() for a in v})
    series = {}
    for s, (ends, closes) in book.series.items():
        r = np.abs(np.r_[np.nan, np.diff(np.log(closes))])
        contiguous = np.r_[False, np.diff(ends) == 3600]
        hod = (ends // 3600) % 24
        norm = pd.Series(np.where(contiguous, r, np.nan)).groupby(hod).transform("mean").to_numpy()
        first = ~contiguous                                   # first bar after a gap (session open for stocks)
        first_norm = np.nanmean(np.where(first, r, np.nan)) if first.any() else np.nan
        series[s] = {"ends": ends, "r_signed": np.r_[np.nan, np.diff(np.log(closes))], "y": r / norm,
                     "contig": contiguous, "first": first, "first_y": r / first_norm}
    J = jumps(ctx)
    if exclude:
        J = J[~J["groups"].str.split("|").map(lambda gs: any(g in exclude for g in gs))]
        pool = [a for a in pool if a not in CRYPTO | {"COIN", "MSTR"}]

    # ---------------- S1: event-time profile, jumps on each asset's own bar grid (as V1)
    sh = ctx.watched["shocks"].sort_values("ts")
    sh = sh[~sh["groups"].fillna("").str.fullmatch("us_politics")]
    if exclude:
        sh = sh[~sh["groups"].fillna("").str.split("|").map(lambda gs: any(g in exclude for g in gs))]
        sh = sh[~sh["asset"].isin(CRYPTO | {"COIN", "MSTR"})]
    keep, last = [], {}
    for idx, row in zip(sh.index, sh.itertuples(index=False)):
        key = (row.market_id, row.asset)
        if row.ts - last.get(key, -10**12) >= 6 * 3600:
            keep.append(idx)
        last[key] = row.ts
    sh = sh.loc[keep]
    rows = []
    for row in sh.itertuples(index=False):
        s = series.get(row.asset)
        if s is None:
            continue
        i = int(np.searchsorted(s["ends"], row.ts))
        if i >= len(s["ends"]) or s["ends"][i] != row.ts:
            continue
        out = {"market_id": row.market_id, "asset": row.asset, "kind": row.kind, "ts": row.ts, "dp": row.dp,
               "group": str(row.groups).split("|")[0]}
        for k in LAGS:
            j = i + k
            lo_, hi_ = min(i, j), max(i, j)
            ok = 0 <= lo_ and hi_ < len(s["ends"]) and s["contig"][lo_ + 1: hi_ + 1].all() and s["contig"][j]
            out[f"y{k:+d}"] = s["y"][j] if ok else np.nan
        j = i + 1
        out["r+1"] = s["r_signed"][j] if j < len(s["ends"]) and s["contig"][j] else np.nan
        rows.append(out)
    P = pd.DataFrame(rows)
    per = P.groupby(["market_id", "kind"])[[f"y{k:+d}" for k in LAGS]].mean().unstack("kind")
    profile = []
    for k in LAGS:
        col = f"y{k:+d}"
        diff = (per[(col, "mapped")] - per[(col, "placebo")]).dropna()
        m, lo, hi = _boot(diff, diff.index.to_series(), rng)
        profile.append({"hour": k, "linked": float(per[(col, "mapped")].mean()), "placebo": float(per[(col, "placebo")].mean()),
                        "excess": m, "low": lo, "high": hi})
    profile = pd.DataFrame(profile)
    after_minus_before = (per[("y+1", "mapped")] - per[("y-1", "mapped")]).dropna()
    amb = _boot(after_minus_before, after_minus_before.index.to_series(), rng)
    plus1 = profile.set_index("hour").loc[1]
    s1 = {"a_plus1_excess": bool(plus1["low"] > 0), "b_after_gt_before": bool(amb[1] > 0)}

    # ---------------- S2: overnight jumps -> next open
    rows = []
    for jp in J.itertuples(index=False):
        mapped, placebo = _assets(jp.groups, jp.market_id, pool)
        for kind, assets in (("mapped", mapped), ("placebo", placebo)):
            for a in assets:
                if a in CRYPTO or a not in series:
                    continue
                s = series[a]
                i = int(np.searchsorted(s["ends"], jp.ts))
                if i == 0 or i >= len(s["ends"]) or not s["first"][i]:
                    continue                                     # next bar must be a session's first bar
                if jp.ts - 3600 < s["ends"][i - 1]:              # jump hour must start after the previous close
                    continue
                if s["ends"][i] - 3600 < jp.ts:                  # and end before the next session opens
                    continue
                rows.append({"market_id": jp.market_id, "asset": a, "kind": kind, "y": s["first_y"][i]})
    O = pd.DataFrame(rows)
    on = O.groupby(["market_id", "kind"])["y"].mean().unstack().dropna()
    s2 = _boot(on["mapped"] - on["placebo"], on.index.to_series(), rng)

    # ---------------- S3: direction in the hour after
    M = P[P["kind"] == "mapped"].dropna(subset=["r+1"])
    train = M[M["ts"] < ctx.split_ts]
    orient = np.sign((np.sign(train["r+1"]) * np.sign(train["dp"])).groupby([train["group"], train["asset"]]).mean())
    test = M[M["ts"] >= ctx.split_ts].copy()
    test["o"] = [orient.get((g, a), np.nan) for g, a in zip(test["group"], test["asset"])]
    test = test[(test["o"] != 0) & test["o"].notna() & (test["r+1"] != 0)]
    hit = (np.sign(test["r+1"]) == np.sign(test["dp"]) * test["o"]).astype(float)
    s3 = _boot(hit, test["market_id"], rng)

    checks = {"S1": all(s1.values()), "S2": bool(s2[1] > 0), "S3": bool(s3[1] > 0.52)}
    verdict = "pass" if checks["S1"] or checks["S2"] else "fail"
    p = profile.set_index("hour")
    headline = (f"S1 linked − placebo by hour: " + ", ".join(f"{k:+d}h {p.loc[k, 'excess']:+.2f}" for k in LAGS)
                + f"; +1h CI {p.loc[1, 'low']:+.2f} to {p.loc[1, 'high']:+.2f}; after − before (linked) {amb[0]:+.2f} "
                f"(CI {amb[1]:+.2f} to {amb[2]:+.2f}). S2 overnight jump → next open: linked − placebo {s2[0]:+.2f} "
                f"(CI {s2[1]:+.2f} to {s2[2]:+.2f}, {len(on)} jumps). S3 direction next hour {s3[0]:.1%} (CI {s3[1]:.1%} to {s3[2]:.1%}).")
    return ExperimentResult(id="s", title="Does the jump come first?", verdict=verdict, headline=headline,
                            question="When an event jumps, does the linked stock move afterwards (not just at the same time)?",
                            metrics={"checks": checks, "s1": s1, "after_minus_before": amb, "s2": s2, "s3": s3,
                                     "jumps": int(len(J)), "s1_markets": int(len(per)), "s2_markets": int(len(on)),
                                     "s3_tests": int(len(test))},
                            tables={"profile": profile})
