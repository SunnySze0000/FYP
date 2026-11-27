"""V2 · After a shock, can we predict the related asset's *next* hour (direction, and size)?"""

from __future__ import annotations

import numpy as np

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.context import EventsContext
from walletlens.topics.events.panel import ratio_by_market


def run(ctx: EventsContext) -> ExperimentResult:
    pairs = ctx.analysis["pairs"]
    mapped = pairs[(pairs["kind"] == "mapped") & (pairs["direction_attempts"] > 0)]
    per_market = mapped.groupby("market_id")[["direction_hits", "direction_attempts"]].sum()
    hit_rate = per_market["direction_hits"] / per_market["direction_attempts"]
    stat = cluster_bootstrap_mean(hit_rate - 0.5, per_market.index, ctx.cfg.bootstrap_draws, ctx.cfg.seed) \
        if len(per_market) else {"mean": np.nan, "low": np.nan, "high": np.nan, "groups": 0}
    vol = ratio_by_market(pairs, "abs_next_shock", "abs_next_normal")
    vol_stat = cluster_bootstrap_mean(vol["mapped"] - vol["placebo"], vol["market_id"], ctx.cfg.bootstrap_draws,
                                      ctx.cfg.seed) if len(vol) else {"mean": np.nan, "low": np.nan, "high": np.nan, "groups": 0}
    passed = stat["mean"] > 0 and stat["low"] > 0
    verdict = "inconclusive" if stat["groups"] < 30 else ("pass" if passed else "fail")

    fig, axes = plots.figure(10, 3.4, ncols=2)
    if len(hit_rate):
        axes[0].hist(hit_rate, bins=20, color=plots.ACCENT)
        axes[0].axvline(0.5, color=plots.INK, ls="--", lw=1)
        axes[0].set_title("Next-hour direction hit rate per market")
    if len(vol):
        axes[1].scatter(vol["placebo"], vol["mapped"], s=8, alpha=0.5, color=plots.ACCENT)
        lim = float(np.nanmax([vol["placebo"].max(), vol["mapped"].max(), 2]))
        axes[1].plot([0, lim], [0, lim], color=plots.MUTED, ls="--", lw=1)
        axes[1].set_xlabel("unrelated assets")
        axes[1].set_ylabel("related assets")
        axes[1].set_title("Next-hour |return| ratio after shocks")
    headline = (f"Next-hour direction after shocks: hit rate {0.5 + stat['mean']:.1%} (95% CI {0.5 + stat['low']:.1%} to "
                f"{0.5 + stat['high']:.1%}, {stat['groups']} markets). Next-hour size effect vs unrelated assets: "
                f"{vol_stat['mean']:+.2f}× (CI {vol_stat['low']:+.2f} to {vol_stat['high']:+.2f}).")
    return ExperimentResult(
        id="v2", title="Next-hour lead", verdict=verdict, headline=headline,
        question="Does a probability shock tell us where the related asset goes in the following hour?",
        metrics={"direction": stat, "next_hour_size": vol_stat}, tables={"per_market_hits": per_market.reset_index()},
        figures={"lead": fig},
        notes=["Direction uses the sign of each market-asset co-movement estimated on earlier hours only.",
               "Pass rule (direction): hit rate above 50% with the 95% CI above 50%; < 30 markets = inconclusive. "
               "The size effect is reported as secondary (useful for a volatility warning)."])
