"""V4 · Same-hour test on the cleanest links only (docs/14_clean_links.md)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
root, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

CLEAN = {"rates": {"TLT", "IEF", "SHY"}, "macro": set(), "trade_china": {"FXI", "KWEB"},
         "energy_mideast": {"USO", "XLE"}, "war_europe": {"ITA", "EZU"}, "ai_tech": {"NVDA", "SMH"}}
ctx = DailyContext(load_settings(root=root), "events")
J = jumps(ctx, gap_h=1); J = J[~J.groups.str.split("|").map(lambda g: "crypto" in g)].copy(); J["glist"] = J.groups.str.split("|")
start, stop = int(J.ts.min()), int(J.ts.max())
H = ctx.hourly.sort_values("end_ts"); alljt = np.sort(J.ts.to_numpy())
def count(ts, ends, lo): return np.searchsorted(ts, ends, side="right") - np.searchsorted(ts, lo, side="right")
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
    groups = {k for k, v in ASSET_GROUPS.items() if sym in v and k not in ("us_politics", "crypto")}
    cg = {k for k in groups if sym in CLEAN.get(k, set())}; lg = groups - cg
    cj = np.sort(J[J.glist.map(lambda x: bool(cg & set(x)))].ts.to_numpy())
    lj = np.sort(J[J.glist.map(lambda x: bool(lg & set(x)))].ts.to_numpy())
    rows.append(pd.DataFrame({"sym": sym, "end": ends, "first": first, "y": y, "recent": recent,
                              "n_clean": count(cj, ends, lo), "n_loose": count(lj, ends, lo), "n_any": count(alljt, ends, lo)}))
D = pd.concat(rows)
D = D[(D.end - 3600 >= start) & (D.end <= stop)].replace([np.inf, -np.inf], np.nan).dropna()
D = D[D.y < D.y.quantile(0.999)]
D["slot"] = (D.end // 1800).astype(int)
D = D[D.groupby("slot").n_any.transform("max") > 0]
D = D[D.groupby("slot").sym.transform("count") >= 5]
D["clean"] = (D.n_clean > 0).astype(float); D["loose"] = ((D.n_clean == 0) & (D.n_loose > 0)).astype(float)
D["day"] = D.end // 86400

def demean(d, cols, keys=("slot", "sym"), it=8):
    X = d[cols].copy()
    for _ in range(it):
        for k in keys: X = X - X.groupby(d[k]).transform("mean")
    return X
def fit(d, xcols, draws=1000, seed=7):
    Z = demean(d, ["y"] + xcols); yv, X = Z["y"].to_numpy(), Z[xcols].to_numpy()
    beta = np.linalg.lstsq(X, yv, rcond=None)[0]
    uniq, inv = np.unique(d.day.to_numpy(), return_inverse=True)
    idx = [np.nonzero(inv == k)[0] for k in range(len(uniq))]
    rng = np.random.default_rng(seed); B = []
    for _ in range(draws):
        p = np.concatenate([idx[k] for k in rng.integers(0, len(uniq), len(uniq))])
        B.append(np.linalg.lstsq(X[p], yv[p], rcond=None)[0])
    B = np.array(B); diff = B[:, 0] - B[:, 1]
    res = {c: {"coef": float(beta[i]), "low": float(np.quantile(B[:, i], .025)), "high": float(np.quantile(B[:, i], .975))} for i, c in enumerate(xcols)}
    res["clean_minus_loose"] = {"coef": float(beta[0] - beta[1]), "low": float(np.quantile(diff, .025)), "high": float(np.quantile(diff, .975))}
    return res | {"n": int(len(d)), "clean_rows": int(d.clean.sum()), "loose_rows": int(d.loose.sum())}
X = ["clean", "loose", "recent"]
R = {"all": fit(D, X), "overnight": fit(D[D["first"]], X), "intraday": fit(D[~D["first"]], X)}
R["per_symbol_clean_rows"] = D[D.clean > 0].groupby("sym").size().to_dict()
R["rule1_clean_gt0"] = "pass" if R["all"]["clean"]["low"] > 0 else "fail"
R["rule2_clean_gt_loose"] = "pass" if R["all"]["clean_minus_loose"]["low"] > 0 else "fail"
json.dump(R, open(out / "clean_links.json", "w"), indent=1)
for k in ("all", "overnight", "intraday"):
    r = R[k]; print(f"{k:9s} n={r['n']:6d} clean={r['clean_rows']:5d} loose={r['loose_rows']:5d}")
    for c in ("clean", "loose", "clean_minus_loose"):
        v = r[c]; print(f"   {c:18s} {v['coef']:+.3f} [{v['low']:+.3f},{v['high']:+.3f}]")
print("rule1:", R["rule1_clean_gt0"], " rule2:", R["rule2_clean_gt_loose"]); print(R["per_symbol_clean_rows"])
