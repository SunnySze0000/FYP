"""V3 · Do linked jumps predict bigger moves after controlling for the VIX? (docs/12_vix_control.md)"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
root, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

ctx = DailyContext(load_settings(root=root), "events")
J = jumps(ctx); J = J[~J.groups.str.split("|").map(lambda g: "crypto" in g)].copy(); J["glist"] = J.groups.str.split("|")
start = int(J.ts.min())
H = ctx.hourly.sort_values("end_ts")
vix = H[H.symbol == "^VIX"]; vt, vc = vix.end_ts.to_numpy("int64"), vix.close.to_numpy(float)
rows = []
for sym in sorted({x for v in ASSET_GROUPS.values() for x in v} - {"BTC-USD", "ETH-USD", "COIN", "MSTR", "^VIX", "VIXY"}):
    g = H[H.symbol == sym]
    if g.empty: continue
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    recent = pd.Series(y).shift(1).rolling(24, min_periods=12).mean().to_numpy()
    first = np.r_[True, np.diff(ends) != 3600]
    prev_end = np.r_[ends[0] - 3600, ends[:-1]]
    lo = np.where(first, prev_end, ends - 3600)
    lg = {k for k, v in ASSET_GROUPS.items() if sym in v and k != "us_politics"}
    lj = np.sort(J[J.glist.map(lambda x: bool(lg & set(x)))].ts.to_numpy())
    uj = np.sort(J[~J.glist.map(lambda x: bool(lg & set(x)))].ts.to_numpy())
    cnt = lambda a: np.searchsorted(a, ends, side="right") > np.searchsorted(a, lo, side="right")
    iv = np.searchsorted(vt, ends - 3600, side="right") - 1           # last VIX bar at or before the hour starts
    iv2 = np.searchsorted(vt, ends, side="right") - 1
    ok = (iv >= 0) & (iv2 >= 0)
    vix_lvl = np.where(ok, np.log(vc[np.maximum(iv, 0)]), np.nan)
    vix_chg = np.where(ok, np.abs(np.log(vc[np.maximum(iv2, 0)] / vc[np.maximum(iv, 0)])), np.nan)
    rows.append(pd.DataFrame({"sym": sym, "end": ends, "y": y, "linked": cnt(lj).astype(float), "unrelated": cnt(uj).astype(float),
                              "vix": vix_lvl, "vix_move": vix_chg, "recent": recent, "hod": hod, "first": first}))
D = pd.concat(rows)
D = D[(D.end - 3600 >= start) & (D.end <= J.ts.max())].replace([np.inf, -np.inf], np.nan).dropna()
D = D[D.y < D.y.quantile(0.999)]                                   # trim extreme outliers (0.1%)
D["day"] = D.end // 86400

def design(d, cols):
    fe = pd.get_dummies(d[["hod", "sym"]].astype(str), drop_first=True).astype(float)
    X = pd.concat([pd.Series(1.0, index=d.index, name="const"), d[cols], fe], axis=1)
    return X.to_numpy(float), list(X.columns)

def fit(d, cols, draws=1000, seed=7):
    X, names = design(d, cols); yv = d.y.to_numpy(float)
    beta = np.linalg.lstsq(X, yv, rcond=None)[0]
    days = d.day.to_numpy(); uniq, inv = np.unique(days, return_inverse=True)
    idx = [np.nonzero(inv == k)[0] for k in range(len(uniq))]
    rng = np.random.default_rng(seed); B = []
    for _ in range(draws):
        pick = np.concatenate([idx[k] for k in rng.integers(0, len(uniq), len(uniq))])
        B.append(np.linalg.lstsq(X[pick], yv[pick], rcond=None)[0])
    B = np.array(B); i_l, i_u = names.index("linked"), names.index("unrelated")
    res = {n: {"coef": float(beta[names.index(n)]), "low": float(np.quantile(B[:, names.index(n)], .025)),
               "high": float(np.quantile(B[:, names.index(n)], .975))} for n in cols}
    diff = B[:, i_l] - B[:, i_u]
    res["linked_minus_unrelated"] = {"coef": float(beta[i_l] - beta[i_u]), "low": float(np.quantile(diff, .025)), "high": float(np.quantile(diff, .975))}
    res["n"] = int(len(d)); res["linked_hours"] = int(d.linked.sum())
    return res

R = {"M0": fit(D, ["linked", "unrelated"]),
     "M1": fit(D, ["linked", "unrelated", "vix", "recent"]),
     "M2": fit(D, ["linked", "unrelated", "vix", "recent", "vix_move"]),
     "overnight_M1": fit(D[D["first"]], ["linked", "unrelated", "vix", "recent"])}
# how much of the linked effect does the VIX/recent-vol control remove?
m1 = R["M1"]
R["verdict"] = "pass" if (m1["linked"]["low"] > 0 and m1["linked_minus_unrelated"]["low"] > 0) else "fail"
json.dump(R, open(out / "vix_control.json", "w"), indent=1)
for k in ("M0", "M1", "M2", "overnight_M1"):
    v = R[k]; print(f"{k:13s} n={v['n']:6d} linked {v['linked']['coef']:+.3f} [{v['linked']['low']:+.3f},{v['linked']['high']:+.3f}]  "
                    f"unrelated {v['unrelated']['coef']:+.3f}  linked-unrel {v['linked_minus_unrelated']['coef']:+.3f} "
                    f"[{v['linked_minus_unrelated']['low']:+.3f},{v['linked_minus_unrelated']['high']:+.3f}]"
                    + (f"  vix {v['vix']['coef']:+.3f} recent {v['recent']['coef']:+.3f}" if 'vix' in v else "")
                    + (f"  vix_move {v['vix_move']['coef']:+.2f}" if 'vix_move' in v else ""))
print("verdict:", R["verdict"])
