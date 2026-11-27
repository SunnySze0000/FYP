"""V2 · Charts: holding volatility over time with linked event jumps marked (docs/10)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

LINKED, OTHER, INK, MUTED, GRID = "#257de0", "#f47230", "#191919", "#666666", "#e6e6e6"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#bbbbbb", "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
ctx = DailyContext(load_settings(root=root), "events")
J = jumps(ctx)
J = J[~J["groups"].str.split("|").map(lambda g: "crypto" in g)]
J["glist"] = J["groups"].str.split("|")
H = ctx.hourly.sort_values("end_ts")

def vol_series(sym):
    g = H[H.symbol == sym]
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); ok = np.r_[False, np.diff(ends) == 3600]
    r = np.where(ok, r, np.nan); hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    return pd.Series(y, index=pd.to_datetime(ends, unit="s"))

def linked_groups(sym):
    return {g for g, a in ASSET_GROUPS.items() if sym in a and g != "us_politics"}

# ---------------- 1. timelines: one bar per trading hour, coloured by what happened in Polymarket
picks = ["USO", "TLT", "SPY", "FXI"]
fig, axes = plt.subplots(len(picks), 1, figsize=(12, 3.0 * len(picks)))
summary = []
for ax, sym in zip(axes, picks):
    g = H[H.symbol == sym]
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    prev_end = np.r_[ends[0] - 3600, ends[:-1]]
    lg = linked_groups(sym)
    jt = np.sort(J[J.glist.map(lambda gl: bool(lg & set(gl)))].ts.to_numpy())
    ut = np.sort(J[~J.glist.map(lambda gl: bool(lg & set(gl)))].ts.to_numpy())
    # a bar "has" a jump if a jump hour ended inside the bar or in the closed gap before it (overnight)
    has = lambda arr: np.searchsorted(arr, ends, side="right") > np.searchsorted(arr, prev_end, side="right")
    kind = np.where(has(jt), 2, np.where(has(ut), 1, 0))
    ok = np.isfinite(y)
    summary.append({"holding": sym, "linked": np.nanmean(y[ok & (kind == 2)]), "unlinked_only": np.nanmean(y[ok & (kind == 1)]),
                    "no_jump": np.nanmean(y[ok & (kind == 0)]), "linked_bars": int((ok & (kind == 2)).sum())})
    # window: 15 trading days with the most linked-jump bars
    day = pd.to_datetime(ends, unit="s").normalize()
    days = pd.Series(day).unique()
    best, bi = -1, 0
    for i in range(0, len(days) - 15):
        m = (day >= days[i]) & (day < days[i + 15])
        n = int((kind[m] == 2).sum())
        if n > best: best, bi = n, i
    m = (day >= days[bi]) & (day < days[bi + 15]) & ok
    yy, kk, dd = y[m], kind[m], day[m]
    x = np.arange(len(yy))
    cols = np.array(["#c4c4c4", OTHER, LINKED])[kk]
    ax.bar(x, np.minimum(yy, 8), width=0.8, color=cols)
    ax.axhline(1, color=INK, lw=0.8, ls=(0, (3, 3)))
    starts = np.r_[0, np.nonzero(np.diff(dd.astype("int64")) != 0)[0] + 1]
    for st in starts[1:]: ax.axvline(st - 0.5, color="#dddddd", lw=0.8)
    ax.set_xticks(starts[::2]); ax.set_xticklabels([pd.Timestamp(dd[i]).strftime("%d %b %Y") if j == 0 else pd.Timestamp(dd[i]).strftime("%d %b") for j, i in enumerate(starts[::2])], fontsize=8.5)
    ax.set_xlim(-1, len(x)); ax.set_ylabel("volatility\n(1 = normal)"); ax.grid(axis="y", color=GRID, lw=0.8)
    s_ = summary[-1]
    ax.set_title(f"{sym}  ·  bars in hours with a linked jump average {s_['linked']:.1f}× normal, other hours {s_['no_jump']:.1f}×",
                 loc="left", fontsize=11, color=INK)
from matplotlib.patches import Patch
fig.legend(handles=[Patch(color=LINKED, label="a linked event jumped in this hour (or overnight before this open)"),
                    Patch(color=OTHER, label="only unrelated events jumped"), Patch(color="#c4c4c4", label="no event jump")],
           loc="upper center", ncol=3, frameon=False, fontsize=9.5)
fig.tight_layout(rect=(0, 0, 1, 0.965)); fig.savefig(out / "1_timelines.png", dpi=150); plt.close(fig)
pd.DataFrame(summary).to_csv(out / "1_timeline_summary.csv", index=False)
print(pd.DataFrame(summary).round(2).to_string())

# ---------------- 2. event-time profile (from S1, without crypto)
p = pd.read_csv(root / "results/20261127-1400_sequence/s_profile_nocrypto.csv") if (root / "results/20261127-1400_sequence/s_profile_nocrypto.csv").exists() else pd.read_csv("/tmp/s_profile_nocrypto.csv")
fig, ax = plt.subplots(figsize=(8, 4))
ax.axhline(1, color="#aaaaaa", lw=1, ls=(0, (3, 3))); ax.axvline(0, color="#cccccc", lw=8, alpha=0.5)
ax.plot(p.hour, p.linked, color=LINKED, lw=2, marker="o", ms=8, label="linked holdings")
ax.plot(p.hour, p.placebo, color=OTHER, lw=2, marker="s", ms=8, label="unrelated assets, same jumps")
for h, v in zip(p.hour, p.linked): ax.annotate(f"{v:.2f}", (h, v), textcoords="offset points", xytext=(0, 9), ha="center", color=INK, fontsize=9)
ax.set_xticks(p.hour); ax.set_xticklabels([f"{h:+d}h" if h else "jump hour" for h in p.hour])
ax.set_ylabel("volatility (1 = normal)"); ax.grid(axis="y", color=GRID); ax.legend(frameon=False, loc="upper right")
ax.set_title("Average volatility in the hours around a linked event jump (US trading hours, 227 bets)", loc="left", fontsize=11, color=INK)
fig.tight_layout(); fig.savefig(out / "2_event_time_profile.png", dpi=150); plt.close(fig)

# ---------------- 3. per-holding: volatility in jump hours vs normal (V1)
model = json.loads((root / "data/app/model.json").read_text())
a = pd.DataFrame(model["assets"]); a["ratio"] = a.shock_abs_r / a.normal_abs_r
a = a[~a.asset.isin(["BTC-USD", "ETH-USD", "COIN", "MSTR"])].sort_values("ratio")
fig, ax = plt.subplots(figsize=(8, 6))
ax.barh(a.asset, a.ratio, color=LINKED, height=0.6); ax.axvline(1, color=INK, lw=1)
for i, (r, n) in enumerate(zip(a.ratio, a.shocks)): ax.text(r + 0.03, i, f"{r:.1f}×  ({n} jumps)", va="center", fontsize=8.5, color=MUTED)
ax.set_xlabel("volatility in linked-jump hours ÷ normal hours"); ax.grid(axis="x", color=GRID)
ax.set_title("How much more each holding moves in hours when a linked event jumps", loc="left", fontsize=11, color=INK)
fig.tight_layout(); fig.savefig(out / "3_per_holding_ratio.png", dpi=150); plt.close(fig)

# ---------------- 4. overnight jumps -> next open (S2)
s2 = json.loads(Path("/tmp/s_metrics.json").read_text())["s2"] if Path("/tmp/s_metrics.json").exists() else None
rows = []
for sym in sorted({x for v in ASSET_GROUPS.values() for x in v} - {"BTC-USD", "ETH-USD"}):
    g = H[H.symbol == sym]
    if g.empty: continue
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    first = np.r_[True, np.diff(ends) != 3600]
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); norm = np.nanmean(np.where(first, r, np.nan))
    lg = linked_groups(sym)
    jt = np.sort(J[J.glist.map(lambda gl: bool(lg & set(gl)))].ts.to_numpy())
    ut = np.sort(J[~J.glist.map(lambda gl: bool(lg & set(gl)))].ts.to_numpy())
    for i in np.nonzero(first)[0][1:]:
        lo, hi = ends[i - 1], ends[i] - 3600
        hasl = np.searchsorted(jt, hi, side="right") > np.searchsorted(jt, lo + 3600, side="left")
        hasu = np.searchsorted(ut, hi, side="right") > np.searchsorted(ut, lo + 3600, side="left")
        rows.append({"sym": sym, "y": r[i] / norm, "kind": "linked jump overnight" if hasl else ("only unlinked jumps" if hasu else "no jump")})
O = pd.DataFrame(rows).dropna()
m = O.groupby("kind")["y"].agg(["mean", "count"]).reindex(["no jump", "only unlinked jumps", "linked jump overnight"])
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.bar(m.index, m["mean"], color=["#999999", OTHER, LINKED], width=0.55)
ax.axhline(1, color=INK, lw=1)
for i, (v, n) in enumerate(zip(m["mean"], m["count"])): ax.text(i, v + 0.02, f"{v:.2f}  (n={n})", ha="center", color=INK, fontsize=9)
ax.set_ylabel("first-hour move at the open\n(1 = typical open)"); ax.grid(axis="y", color=GRID)
ax.set_title("Next US open after a night with / without a linked event jump", loc="left", fontsize=11, color=INK)
fig.tight_layout(); fig.savefig(out / "4_overnight_next_open.png", dpi=150); plt.close(fig)
m.to_csv(out / "4_overnight_next_open.csv")
print(m.round(3).to_string()); print(a[["asset", "ratio", "shocks"]].round(2).tail(5).to_string())
