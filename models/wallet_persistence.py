"""Does wallet skill persist ACROSS Fed meetings? (walk-forward, past-only)

sunny_playground found within-meeting persistence for the June 2026 meeting,
with the top wallets being near-certain favourite buyers. With one meeting,
skill cannot be told apart from (a) holding a favourite that drifts to $1 or
(b) the favourite-longshot bias. This test uses seven meetings and two scores:

* raw edge per share, YES-equivalent: d * (y - p)
  (d = +1 long YES / -1 short YES, p = YES price paid, y = resolved outcome)
* bias-adjusted edge: d * (y - c(p)), where c(p) = P(YES | price p) is a
  calibration curve fitted ONLY on other meetings. Systematically buying
  favourites earns ~0 here; only foresight beyond the price level counts.

For each test meeting k (in time order), wallets are scored on meetings < k
and tested on meeting k. Only trades before each market's decision cutoff
(Gamma endDate - 24 h) are used, so no trade knows its outcome.

Robustness: a partial correlation controls for formation-period style
(hold-betting, hawkish-betting, price level, one-directional vs round-trip
trading, taker share), and the one-directional subsample excludes
market-maker-like wallets. A copy test replicates the formation-top-quintile
wallets' test-meeting trades 24 h later at the then-current price, held to
resolution, net of a per-share cost.

    python models/wallet_persistence.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "polymarket"))
from wallet_pipeline.trades import load_trade_files  # noqa: E402

OUT = ROOT / "models" / "wallet_persistence"
JUNE = {"906972": "2026-06-16", "906973": "2026-06-16", "906974": "2026-06-16", "906975": "2026-06-16", "906976": "2026-06-16"}
BINS = np.r_[0, .02, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, .98, 1.0001]
MIN_TRADES = 10          # per wallet, in formation AND in test
COPY_DELAY = pd.Timedelta(hours=24)
COPY_COSTS = (0.0, 0.005, 0.01)   # USD per share


def market_table() -> pd.DataFrame:
    """Market id, meeting, decision cutoff and resolved YES outcome (0/1)."""
    probability = pd.read_csv(ROOT / "datasets" / "forward_probabilities.csv")
    probability["market_id"] = probability["market_id"].astype(str)
    final = probability.drop_duplicates("market_id").set_index("market_id")[["meeting_month", "final_outcome"]]
    rows = []
    for path in sorted((ROOT / "tmp" / "polymarket").glob("history_market_*/raw/market.json")):
        m = json.loads(path.read_text())
        rows.append(dict(market_id=str(m["id"]), cutoff=pd.Timestamp(m["endDate"]) - pd.Timedelta(hours=24),
                         file=path.parents[1] / "wallet_trades.csv.gz"))
    for mid, day in JUNE.items():
        rows.append(dict(market_id=mid, cutoff=pd.Timestamp(day, tz="UTC"),
                         file=ROOT / "datasets" / "polymarket" / f"market_{mid}" / "wallet_trades.csv.gz"))
    table = pd.DataFrame(rows).join(final, on="market_id")
    if table["final_outcome"].isna().any():
        raise ValueError("Unresolved market in table")
    return table


def load_trades(markets: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for row in markets.itertuples():
        t = load_trade_files([row.file])
        t = t.loc[t["timestamp_utc"].lt(row.cutoff)].copy()
        t["meeting"] = row.meeting_month
        t["y"] = float(row.final_outcome)
        frames.append(t)
    trades = pd.concat(frames, ignore_index=True)
    trades["raw_edge"] = trades["direction"] * (trades["y"] - trades["yes_price"])
    label = trades["rate_outcome"].str.lower()
    hawk = np.where(label.str.contains("increase"), 1, np.where(label.str.contains("decrease"), -1, 0))
    trades["signed"] = trades["direction"] * trades["shares"]
    trades["hold_vote"] = np.where(label.eq("no change"), 1, -1) * trades["signed"]
    trades["hawk_vote"] = hawk * trades["signed"]
    trades["bin"] = pd.cut(trades["yes_price"], BINS, right=False, labels=False)
    return trades


def calibration(trades: pd.DataFrame, exclude: str) -> pd.Series:
    """P(YES | price bin) from market-level trades of every meeting except one."""
    other = trades.loc[trades["meeting"].ne(exclude)]
    # one vote per market and bin, so huge markets do not dominate
    per = other.groupby(["market_id", "bin"]).agg(y=("y", "first")).reset_index()
    curve = per.groupby("bin")["y"].mean()
    return curve.reindex(range(len(BINS) - 1)).interpolate().bfill().ffill()


def add_adjusted_edge(trades: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for meeting, part in trades.groupby("meeting"):
        curve = calibration(trades, meeting)
        part = part.copy()
        part["adj_edge"] = part["direction"] * (part["y"] - part["bin"].map(curve))
        parts.append(part)
    return pd.concat(parts)


def wallet_scores(trades: pd.DataFrame) -> pd.DataFrame:
    d = trades.assign(w_raw=trades["raw_edge"] * trades["shares"], w_adj=trades["adj_edge"] * trades["shares"])
    g = d.groupby("wallet_address")
    out = pd.DataFrame({"trades": g.size(), "shares": g["shares"].sum(), "meetings": g["meeting"].nunique(),
                        "raw": g["w_raw"].sum(), "adj": g["w_adj"].sum(), "hold": g["hold_vote"].sum(),
                        "hawk": g["hawk_vote"].sum(), "price": g["yes_price"].mean(), "taker": g["taker_role"].mean()})
    for col in ("raw", "adj", "hold", "hawk"):
        out[col] /= out["shares"]
    per = d.groupby(["wallet_address", "market_id"]).agg(net=("signed", "sum"), gross=("shares", "sum"))
    out["directional"] = per["net"].abs().groupby(level=0).sum() / per["gross"].groupby(level=0).sum()
    return out


def partial_spearman(x, y, controls: pd.DataFrame) -> float:
    """Spearman correlation of x and y after removing rank-linear effects of the controls."""
    z = np.column_stack([np.ones(len(controls))] + [controls[c].rank().to_numpy() for c in controls])
    rx, ry = x.rank().to_numpy(), y.rank().to_numpy()
    res = lambda v: v - z @ np.linalg.lstsq(z, v, rcond=None)[0]
    return spearmanr(res(rx), res(ry)).statistic


def copy_test(trades, markets, test_meeting, top_wallets) -> dict:
    """Replicate the top wallets' trades COPY_DELAY later at the last traded price, hold to resolution."""
    cutoff = markets.set_index("market_id")["cutoff"]
    t = trades.loc[trades["meeting"].eq(test_meeting) & trades["wallet_address"].isin(top_wallets)].copy()
    t["copy_time"] = t["timestamp_utc"] + COPY_DELAY
    t = t.loc[t["copy_time"] < t["market_id"].map(cutoff)]
    prices = trades.loc[trades["meeting"].eq(test_meeting), ["market_id", "timestamp_utc", "yes_price"]]
    filled = []
    for mid, part in t.groupby("market_id"):
        path = prices.loc[prices["market_id"].eq(mid)].sort_values("timestamp_utc")
        idx = path["timestamp_utc"].searchsorted(part["copy_time"], side="right") - 1
        part = part.loc[idx >= 0].assign(copy_price=path["yes_price"].to_numpy()[idx[idx >= 0]])
        filled.append(part)
    t = pd.concat(filled)
    gross = t["direction"] * (t["y"] - t["copy_price"])
    w = t["shares"]
    out = dict(copied_trades=len(t), their_edge_per_share=float((t["raw_edge"] * w).sum() / w.sum()))
    for cost in COPY_COSTS:
        out[f"copy_net_cost_{cost:.3f}"] = float(((gross - cost) * w).sum() / w.sum())
    return out


def persistence(trades: pd.DataFrame, markets: pd.DataFrame, order: list[str]):
    rng = np.random.default_rng(0)
    rows, quint, copies = [], [], []
    controls = ["hold_f", "hawk_f", "price_f", "directional_f", "taker_f"]
    for k in range(2, len(order)):
        form = wallet_scores(trades.loc[trades["meeting"].isin(order[:k])])
        test = wallet_scores(trades.loc[trades["meeting"].eq(order[k])])
        both = form.join(test, lsuffix="_f", rsuffix="_t", how="inner")
        both = both.loc[(both["trades_f"] >= MIN_TRADES) & (both["trades_t"] >= MIN_TRADES)].copy()
        both["taker_f"] = both["taker_f"].fillna(both["taker_f"].median())
        one_way = both.loc[both["directional_f"] >= .8]
        for score in ("raw", "adj"):
            rho = spearmanr(both[f"{score}_f"], both[f"{score}_t"]).statistic
            perm = np.array([spearmanr(rng.permutation(both[f"{score}_f"].to_numpy()), both[f"{score}_t"]).statistic
                             for _ in range(300)])
            q = pd.qcut(both[f"{score}_f"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
            test_by_q = both.groupby(q, observed=True).apply(lambda g: (g[f"{score}_t"] * g["shares_t"]).sum() / g["shares_t"].sum())
            rows.append(dict(test_meeting=order[k], formation=f"{order[0]}..{order[k - 1]}", score=score,
                             wallets=len(both), rho=rho, perm_p=float((np.abs(perm) >= abs(rho)).mean()),
                             partial_rho_style_controls=partial_spearman(both[f"{score}_f"], both[f"{score}_t"], both[controls]),
                             rho_one_directional=spearmanr(one_way[f"{score}_f"], one_way[f"{score}_t"]).statistic,
                             one_directional_wallets=len(one_way),
                             top_minus_bottom=float(test_by_q.loc[5] - test_by_q.loc[1])))
            for qi, v in test_by_q.items():
                quint.append(dict(test_meeting=order[k], score=score, quintile=int(qi), test_edge_per_share=v))
        eligible = form.loc[form["trades"] >= MIN_TRADES]
        top = set(eligible.index[eligible["adj"] >= eligible["adj"].quantile(.8)])
        copies.append(dict(test_meeting=order[k], top_wallets=len(top), **copy_test(trades, markets, order[k], top)))
    return pd.DataFrame(rows), pd.DataFrame(quint), pd.DataFrame(copies)


def pooled(res: pd.DataFrame) -> pd.DataFrame:
    """Meeting-level summary: mean rho, how many test meetings positive, sign test."""
    from scipy.stats import binomtest
    out = []
    for score, g in res.groupby("score"):
        pos = int((g["rho"] > 0).sum())
        out.append(dict(score=score, test_meetings=len(g), mean_rho=g["rho"].mean(),
                        positive_meetings=pos, sign_test_p=binomtest(pos, len(g), .5).pvalue,
                        mean_top_minus_bottom=g["top_minus_bottom"].mean(), median_wallets=int(g["wallets"].median())))
    return pd.DataFrame(out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    markets = market_table()
    trades = add_adjusted_edge(load_trades(markets))
    order = list(markets.groupby("meeting_month")["cutoff"].max().sort_values().index)
    cov = trades.groupby("meeting").agg(markets=("market_id", "nunique"), trades=("shares", "size"),
                                        wallets=("wallet_address", "nunique")).reindex(order)
    curve = calibration(trades, exclude="none")
    res, quint, copies = persistence(trades, markets, order)
    pool = pooled(res)
    cov.to_csv(OUT / "coverage.csv"); res.to_csv(OUT / "persistence_by_meeting.csv", index=False)
    quint.to_csv(OUT / "test_edge_by_quintile.csv", index=False); pool.to_csv(OUT / "pooled.csv", index=False)
    copies.to_csv(OUT / "copy_test.csv", index=False)
    mids = [(BINS[i] + min(BINS[i + 1], 1)) / 2 for i in range(len(BINS) - 1)]
    cal = pd.DataFrame({"price_bin_mid": mids, "yes_rate": curve.to_numpy()})
    cal.to_csv(OUT / "calibration_all.csv", index=False)
    print(cov, "\n", cal.round(3).to_string(index=False), "\n", res.round(4).to_string(index=False),
          "\n", pool.round(4).to_string(index=False), "\n", copies.round(4).to_string(index=False))
    return cov, cal, res, quint, pool, copies


if __name__ == "__main__":
    main()
