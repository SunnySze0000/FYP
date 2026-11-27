"""W10 (supervised wallet model) and M3 (direction model), both low priority (docs/06)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.m2_move_size import COLS, features

DRAWS = 2000


def _markouts(ctx: DailyContext) -> pd.DataFrame:
    t = ctx.tagged[["market_id", "ts", "wallet", "notional", "yes_dir", "yes_price", "cluster_id"]].copy()
    out = []
    for market_id, g in ctx.prices.sort_values("ts").groupby("market_id"):
        part = t[t["market_id"] == market_id]
        if part.empty:
            continue
        ts, p = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        i = np.searchsorted(ts, part["ts"].to_numpy() + 3600, side="right") - 1
        ok = (i >= 0) & (ts[np.clip(i, 0, None)] > part["ts"].to_numpy())
        out.append(part.assign(markout=np.where(ok, part["yes_dir"] * (p[np.clip(i, 0, None)] - part["yes_price"]), np.nan)))
    return pd.concat(out).dropna(subset=["markout"])


def _boot_diff(a: pd.DataFrame, b: pd.DataFrame, rng) -> tuple[float, float, float]:
    """Mean trade markout of a minus b, bootstrapping wallets within each set."""
    def stats(f):
        g = f.groupby("wallet")["markout"].agg(["sum", "count"])
        return g["sum"].to_numpy(), g["count"].to_numpy()
    sa, ca = stats(a)
    sb, cb = stats(b)
    diffs = []
    for _ in range(DRAWS):
        ia, ib = rng.integers(0, len(sa), len(sa)), rng.integers(0, len(sb), len(sb))
        diffs.append(sa[ia].sum() / ca[ia].sum() - sb[ib].sum() / cb[ib].sum())
    return float(a["markout"].mean() - b["markout"].mean()), float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))


def run_w10(ctx: DailyContext) -> ExperimentResult:
    m = _markouts(ctx)
    early, late = m[m["ts"] < ctx.split_ts], m[m["ts"] >= ctx.split_ts]
    g = early.groupby("wallet")
    feat = pd.DataFrame({
        "trades": g.size(), "days": g["ts"].agg(lambda s: s.floordiv(86_400).nunique()), "markets": g["market_id"].nunique(),
        "mean_usd": g["notional"].mean(), "median_usd": g["notional"].median(),
        "large_share": g["notional"].agg(lambda s: (s >= 5_000).mean()), "buy_yes_share": g["yes_dir"].agg(lambda s: (s > 0).mean()),
        "early_markout": g["markout"].mean(),
        "cluster": g["cluster_id"].agg(lambda s: {"C0": 0, "C1": 1, "C2": 2}.get(s.iloc[0], 3)),
    })
    two = early.groupby(["wallet", "market_id"])["yes_dir"].nunique().gt(1).groupby(level=0).mean()
    feat["two_sided"] = two
    target = late.groupby("wallet")["markout"].agg(["mean", "count"])
    data = feat.join(target, how="inner")
    data = data[(data["count"] >= 5) & (data["trades"] >= 3)]
    rng = np.random.default_rng(ctx.cfg.seed)
    wallets = data.index.to_numpy()
    rng.shuffle(wallets)
    half = len(wallets) // 2
    fit_w, eval_w = wallets[:half], wallets[half:]            # fit on half the wallets, rank the other half
    cols = [c for c in feat.columns]
    model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, min_samples_leaf=50, random_state=0,
                                          categorical_features=[cols.index("cluster")])
    model.fit(data.loc[fit_w, cols], data.loc[fit_w, "mean"].clip(-0.2, 0.2), sample_weight=np.sqrt(data.loc[fit_w, "count"]))
    score = pd.Series(model.predict(data.loc[eval_w, cols]), index=eval_w)
    top = score[score >= score.quantile(0.9)].index
    late_eval = late[late["wallet"].isin(eval_w)]
    top_trades = late_eval[late_eval["wallet"].isin(top)]
    vs_all = _boot_diff(top_trades, late_eval, rng)
    vs_large = _boot_diff(top_trades, late[late["notional"] >= 5_000], rng)
    checks = {"beats_all_wallets": vs_all[1] > 0, "beats_large_trade_rule": vs_large[1] > 0}
    verdict = "pass" if all(checks.values()) else "fail"
    headline = (f"Top-decile wallets by the model ({len(top)} wallets, {len(top_trades)} later trades): 1-hour markout "
                f"{top_trades['markout'].mean() * 100:+.2f} points vs all evaluated wallets {late_eval['markout'].mean() * 100:+.2f} "
                f"(diff {vs_all[0] * 100:+.2f}, CI {vs_all[1] * 100:+.2f} to {vs_all[2] * 100:+.2f}) and vs $5k+ trades "
                f"{late[late['notional'] >= 5_000]['markout'].mean() * 100:+.2f} (diff {vs_large[0] * 100:+.2f}, CI {vs_large[1] * 100:+.2f} to {vs_large[2] * 100:+.2f}).")
    return ExperimentResult(id="w10", title="Supervised wallet model", verdict=verdict, headline=headline,
                            question="Can a model on wallet history pick wallets whose later trades lead the price?",
                            metrics={"checks": checks, "wallets": int(len(data)), "vs_all": vs_all, "vs_large": vs_large})


def run_m3(ctx: DailyContext) -> ExperimentResult:
    s = features(ctx)
    t = ctx.tagged
    big = t[t["notional"] >= 5_000]
    flow = []
    for market_id, idx in s.groupby("market_id").groups.items():
        b = big[big["market_id"] == market_id].sort_values("ts")
        ts, c = b["ts"].to_numpy(), np.r_[0, np.cumsum((b["yes_dir"] * b["notional"]).to_numpy())]
        x = s.loc[idx, "ts"].to_numpy()
        flow.append(pd.Series(c[np.searchsorted(ts, x - 900, side="right")] - c[np.searchsorted(ts, x - 3600, side="right")], index=idx))
    s["whale_flow_signed"] = pd.concat(flow) * np.sign(s["dp"])
    train = s[s["ts"] < ctx.split_ts]
    orient = np.sign((np.sign(train["r"]) * np.sign(train["dp"])).groupby([train["group"], train["asset"]]).mean())
    s["orient"] = [orient.get((g, a), 1.0) or 1.0 for g, a in zip(s["group"], s["asset"])]
    s["y"] = (np.sign(s["r"]) == np.sign(s["dp"]) * s["orient"]).astype(int)
    s = s[s["r"] != 0]
    train, test = s[s["ts"] < ctx.split_ts], s[s["ts"] >= ctx.split_ts]
    cols = COLS + ["orient", "whale_flow_signed"]
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=40, random_state=0,
                                         categorical_features=[cols.index("asset_code"), cols.index("group_code")])
    clf.fit(train[cols], train["y"])
    prob = clf.predict_proba(test[cols])[:, 1]
    hit = np.where(prob >= 0.5, test["y"], 1 - test["y"]).astype(float)
    rule = test["y"].to_numpy(float)
    markets = test["market_id"].to_numpy()
    uniq, inv = np.unique(markets, return_inverse=True)
    rng = np.random.default_rng(ctx.cfg.seed)
    hs, rs, cs = (np.bincount(inv, weights=v, minlength=len(uniq)) for v in (hit, rule, np.ones(len(hit))))
    boots = []
    for _ in range(DRAWS):
        w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        boots.append((w @ hs / (w @ cs), w @ rs / (w @ cs)))
    boots = np.array(boots)
    lo = float(np.quantile(boots[:, 0], 0.025))
    checks = {"ci_above_52": lo > 0.52, "above_v2_rule": float(hit.mean()) > float(rule.mean())}
    verdict = "pass" if all(checks.values()) else "fail"
    headline = (f"Test shocks {len(test)}: model hit rate {hit.mean():.1%} (CI {lo:.1%} to {np.quantile(boots[:, 0], 0.975):.1%}) "
                f"vs simple co-movement rule {rule.mean():.1%}.")
    return ExperimentResult(id="m3", title="Direction model", verdict=verdict, headline=headline,
                            question="Can a model call the direction of the holding's move after a linked jump?",
                            metrics={"checks": checks, "hit": float(hit.mean()), "rule": float(rule.mean()), "low": lo})
