"""E2 · H1: do wallets that beat fair value earlier keep beating it later?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.skill import shrink
from walletlens.analytics.stats import spearman, spearman_test
from walletlens.research import plots
from walletlens.research.context import ResearchContext
from walletlens.research.result import ExperimentResult


def _period_means(wm: pd.DataFrame, markets: set, column: str) -> pd.DataFrame:
    part = wm[wm["market_id"].isin(markets)]
    return part.groupby("wallet").agg(n=(column, "size"), mean=(column, "mean"),
                                      longshot=("longshot_share", "mean"))


def run(ctx: ResearchContext) -> ExperimentResult:
    cfg = ctx.cfg
    wm = ctx.wallet_markets
    m = cfg.persistence_min_markets
    results, pairs_out = {}, None
    for column in ("edge", "raw_edge"):
        a = _period_means(wm, ctx.split["a_markets"], column)
        b = _period_means(wm, ctx.split["b_markets"], column)
        pairs = a.merge(b, left_index=True, right_index=True, suffixes=("_a", "_b"), how="inner")
        pairs = pairs[(pairs["n_a"] >= m) & (pairs["n_b"] >= m)]
        results[column] = spearman_test(pairs["mean_a"], pairs["mean_b"], cfg.permutations, cfg.seed)
        if column == "edge":
            pairs_out = pairs
            # style control: does early edge still predict later edge once long-shot buying is held fixed?
            if len(pairs) > 10:
                resid = lambda v: v - np.polyval(np.polyfit(pairs["longshot_a"], v, 1), pairs["longshot_a"])  # noqa: E731
                results["edge_partial_longshot"] = {"rho": spearman(resid(pairs["mean_a"]), pairs["mean_b"]),
                                                    "n": int(len(pairs))}

    # rolling version: prior skill (all earlier events) vs edge in each later event
    order = ctx.markets.groupby("group_id")["close_ts"].max().sort_values()
    rolling = []
    for position, group in enumerate(order.index):
        if position < 2:
            continue
        earlier = wm[wm["close_ts"] < ctx.markets.loc[ctx.markets["group_id"] == group, "close_ts"].min()]
        prior = earlier.groupby("wallet")["edge"].agg(["size", "mean"])
        prior = prior[prior["size"] >= m]
        now = wm[wm["group_id"] == group].groupby("wallet")["edge"].mean()
        joined = prior.join(now.rename("now"), how="inner")
        if len(joined) >= 10:
            rolling.append({"event": group, "wallets": len(joined),
                            "rho": spearman(shrink(joined["mean"], joined["size"], cfg.skill_shrinkage_markets),
                                            joined["now"])})
    rolling = pd.DataFrame(rolling)

    main = results["edge"]
    passed = (main["rho"] > 0) and (main["p_one_sided"] < 0.05)
    verdict = "inconclusive" if main["n"] < 30 else ("pass" if passed else "fail")

    fig, axes = plots.figure(10, 3.8, ncols=2)
    if pairs_out is not None and len(pairs_out):
        axes[0].scatter(pairs_out["mean_a"].rank(pct=True), pairs_out["mean_b"].rank(pct=True), s=6,
                        color=plots.ACCENT, alpha=0.45)
        axes[0].set_xlabel("edge rank in period A")
        axes[0].set_ylabel("edge rank in period B")
        axes[0].set_title(f"Same wallets, two periods (ρ = {main['rho']:.2f}, n = {main['n']})")
    if len(rolling):
        axes[1].bar(rolling["event"].astype(str), rolling["rho"],
                    color=[plots.ACCENT if r > 0 else plots.SECOND for r in rolling["rho"]])
        axes[1].axhline(0, color=plots.MUTED, lw=1)
        axes[1].set_title("Prior skill vs edge in each later event (Spearman)")
        axes[1].tick_params(axis="x", rotation=45)

    headline = (f"Spearman ρ between period-A and period-B edge = {main['rho']:.3f} "
                f"(95% CI {main['low']:.3f} to {main['high']:.3f}, permutation p = {main['p_one_sided']:.4f}, "
                f"{main['n']} wallets with ≥ {m} markets in each period).")
    if "edge_partial_longshot" in results:
        headline += f" Holding long-shot style fixed: ρ = {results['edge_partial_longshot']['rho']:.3f}."
    metrics = {"edge_vs_fair": main, "edge_vs_price": results["raw_edge"],
               "partial_longshot": results.get("edge_partial_longshot", {}),
               "rolling_mean_rho": float(rolling["rho"].mean()) if len(rolling) else float("nan"),
               "rolling_events": int(len(rolling)), "min_markets_per_period": m}
    tables = {"rolling": rolling}
    if pairs_out is not None:
        tables["wallet_pairs"] = pairs_out.reset_index()
    return ExperimentResult(
        id="e2", title="Skill persistence (H1)", verdict=verdict, headline=headline,
        question="Do wallets with high edge in earlier markets also have high edge in later markets?",
        metrics=metrics, tables=tables, figures={"persistence": fig},
        notes=["Pass rule (pre-registered): ρ > 0 with permutation p < 0.05; fewer than 30 wallets = inconclusive.",
               "Edge is measured against fair value from E1; the raw-price version is reported for comparison."])
