"""M2 · Predicting how big a holding's move will be when a linked market jumps (docs/06).

Target: |asset return in the shock hour| / the pair's normal |return|. Gradient boosting (median loss) with
10%/90% quantile models for a range, vs the current product's fixed per-asset mean ratio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import DailyContext, hourly_book

DRAWS = 2000


def features(ctx: DailyContext) -> pd.DataFrame:
    shocks = ctx.watched["shocks"]
    s = shocks[(shocks["kind"] == "mapped") & (shocks["abs_r_normal"] > 0)].copy()
    s["y"] = s["r"].abs() / s["abs_r_normal"]
    book = hourly_book(ctx.hourly)
    recent, first = [], []
    for asset, idx in s.groupby("asset").groups.items():
        ends, closes = book.series[asset]
        r = np.abs(np.r_[np.nan, np.diff(np.log(closes))])
        trail = pd.Series(r).shift(1).rolling(24, min_periods=6).mean().to_numpy()
        pos = np.searchsorted(ends, s.loc[idx, "ts"].to_numpy())
        pos = np.clip(pos, 0, len(ends) - 1)
        recent.append(pd.Series(trail[pos], index=idx))
        gap = np.r_[np.inf, np.diff(ends)]
        first.append(pd.Series(gap[np.clip(pos - 1, 0, len(ends) - 1)] > 3600, index=idx))
    s["asset_recent_vol"] = pd.concat(recent) / s["abs_r_normal"]
    s["first_bar"] = pd.concat(first).astype(int)
    vol = ctx.all_markets.set_index("market_id")["volume_usd"]
    s["log_volume"] = np.log1p(s["market_id"].map(vol).astype(float))
    p = ctx.all_prices.sort_values("ts")
    mvol = []
    for market_id, idx in s.groupby("market_id").groups.items():
        g = p[p["market_id"] == market_id]
        ts, pv = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        grid = np.arange(ts[0] // 3600 * 3600, ts[-1] + 3600, 3600)
        pg = pv[np.clip(np.searchsorted(ts, grid, side="right") - 1, 0, len(pv) - 1)]
        d = pd.Series(np.abs(np.r_[np.nan, np.diff(pg)])).shift(1).rolling(24, min_periods=6).mean().to_numpy()
        at = np.clip(np.searchsorted(grid, s.loc[idx, "ts"].to_numpy(), side="right") - 2, 0, len(grid) - 1)
        mvol.append(pd.Series(d[at], index=idx))
    s["market_recent_vol"] = pd.concat(mvol)
    s["abs_dp"] = s["dp"].abs()
    s["hour"] = (s["ts"] // 3600) % 24
    s["group"] = s["groups"].str.split("|").str[0]
    for col in ("asset", "group"):
        s[col + "_code"] = s[col].astype("category").cat.codes
    return s.replace([np.inf, -np.inf], np.nan)


COLS = ["abs_dp", "asset_code", "group_code", "hour", "first_bar", "log_volume", "asset_recent_vol", "market_recent_vol"]


def run(ctx: DailyContext) -> ExperimentResult:
    s = features(ctx)
    train, test = s[s["ts"] < ctx.split_ts], s[s["ts"] >= ctx.split_ts]
    cat = [COLS.index("asset_code"), COLS.index("group_code")]
    fit = lambda loss, **kw: HistGradientBoostingRegressor(loss=loss, max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                          min_samples_leaf=40, categorical_features=cat, random_state=0, **kw
                                                          ).fit(train[COLS], train["y"])
    med = fit("absolute_error")
    lo_m, hi_m = fit("quantile", quantile=0.1), fit("quantile", quantile=0.9)
    pred, lo, hi = med.predict(test[COLS]), lo_m.predict(test[COLS]), hi_m.predict(test[COLS])
    base = test["asset"].map(train.groupby("asset")["y"].mean()).fillna(train["y"].mean()).to_numpy()
    base_med = test["asset"].map(train.groupby("asset")["y"].median()).fillna(train["y"].median()).to_numpy()
    y = test["y"].to_numpy()
    err_gbm, err_base, err_base_med = np.abs(y - pred), np.abs(y - base), np.abs(y - base_med)
    markets = test["market_id"].to_numpy()
    uniq, inv = np.unique(markets, return_inverse=True)
    d = np.bincount(inv, weights=err_gbm - err_base_med, minlength=len(uniq))
    c = np.bincount(inv, minlength=len(uniq))
    rng = np.random.default_rng(ctx.cfg.seed)
    boots = []
    for _ in range(DRAWS):
        w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        boots.append((w @ d) / (w @ c))
    dlo, dhi = np.quantile(boots, [0.025, 0.975])
    coverage = float(((y >= lo) & (y <= hi)).mean())
    rank_corr = float(pd.Series(pred).corr(pd.Series(y), method="spearman"))
    checks = {"mae_better_than_baseline": bool(dhi < 0), "range_coverage_70_90": bool(0.70 <= coverage <= 0.90)}
    verdict = "pass" if all(checks.values()) else "fail"
    importance = {}
    from sklearn.inspection import permutation_importance
    imp = permutation_importance(med, test[COLS], y, n_repeats=5, random_state=0, scoring="neg_mean_absolute_error")
    importance = dict(sorted(zip(COLS, imp.importances_mean.round(4)), key=lambda kv: -kv[1]))
    headline = (f"Test shocks {len(test)}: model MAE {err_gbm.mean():.3f} vs fixed per-asset median {err_base_med.mean():.3f} "
                f"(mean-based {err_base.mean():.3f}); difference {np.mean(boots):+.3f} (CI {dlo:+.3f} to {dhi:+.3f}). "
                f"10–90% range covers {coverage:.0%}. Rank correlation predicted vs actual {rank_corr:.2f}.")
    return ExperimentResult(id="m2", title="Move-size model", verdict=verdict, headline=headline,
                            question="Can a model predict the size of the holding's move better than a fixed per-asset ratio?",
                            metrics={"checks": checks, "mae_model": float(err_gbm.mean()), "mae_fixed_median": float(err_base_med.mean()),
                                     "mae_fixed_mean": float(err_base.mean()), "diff_ci": [float(dlo), float(dhi)],
                                     "coverage": coverage, "spearman": rank_corr, "importance": importance,
                                     "train": int(len(train)), "test": int(len(test))},
                            notes=["Baseline for the pass rule is the fixed per-asset median (the fairer baseline for absolute error)."])
