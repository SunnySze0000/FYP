"""V2 · Real days drawn like the illustrative diagram (docs/11): linked bet probability on top, the holding's
hourly move size (× normal for that hour of day) below, US Eastern time."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

root, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import load_settings, ASSET_GROUPS
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.s_sequence import jumps

BLUE, ORANGE, GREY, INK, MUTED = "#2a78d6", "#eb6834", "#b4b2a9", "#191919", "#666666"
plt.rcParams.update({"font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#bbbbbb",
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": MUTED})
ctx = DailyContext(load_settings(root=root), "events")
J = jumps(ctx)
J = J[~J.groups.str.split("|").map(lambda g: "crypto" in g)].copy()
J["glist"] = J.groups.str.split("|")
q = ctx.all_markets.set_index("market_id")["question"]
P = ctx.all_prices.sort_values("ts")
H = ctx.hourly.sort_values("end_ts")
ET = "America/New_York"

cands, base = [], []
for sym in ["SPY", "QQQ", "TLT", "USO", "GLD", "XLE", "FXI", "KWEB", "UUP", "ITA", "XLF", "IEF"]:
    g = H[H.symbol == sym]
    ends, c = g.end_ts.to_numpy("int64"), g.close.to_numpy(float)
    r = np.abs(np.r_[np.nan, np.diff(np.log(c))]); hod = (ends // 3600) % 24
    y = r / pd.Series(r).groupby(hod).transform("mean").to_numpy()
    lg = {k for k, v in ASSET_GROUPS.items() if sym in v and k != "us_politics"}
    lj = J[J.glist.map(lambda x: bool(lg & set(x)))]
    uj = J[~J.glist.map(lambda x: bool(lg & set(x)))]
    first = np.r_[True, np.diff(ends) != 3600]
    for i in np.nonzero(first)[0][1:]:
        j_end0 = i
        while j_end0 + 1 < len(ends) and not first[j_end0 + 1]: j_end0 += 1
        anyj = lj[(lj.ts > ends[i - 1] + 3600) & (lj.ts <= ends[j_end0])]
        if anyj.empty and j_end0 - i >= 4 and not np.isnan(y[i]):
            base.append({"sym": sym, "open_y": y[i], "around": np.nanmax(y[i + 2:i + 5])})
        j_end = i
        while j_end + 1 < len(ends) and not first[j_end + 1]: j_end += 1
        prev_close, open_end, close = ends[i - 1], ends[i], ends[j_end]
        night = lj[(lj.ts > prev_close + 3600) & (lj.ts <= open_end - 3600)]
        day = lj[(lj.ts > open_end) & (lj.ts <= close)]
        if night.empty or day.empty or np.isnan(y[i]): continue
        # intraday: max of the bar before, during and after the jump
        k = np.searchsorted(ends[i:j_end + 1], day.ts.iloc[0]) + i
        around = np.nanmax(y[max(i + 1, k - 1): min(j_end, k + 1) + 1]) if k <= j_end else np.nan
        cands.append({"sym": sym, "i": i, "j": j_end, "open_y": y[i], "around": around,
                      "score": min(y[i], 3) + min(around, 4), "night": night, "day": day, "uj": uj, "ends": ends, "y": y})
C = sorted(cands, key=lambda d: -d["score"])
B = pd.DataFrame(base)
cd = pd.DataFrame([{"open_y": c["open_y"], "around": c["around"]} for c in cands])
looks = (cd.open_y > 1) & (cd.around > 1.5)
blooks = (B.open_y > 1) & (B.around > 1.5)
counts = pd.DataFrame([
    {"days": "overnight + intraday linked jump", "n": len(cd), "open_bigger_than_normal": (cd.open_y > 1).mean(),
     "move_over_1.5x_near_intraday_jump": (cd.around > 1.5).mean(), "both (looks like the diagram)": looks.mean(), "count_both": int(looks.sum())},
    {"days": "no linked jump at all (comparison)", "n": len(B), "open_bigger_than_normal": (B.open_y > 1).mean(),
     "move_over_1.5x_near_intraday_jump": (B.around > 1.5).mean(), "both (looks like the diagram)": blooks.mean(), "count_both": int(blooks.sum())}])
counts.to_csv(out / "pattern_counts.csv", index=False)
print(counts.round(3).to_string(index=False))
chosen, seen = [], set()
for d in C:
    key = (d["sym"], pd.Timestamp(d["ends"][d["i"]], unit="s").date())
    if d["sym"] in seen or key in seen: continue
    chosen.append(d); seen.add(d["sym"]); seen.add(key)
    if len(chosen) == 4: break
print("candidate days:", len(cands), "| share with bigger-than-normal open:", round(np.mean([c["open_y"] > 1 for c in cands]), 2),
      "| share with intraday bars >1.5x around jump:", round(np.nanmean([c["around"] > 1.5 for c in cands]), 2))

def draw(d, path):
    ends, y = d["ends"], d["y"]
    t_open = pd.Timestamp(ends[d["i"]] - 3600, unit="s", tz="UTC").tz_convert(ET)
    day0 = t_open.normalize(); t0 = day0.timestamp() - 6 * 3600; t1 = day0.timestamp() + 24 * 3600
    toh = lambda ts: (ts - day0.timestamp()) / 3600
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [1, 1.25], "hspace": 0.25})
    o, cl = toh(ends[d["i"]] - 3600), toh(ends[d["j"]])
    for ax in (a1, a2):
        ax.axvspan(o, cl, color="#888780", alpha=0.10, lw=0)
    allj = pd.concat([d["night"], d["day"]])
    styles = ["-", (0, (4, 2)), (0, (1, 2))]
    for k, mid in enumerate(allj.market_id.unique()[:3]):
        s = P[(P.market_id == mid) & (P.ts >= t0) & (P.ts <= t1)]
        a1.plot(toh(s.ts.to_numpy()), s.yes_price * 100, color=BLUE, lw=2 if k == 0 else 1.4, ls=styles[k],
                label=(q.get(mid, mid)[:70]))
        for _, jrow in allj[allj.market_id == mid].iterrows():
            pv = s[s.ts <= jrow.ts].yes_price
            if len(pv):
                a1.plot(toh(jrow.ts), pv.iloc[-1] * 100, "o", ms=9, color=BLUE, mec="white", mew=2, zorder=5)
                a1.annotate(f"{jrow.dp * 100:+.0f} pts", (toh(jrow.ts), pv.iloc[-1] * 100), textcoords="offset points",
                            xytext=(0, 10), ha="center", fontsize=8.5, color=INK)
    uj = d["uj"][(d["uj"].ts > t0) & (d["uj"].ts <= t1)]
    for ts in uj.ts: a1.plot([toh(ts) - 0.5] * 2, [2, 12], color=ORANGE, lw=2.5)
    a1.set_ylabel("chance of YES (%)"); a1.set_ylim(0, 100); a1.legend(frameon=False, fontsize=8.5, loc="upper left")
    a1.set_title(f"{d['sym']} on {t_open:%a %d %b %Y}: linked Polymarket bets (top) and {d['sym']}'s hourly move size (bottom)",
                 loc="left", fontsize=10.5, color=INK)
    jt = np.sort(pd.concat([d["night"], d["day"]]).ts.to_numpy())
    for b in range(d["i"], d["j"] + 1):
        x0 = toh(ends[b] - 3600)
        prev = ends[b - 1] if b > d["i"] else ends[d["i"] - 1]
        hit = ((jt > prev) & (jt <= ends[b])).any() or ((jt > ends[b]) & (jt <= ends[b] + 3600)).any() and False
        near = ((jt > ends[b] - 3 * 3600) & (jt <= ends[b] + 3600)).any()
        col = BLUE if hit else (BLUE if near else GREY)
        a2.bar(x0 + 0.5, y[b], width=0.8, color=col, alpha=1 if hit else (0.5 if near else 1))
        a2.text(x0 + 0.5, y[b] + 0.08, f"{y[b]:.1f}×", ha="center", fontsize=8.5, color=INK)
    a2.axhline(1, color=INK, lw=0.8, ls=(0, (3, 3)))
    a2.text(cl + 0.3, 1.02, "normal", color=MUTED, fontsize=8.5)
    a2.set_ylabel("move size\n(× normal for that hour)"); a2.set_ylim(0, max(3, np.nanmax(y[d['i']:d['j'] + 1]) * 1.2))
    a2.text(1, 0.15, "market closed", color=MUTED, fontsize=9); a2.text(cl + 1, 0.15, "market closed", color=MUTED, fontsize=9)
    a2.set_xlim(-6, 24); a2.set_xticks([-6, 0, 4, 9.5, 16, 20, 24])
    a2.set_xticklabels(["18:00\nday before", "0:00", "4:00", "9:30\nopen", "16:00\nclose", "20:00", "24:00 ET"])
    fig.savefig(path, dpi=140, bbox_inches="tight"); plt.close(fig)

rows = []
for n, d in enumerate(chosen, 1):
    p = out / f"R{n}_{d['sym']}.png"; draw(d, p)
    rows.append({"chart": p.name, "holding": d["sym"], "date": str(pd.Timestamp(d["ends"][d["i"]], unit="s").date()),
                 "open_x_normal": round(float(d["open_y"]), 2), "max_around_intraday_jump": round(float(d["around"]), 2),
                 "overnight_jumps": len(d["night"]), "intraday_jumps": len(d["day"]),
                 "bets": " | ".join(q.get(m, m)[:60] for m in pd.concat([d["night"], d["day"]]).market_id.unique()[:3])})
pd.DataFrame(rows).to_csv(out / "real_days.csv", index=False)
gal = out / "gallery"; gal.mkdir(exist_ok=True)
match = [c for c in C if c["open_y"] > 1 and c["around"] > 1.5]
glist = []
for n, d in enumerate(match, 1):
    name = f"G{n:03d}_{d['sym']}_{pd.Timestamp(d['ends'][d['i']], unit='s').date()}.png"
    if n <= 40:
        draw(d, gal / name)
    glist.append({"rank": n, "holding": d["sym"], "date": str(pd.Timestamp(d["ends"][d["i"]], unit="s").date()),
                  "open_x_normal": round(float(d["open_y"]), 2), "max_near_intraday_jump": round(float(d["around"]), 2),
                  "chart": name if n <= 40 else ""})
pd.DataFrame(glist).to_csv(gal / "matching_days.csv", index=False)
print("matching days:", len(match), "charts drawn:", min(40, len(match)))
print(pd.DataFrame(rows).to_string(index=False))
