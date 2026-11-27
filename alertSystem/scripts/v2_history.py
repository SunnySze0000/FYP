"""V2 · Full-history view: daily holding volatility vs daily count of linked event jumps, every holding."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

LINKED, OTHER, INK, MUTED, GRID = "#257de0", "#f47230", "#191919", "#666666", "#e6e6e6"
plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": "#bbbbbb", "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
ctx = DailyContext(load_settings(root=root), "events")
J = jumps(ctx)
J = J[~J["groups"].str.split("|").map(lambda g: "crypto" in g)].copy()
J["glist"] = J["groups"].str.split("|")
H = ctx.hourly.sort_values("end_ts")
CRYPTO = {"BTC-USD", "ETH-USD", "COIN", "MSTR"}

def daily(sym):
    g = H[H.symbol == sym]
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    day = pd.to_datetime(ends - 3600, unit="s").normalize()
    d = pd.DataFrame({"day": day, "y": y, "end": ends}).dropna()
    per = d.groupby("day").agg(vol=("y", "mean"), close=("end", "max"))
    per["open_from"] = per["close"].shift(1)                      # previous session close
    lg = {gname for gname, a in ASSET_GROUPS.items() if sym in a and gname != "us_politics"}
    lj = np.sort(J[J.glist.map(lambda gl: bool(lg & set(gl)))].ts.to_numpy())
    uj = np.sort(J[~J.glist.map(lambda gl: bool(lg & set(gl)))].ts.to_numpy())
    per = per.dropna()
    count = lambda arr: np.searchsorted(arr, per["close"].to_numpy(), side="right") - np.searchsorted(arr, per["open_from"].to_numpy(), side="right")
    per["linked"], per["unlinked"] = count(lj), count(uj)            # jumps since previous close, up to this close
    return per, sorted(lg)

assets = [a for a in sorted({x for v in ASSET_GROUPS.values() for x in v}) if a not in CRYPTO and a in set(H.symbol)]
stats, data = [], {}
for a in assets:
    per, lg = daily(a)
    if len(per) < 100 or not lg: continue
    data[a] = (per, lg)
    hi = per[per.linked >= 3].vol.mean(); lo = per[per.linked == 0].vol.mean()
    stats.append({"holding": a, "topics": ", ".join(lg), "days": len(per),
                  "corr_linked": per.vol.corr(per.linked, method="spearman"),
                  "corr_unlinked": per.vol.corr(per.unlinked, method="spearman"),
                  "vol_days_3plus_linked": hi, "vol_days_no_linked": lo})
S = pd.DataFrame(stats).sort_values("corr_linked")
S.to_csv(out / "history_correlations.csv", index=False)

# ---- Chart A: full history, 8 holdings (volatility line on top, linked/unlinked jumps per day below)
picks = [a for a in ["SPY", "QQQ", "TLT", "UUP", "USO", "GLD", "FXI", "ITA"] if a in data]
fig, axes = plt.subplots(len(picks) * 2, 1, figsize=(13, 2.35 * len(picks)), sharex=True,
                         gridspec_kw={"height_ratios": [2.2, 1] * len(picks), "hspace": 0.55})
for k, a in enumerate(picks):
    per, lg = data[a]
    ax, jx = axes[2 * k], axes[2 * k + 1]
    v = per.vol.rolling(5, min_periods=1).mean()
    ax.plot(per.index, v, color=INK, lw=1.2); ax.axhline(1, color="#aaaaaa", lw=0.8, ls=(0, (3, 3)))
    ax.set_ylim(0, max(3, np.nanpercentile(v, 99.5))); ax.grid(axis="y", color=GRID, lw=0.7)
    row = S.set_index("holding").loc[a]
    ax.set_title(f"{a}  ·  linked topics: {', '.join(lg)}  ·  daily correlation with linked jumps ρ = {row.corr_linked:+.2f}"
                 f"  (unrelated jumps ρ = {row.corr_unlinked:+.2f})", loc="left", fontsize=10, color=INK)
    ax.set_ylabel("volatility\n(5-day avg)")
    jx.bar(per.index, per.linked.clip(upper=15), width=1.0, color=LINKED)
    jx.bar(per.index, -per.unlinked.clip(upper=15), width=1.0, color=OTHER)
    jx.axhline(0, color="#bbbbbb", lw=0.6); jx.set_ylabel("jumps/day"); jx.set_ylim(-16, 16)
    jx.set_yticks([-10, 0, 10]); jx.set_yticklabels(["10", "0", "10"])
axes[-1].set_xlim(pd.to_datetime(J.ts.min(), unit="s"), pd.to_datetime(J.ts.max(), unit="s"))
axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2)); axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
fig.legend(handles=[Line2D([0], [0], color=INK, lw=1.4, label="holding volatility (1 = normal, 5-day average)"),
                    Patch(color=LINKED, label="linked event jumps that day (up)"),
                    Patch(color=OTHER, label="unrelated event jumps that day (down, for comparison)")],
           loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.905))
fig.savefig(out / "A_full_history.png", dpi=130, bbox_inches="tight"); plt.close(fig)

# ---- Chart B: correlation for every holding, linked vs unrelated jumps
fig, ax = plt.subplots(figsize=(9, 0.32 * len(S) + 1.5))
yv = np.arange(len(S))
ax.barh(yv + 0.2, S.corr_linked, height=0.38, color=LINKED, label="linked event jumps")
ax.barh(yv - 0.2, S.corr_unlinked, height=0.38, color=OTHER, label="unrelated event jumps")
ax.set_yticks(yv); ax.set_yticklabels(S.holding); ax.axvline(0, color=INK, lw=0.8); ax.grid(axis="x", color=GRID)
ax.set_xlabel("Spearman correlation: daily volatility vs number of jumps that day")
ax.set_title(f"Across the whole history: linked jumps track volatility more than unrelated jumps in "
             f"{(S.corr_linked > S.corr_unlinked).sum()} of {len(S)} holdings", loc="left", fontsize=10.5, color=INK)
ax.legend(frameon=False, loc="lower right")
fig.tight_layout(); fig.savefig(out / "B_correlation_by_holding.png", dpi=140); plt.close(fig)

# ---- Chart C: pooled, volatility by number of linked jumps that day
P = pd.concat([d.assign(holding=a) for a, (d, _) in data.items()])
P["bucket"] = pd.cut(P.linked, [-1, 0, 1, 2, 4, 9, 1000], labels=["0", "1", "2", "3–4", "5–9", "10+"])
Q = P.groupby("bucket", observed=True).vol.agg(["mean", "count"])
P["ub"] = pd.cut(P.unlinked, [-1, 0, 1, 2, 4, 9, 1000], labels=["0", "1", "2", "3–4", "5–9", "10+"])
U = P.groupby("ub", observed=True).vol.agg(["mean", "count"])
fig, ax = plt.subplots(figsize=(8, 4))
x = np.arange(len(Q))
ax.bar(x - 0.2, Q["mean"], width=0.38, color=LINKED, label="by linked jumps that day")
ax.bar(x + 0.2, U["mean"].reindex(Q.index), width=0.38, color=OTHER, label="by unrelated jumps that day")
for i, (m, n) in enumerate(zip(Q["mean"], Q["count"])): ax.text(i - 0.2, m + 0.02, f"{m:.2f}\nn={n}", ha="center", fontsize=8, color=INK)
ax.axhline(1, color=INK, lw=0.8); ax.set_xticks(x); ax.set_xticklabels(Q.index); ax.grid(axis="y", color=GRID)
ax.set_xlabel("number of event jumps that day"); ax.set_ylabel("holding volatility that day (1 = normal)")
ax.set_title(f"All {len(data)} holdings, all days: the more linked jumps, the more the holding moves", loc="left", fontsize=10.5, color=INK)
ax.legend(frameon=False, loc="upper left")
fig.tight_layout(); fig.savefig(out / "C_volatility_by_jump_count.png", dpi=140); plt.close(fig)
pd.concat([Q.add_prefix("linked_"), U.add_prefix("unrelated_")], axis=1).to_csv(out / "C_volatility_by_jump_count.csv")
print(S.round(2).to_string(index=False)); print(Q.round(2).to_string()); print(U.round(2).to_string())
