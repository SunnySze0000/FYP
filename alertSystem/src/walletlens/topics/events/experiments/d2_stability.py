"""D2 · Do the effects hold quarter by quarter, including the latest quarter?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import DailyContext, quarter
from walletlens.topics.events.experiments.w3_early_warning import _auc, _features, _fit_logistic

BASE = ["abs_dp", "recent_vol"]
WALLET = ["gross_z", "whale_z", "wallets_z", "new_z", "imbalance"]
MIN_FLOW_USD = 500


def v1_by_quarter(shocks: pd.DataFrame) -> pd.DataFrame:
    s = shocks[shocks["abs_r_normal"] > 0].copy()
    s["ratio"] = s["r"].abs() / s["abs_r_normal"]
    s["quarter"] = quarter(s["ts"]).to_numpy()
    per = s.pivot_table(index=["quarter", "market_id"], columns="kind", values="ratio", aggfunc="mean").dropna()
    per["diff"] = per["mapped"] - per["placebo"]
    return per.groupby("quarter")["diff"].agg(["mean", "count"]).rename(columns={"count": "markets"}).reset_index()


def w3_rolling(hours: pd.DataFrame, seed: int):
    frame = _features(hours).dropna(subset=BASE + WALLET + ["shock_next"])
    frame["quarter"] = quarter(frame["ts"]).to_numpy()
    rows, scored = [], []
    for q in sorted(frame["quarter"].unique()):
        start = pd.Period(q).start_time.timestamp()
        train, test = frame[frame["ts"] < start - 3600], frame[frame["quarter"] == q]
        if len(train) < 5000 or test["shock_next"].sum() < 30:
            continue
        mean, std = train[BASE + WALLET].mean(), train[BASE + WALLET].std().replace(0, 1)
        z = lambda f, cols: ((f[cols] - mean[cols]) / std[cols]).to_numpy()
        y_train = train["shock_next"].to_numpy(float)
        b0 = _fit_logistic(z(train, BASE), y_train)
        b1 = _fit_logistic(z(train, BASE + WALLET), y_train)
        s0 = np.column_stack([np.ones(len(test)), z(test, BASE)]) @ b0
        s1 = np.column_stack([np.ones(len(test)), z(test, BASE + WALLET)]) @ b1
        y = test["shock_next"].to_numpy(float)
        rows.append({"quarter": q, "auc_price_only": _auc(s0, y), "auc_with_wallets": _auc(s1, y),
                     "gain": _auc(s1, y) - _auc(s0, y), "test_hours": int(len(test)), "jumps": int(y.sum())})
        scored.append(pd.DataFrame({"market_id": test["market_id"].to_numpy(), "y": y, "s0": s0, "s1": s1}))
    table = pd.DataFrame(rows)
    if not scored:
        return table, {"gain": np.nan, "low": np.nan, "high": np.nan}
    pooled = pd.concat(scored, ignore_index=True)
    # scores from different quarters' models are compared within the pooled set via ranks per quarter-free AUC
    keys = pooled["market_id"].unique()
    index = {k: np.nonzero(pooled["market_id"].to_numpy() == k)[0] for k in keys}
    rng = np.random.default_rng(seed)
    y, s0, s1 = pooled["y"].to_numpy(), pooled["s0"].to_numpy(), pooled["s1"].to_numpy()
    gains = []
    for _ in range(300):
        pick = np.concatenate([index[k] for k in rng.choice(keys, len(keys))])
        gains.append(_auc(s1[pick], y[pick]) - _auc(s0[pick], y[pick]))
    gains = np.array([g for g in gains if np.isfinite(g)])
    return table, {"gain": float(_auc(s1, y) - _auc(s0, y)), "low": float(np.quantile(gains, 0.025)),
                   "high": float(np.quantile(gains, 0.975))}


def w5_by_quarter(hours: pd.DataFrame) -> pd.DataFrame:
    h = hours.dropna(subset=["dp_next"]).copy()
    h["quarter"] = quarter(h["ts"]).to_numpy()
    rows = []
    for q, part in h.groupby("quarter"):
        out = {"quarter": q}
        for kind in ("whale", "retail"):
            use = part[part[f"f_{kind}"].abs() >= MIN_FLOW_USD]
            out[kind] = float((np.sign(use[f"f_{kind}"]) * use["dp_next"]).mean()) if len(use) else np.nan
            out[f"{kind}_markets"] = int(use["market_id"].nunique())
        rows.append(out)
    table = pd.DataFrame(rows)
    table["diff"] = table["whale"] - table["retail"]
    return table


def run(ctx: DailyContext) -> ExperimentResult:
    v1 = v1_by_quarter(ctx.watched["shocks"])
    v1_ok = v1[v1["markets"] >= 20]
    a = bool(len(v1_ok) and (v1_ok["mean"] > 0).mean() >= 2 / 3 and v1_ok.iloc[-1]["mean"] > 0)
    w3, pooled = w3_rolling(ctx.watched_hours, ctx.cfg.seed)
    b = bool(len(w3) and (w3["gain"] > 0).mean() >= 2 / 3 and pooled["low"] > 0)
    w5 = w5_by_quarter(ctx.watched_hours)
    w5_ok = w5[w5["whale_markets"] >= 20]
    c = bool(len(w5_ok) and (w5_ok["diff"] > 0).mean() >= 2 / 3)
    checks = {"a_v1_quarters": a, "b_w3_rolling": b, "c_w5_quarters": c}
    verdict = "pass" if all(checks.values()) else "fail"

    fig, ax = plots.figure(8, 3.4)
    ax.bar(v1_ok["quarter"], v1_ok["mean"], color=[plots.ACCENT if v > 0 else plots.MUTED for v in v1_ok["mean"]])
    ax.axhline(0, color=plots.INK, lw=1)
    ax.set_ylabel("related − unrelated |move| ratio")
    ax.set_title("V1 by quarter (watched hours, all candidates)")
    ax.tick_params(axis="x", rotation=30)
    latest = v1_ok.iloc[-1] if len(v1_ok) else None
    headline = (f"V1 positive in {(v1_ok['mean'] > 0).sum()} of {len(v1_ok)} quarters"
                + (f" (latest {latest['quarter']}: {latest['mean']:+.2f}×)" if latest is not None else "")
                + f"; W3 rolling gain positive in {(w3['gain'] > 0).sum() if len(w3) else 0} of {len(w3)} quarters, pooled "
                f"{pooled['gain']:+.3f} (CI {pooled['low']:+.3f} to {pooled['high']:+.3f}); W5 whale beats retail in "
                f"{(w5_ok['diff'] > 0).sum()} of {len(w5_ok)} quarters.")
    return ExperimentResult(
        id="d2", title="Stability over time", verdict=verdict, headline=headline,
        question="Do the effects keep holding quarter by quarter, including the most recent quarter?",
        metrics={"checks": checks, "w3_pooled": pooled, "v1_quarters": v1.to_dict("records"),
                 "w3_quarters": w3.to_dict("records"), "w5_quarters": w5.to_dict("records")},
        tables={"v1_quarters": v1, "w3_quarters": w3, "w5_quarters": w5}, figures={"v1_quarters": fig},
        notes=["W3 is rolling-origin: each quarter is scored by a model trained only on hours before it.",
               "Pass rule (pre-registered): V1 > 0 in >= 2/3 of quarters with >= 20 markets and in the latest; "
               "W3 gain > 0 in >= 2/3 of quarters and pooled CI > 0; W5 whale > retail in >= 2/3 of quarters."])
