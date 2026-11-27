"""M1 · Learned bet-to-asset links with our own text model (TF-IDF + ridge), no LLM.

Pre-registered in docs/06_round3_research.md. Labels: for every candidate market x asset, the asset's
shock-hour |return| / normal |return| - 1 (watched hours). One ridge per asset on the question text, trained
on markets closing before split_ts. Links = top 3 assets per market whose prediction clears that asset's
75th training percentile. Compared with keyword links on markets closing after split_ts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from walletlens import io
from walletlens.config import ASSET_GROUPS
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.collect import DTYPES, groups_for
from walletlens.topics.events.daily import WATCH_AGE, WATCH_HIGH, WATCH_LOW, hourly_book
from walletlens.topics.events.panel import _price_at

TOP_K, QUANTILE, DRAWS = 3, 0.75, 2000


def all_pairs(markets: pd.DataFrame, prices: pd.DataFrame, book, shock: float) -> pd.DataFrame:
    series = {m: (g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float))
              for m, g in prices.sort_values("ts").groupby("market_id")}
    rows = []
    for m in markets.itertuples(index=False):
        if m.market_id not in series:
            continue
        p_times, p_values = series[m.market_id]
        for asset, (ends, closes) in book.series.items():
            inside = (ends > p_times[0] + WATCH_AGE) & (ends <= min(m.close_ts, p_times[-1] + 3600))
            idx = np.nonzero(inside)[0]
            idx = idx[idx >= 1]
            if len(idx) < 10:
                continue
            x, xp = ends[idx], ends[idx - 1]
            p_now, p_before = _price_at(p_times, p_values, x, 7200), _price_at(p_times, p_values, xp, 7200)
            ok = (x - xp <= 3600) & (p_before >= WATCH_LOW) & (p_before <= WATCH_HIGH) & np.isfinite(p_now)
            r = np.log(closes[idx] / closes[idx - 1])
            ok &= np.isfinite(r)
            if ok.sum() < 10:
                continue
            dp, r = (p_now - p_before)[ok], np.abs(r[ok])
            s = np.abs(dp) >= shock
            if not s.any() or (~s).sum() < 5:
                continue
            normal = r[~s].mean()
            if normal <= 0:
                continue
            rows.append({"market_id": m.market_id, "asset": asset, "shocks": int(s.sum()),
                         "excess": float(r[s].mean() / normal - 1)})
    return pd.DataFrame(rows)


def _effect(test: pd.DataFrame, linked_col: str) -> pd.DataFrame:
    g = test.groupby(["market_id", linked_col])["excess"].mean().unstack()
    return g.dropna(subset=[True, False]) if True in g and False in g else pd.DataFrame(columns=[True, False])


def _boot(values: np.ndarray, rng) -> tuple[float, float, float]:
    if len(values) < 2:
        return np.nan, np.nan, np.nan
    means = np.array([values[rng.integers(0, len(values), len(values))].mean() for _ in range(DRAWS)])
    return float(values.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def run(ctx) -> ExperimentResult:
    folder = ctx.settings.paths.dataset("events_all")
    markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)          # all candidates, incl. unmapped
    prices = io.read_table(folder / "prices.pkl.gz")
    pairs = all_pairs(markets, prices, hourly_book(ctx.hourly), ctx.cfg.shock_points)
    pairs = pairs.merge(markets[["market_id", "question", "close_ts"]], on="market_id")
    pairs["keyword"] = [a in {x for g in groups_for(q) if g != "us_politics" for x in ASSET_GROUPS.get(g, ())}
                        for a, q in zip(pairs["asset"], pairs["question"])]
    train_m = markets[markets["close_ts"] < ctx.split_ts]
    test_m = markets[markets["close_ts"] >= ctx.split_ts]
    vec_w = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    vec_c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True)
    vec_w.fit(train_m["question"]), vec_c.fit(train_m["question"])
    X = lambda q: hstack([vec_w.transform(q), vec_c.transform(q)]).tocsr()
    preds, cuts = {}, {}
    q_all = markets.set_index("market_id")["question"]
    for asset, part in pairs[pairs["close_ts"] < ctx.split_ts].groupby("asset"):
        if len(part) < 30:
            continue
        model = Ridge(alpha=3.0).fit(X(part["question"]), part["excess"].clip(-1, 3), sample_weight=np.sqrt(part["shocks"]))
        preds[asset] = pd.Series(model.predict(X(q_all)), index=q_all.index)
        cuts[asset] = float(preds[asset].loc[part["market_id"]].quantile(QUANTILE))
    P = pd.DataFrame(preds)
    over = P.ge(pd.Series(cuts)).astype(bool)
    rank = P.rank(axis=1, ascending=False) <= TOP_K
    linked = (over & rank).stack().rename("model").reset_index().rename(columns={"level_0": "market_id", "level_1": "asset"})
    pairs = pairs.merge(linked, on=["market_id", "asset"], how="left")
    pairs["model"] = pairs["model"].fillna(False).astype(bool)
    pairs["union"] = pairs["model"] | pairs["keyword"]
    test = pairs[pairs["close_ts"] >= ctx.split_ts]
    rng = np.random.default_rng(ctx.cfg.seed)
    out, effects = {}, {}
    for col in ("keyword", "model", "union"):
        e = _effect(test, col)
        diff = (e[True] - e[False]).to_numpy()
        effects[col] = pd.Series(diff, index=e.index)
        mean, lo, hi = _boot(diff, rng)
        covered = int(test.loc[test[col], "market_id"].nunique())
        out[col] = {"effect": mean, "low": lo, "high": hi, "markets_scored": int(len(diff)), "markets_covered": covered,
                    "links": int(test[col].sum())}
    common = effects["model"].index.intersection(effects["keyword"].index)
    paired = _boot((effects["model"][common] - effects["keyword"][common]).to_numpy(), rng)
    checks = {"model_ci_above_0": bool(out["model"]["low"] > 0),
              "model_at_least_keyword": bool(out["model"]["effect"] >= out["keyword"]["effect"]),
              "coverage_at_least_keyword": bool(out["model"]["markets_covered"] >= out["keyword"]["markets_covered"])}
    verdict = "pass" if all(checks.values()) else "fail"
    examples = []
    for mid in test_m.sample(min(12, len(test_m)), random_state=1)["market_id"]:
        if mid in P.index:
            top = P.loc[mid].sort_values(ascending=False).head(3)
            examples.append({"question": q_all[mid][:90], "model_top3": ", ".join(f"{a} {v:+.2f}" for a, v in top.items()),
                             "keyword": "|".join(groups_for(q_all[mid]))})
    headline = (f"Test markets: keyword links {out['keyword']['effect']:+.3f} (CI {out['keyword']['low']:+.3f} to {out['keyword']['high']:+.3f}, "
                f"{out['keyword']['markets_covered']} markets); text model {out['model']['effect']:+.3f} (CI {out['model']['low']:+.3f} to "
                f"{out['model']['high']:+.3f}, {out['model']['markets_covered']} markets); union {out['union']['effect']:+.3f} "
                f"({out['union']['markets_covered']} markets). Model − keyword on shared markets {paired[0]:+.3f} (CI {paired[1]:+.3f} to {paired[2]:+.3f}).")
    return ExperimentResult(id="m1", title="Learned bet-to-asset links", verdict=verdict, headline=headline,
                            question="Does a text model trained on which markets moved which assets link bets better than keywords?",
                            metrics={"checks": checks, "results": out, "paired_model_minus_keyword": paired,
                                     "pairs": int(len(pairs)), "assets_modelled": len(preds)},
                            tables={"summary": pd.DataFrame(out).T.reset_index(), "examples": pd.DataFrame(examples)},
                            notes=["Effect = per market, mean excess shock-hour move of linked assets minus unlinked assets."])
