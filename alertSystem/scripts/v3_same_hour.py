"""V3b · Same-hour comparison across holdings (docs/13_same_hour_test.md)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
root, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

ctx = DailyContext(load_settings(root=root), "events")
J = jumps(ctx, gap_h=1); J = J[~J.groups.str.split("|").map(lambda g: "crypto" in g)].copy(); J["glist"] = J.groups.str.split("|")
start, stop = int(J.ts.min()), int(J.ts.max())
H = ctx.hourly.sort_values("end_ts")
alljt = np.sort(J.ts.to_numpy())
rows = []
for sym in sorted({x for v in ASSET_GROUPS.values() for x in v} - {"BTC-USD", "ETH-USD", "COIN", "MSTR", "^VIX", "VIXY"}):
    g = H[H.symbol == sym]
    if g.empty: continue
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    recent = pd.Series(y).shift(1).rolling(24, min_periods=12).mean().to_numpy()
    first = np.r_[True, np.diff(ends) != 3600]
    lo = np.where(first, np.r_[ends[0] - 3600, ends[:-1]], ends - 3600)
    lg = {k for k, v in ASSET_GROUPS.items() if sym in v and k != "us_politics"}
    lj = np.sort(J[J.glist.map(lambda x: bool(lg & set(x)))].ts.to_numpy())
    n_l = np.searchsorted(lj, ends, side="right") - np.searchsorted(lj, lo, side="right")
    n_any = np.searchsorted(alljt, ends, side="right") - np.searchsorted(alljt, lo, side="right")
    rows.append(pd.DataFrame({"sym": sym, "end": ends, "first": first, "y": y, "recent": recent, "n_linked": n_l, "n_any": n_any}))
D = pd.concat(rows)
D = D[(D.end - 3600 >= start) & (D.end <= stop)].replace([np.inf, -np.inf], np.nan).dropna()
D = D[D.y < D.y.quantile(0.999)]
D["slot"] = (D.end // 1800).astype(int)      # same clock half-hour = same moment (stock bars end :30, others :00)
D = D[D.groupby("slot").n_any.transform("max") > 0]                 # hours with at least one bet jump
D = D[D.groupby("slot").sym.transform("count") >= 5]                # need several holdings to compare
D["linked"] = (D.n_linked > 0).astype(float); D["one"] = (D.n_linked == 1).astype(float); D["twoplus"] = (D.n_linked >= 2).astype(float)
D["day"] = D.end // 86400

def demean(d, cols, keys=("slot", "sym"), it=8):
    X = d[cols].copy()
    for _ in range(it):
        for k in keys:
            X = X - X.groupby(d[k]).transform("mean")
    return X

def fit(d, xcols, draws=1000, seed=7):
    Z = demean(d, ["y"] + xcols)
    yv, X = Z["y"].to_numpy(), Z[xcols].to_numpy()
    beta = np.linalg.lstsq(X, yv, rcond=None)[0]
    uniq, inv = np.unique(d.day.to_numpy(), return_inverse=True)
    idx = [np.nonzero(inv == k)[0] for k in range(len(uniq))]
    rng = np.random.default_rng(seed); B = []
    for _ in range(draws):
        p = np.concatenate([idx[k] for k in rng.integers(0, len(uniq), len(uniq))])
        B.append(np.linalg.lstsq(X[p], yv[p], rcond=None)[0])
    B = np.array(B)
    return {c: {"coef": float(beta[i]), "low": float(np.quantile(B[:, i], .025)), "high": float(np.quantile(B[:, i], .975))} for i, c in enumerate(xcols)} | {"n": int(len(d))}

R = {"a_linked": fit(D, ["linked", "recent"]), "b_count": fit(D, ["one", "twoplus", "recent"]),
     "a_linked_overnight": fit(D[D["first"]], ["linked", "recent"]), "a_linked_intraday": fit(D[~D["first"]], ["linked", "recent"])}
R["mean_y_in_these_hours"] = float(D.y.mean()); R["linked_rows"] = int(D.linked.sum()); R["slots"] = int(D.slot.nunique())
R["verdict"] = "pass" if R["a_linked"]["linked"]["low"] > 0 else "fail"
json.dump(R, open(out / "same_hour.json", "w"), indent=1)
for k in ("a_linked", "a_linked_overnight", "a_linked_intraday"):
    v = R[k]["linked"]; print(f"{k:20s} n={R[k]['n']:6d} linked {v['coef']:+.3f} [{v['low']:+.3f},{v['high']:+.3f}]")
for c in ("one", "twoplus"):
    v = R["b_count"][c]; print(f"count {c:8s} {v['coef']:+.3f} [{v['low']:+.3f},{v['high']:+.3f}]")
print("hours compared:", R["slots"], "linked holding-hours:", R["linked_rows"], "mean outcome:", round(R["mean_y_in_these_hours"], 2), "verdict:", R["verdict"])
