"""V3 · same-hour test with sector volatility gauges as controls (docs/15_sector_vol.md)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
root, out, gauges_csv = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

GAUGE_OF = {"USO": "^OVX", "XLE": "^OVX", "GLD": "^GVZ", "TLT": "^MOVE", "IEF": "^MOVE", "SHY": "^MOVE",
            "FXI": "^VXFXI", "KWEB": "^VXFXI", "EEM": "^VXFXI", "QQQ": "^VXN", "NVDA": "^VXN", "SMH": "^VXN", "MSFT": "^VXN"}
G = pd.read_csv(gauges_csv).sort_values("end_ts")
counts = G.groupby("symbol").size().to_dict()
usable = {g for g, n in counts.items() if n >= 1000}
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
    lg = {k for k, v in ASSET_GROUPS.items() if sym in v and k != "us_politics"}
    lj = np.sort(J[J.glist.map(lambda x: bool(lg & set(x)))].ts.to_numpy())
    gname = GAUGE_OF.get(sym); lvl = chg = np.full(len(ends), np.nan)
    if gname in usable:
        gg = G[G.symbol == gname]; gt, gc = gg.end_ts.to_numpy("int64"), gg.close.to_numpy(float)
        i0 = np.searchsorted(gt, lo, side="right") - 1; i1 = np.searchsorted(gt, ends, side="right") - 1
        ok = (i0 >= 0) & (i1 >= 0) & (ends - gt[np.maximum(i1, 0)] < 6 * 3600)
        lvl = np.where(ok, np.log(gc[np.maximum(i0, 0)]), np.nan)
        chg = np.where(ok, np.abs(np.log(gc[np.maximum(i1, 0)] / gc[np.maximum(i0, 0)])), np.nan)
    rows.append(pd.DataFrame({"sym": sym, "end": ends, "first": first, "y": y, "recent": recent, "g_lvl": lvl, "g_chg": chg,
                              "linked": (count(lj, ends, lo) > 0).astype(float), "n_any": count(alljt, ends, lo)}))
D = pd.concat(rows)
D = D[(D.end - 3600 >= start) & (D.end <= stop)].replace([np.inf, -np.inf], np.nan).dropna()
D = D[D.y < D.y.quantile(0.999)]
D["slot"] = (D.end // 1800).astype(int)
D = D[D.groupby("slot").n_any.transform("max") > 0]
D = D[D.groupby("slot").sym.transform("count") >= 3]          # fewer holdings have a gauge than in doc 13
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
    B = np.array(B)
    return {c: {"coef": float(beta[i]), "low": float(np.quantile(B[:, i], .025)), "high": float(np.quantile(B[:, i], .975))}
            for i, c in enumerate(xcols)} | {"n": int(len(d)), "linked_rows": int(d.linked.sum())}
R = {"gauge_bars": counts, "gauges_used": sorted(usable), "holdings": sorted(D.sym.unique()),
     "without_gauge": fit(D, ["linked", "recent"]), "with_gauge": fit(D, ["linked", "recent", "g_lvl", "g_chg"]),
     "overnight_with_gauge": fit(D[D["first"]], ["linked", "recent", "g_lvl", "g_chg"]),
     "intraday_with_gauge": fit(D[~D["first"]], ["linked", "recent", "g_lvl", "g_chg"])}
R["rule1"] = "pass" if R["with_gauge"]["linked"]["low"] > 0 else "fail"
R["rule2_overnight"] = "pass" if R["overnight_with_gauge"]["linked"]["low"] > 0 else "fail"
json.dump(R, open(out / "sector_vol.json", "w"), indent=1)
print("gauges used:", R["gauges_used"], "holdings:", R["holdings"])
for k in ("without_gauge", "with_gauge", "overnight_with_gauge", "intraday_with_gauge"):
    v = R[k]["linked"]; print(f"{k:22s} n={R[k]['n']:6d} linked {v['coef']:+.3f} [{v['low']:+.3f},{v['high']:+.3f}]")
for c in ("g_lvl", "g_chg"):
    v = R["with_gauge"][c]; print(f"gauge {c:6s} {v['coef']:+.3f} [{v['low']:+.3f},{v['high']:+.3f}]")
print("rule1:", R["rule1"], "rule2 overnight:", R["rule2_overnight"])
