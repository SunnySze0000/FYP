"""V4 · Are event-asset exposures stable enough to use as hedge ratios?"""

from __future__ import annotations

import numpy as np

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.context import EventsContext


def run(ctx: EventsContext) -> ExperimentResult:
    pairs = ctx.analysis["pairs"]
    mapped = pairs[(pairs["kind"] == "mapped") & (pairs["shocks_first"] >= 2) & (pairs["shocks_second"] >= 2)].dropna(
        subset=["beta_first", "beta_second"])
    agree = (np.sign(mapped["beta_first"]) == np.sign(mapped["beta_second"])).astype(float)
    stat = cluster_bootstrap_mean(agree - 0.5, mapped["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed) \
        if len(mapped) else {"mean": np.nan, "low": np.nan, "high": np.nan, "groups": 0}
    passed = stat["mean"] > 0 and stat["low"] > 0
    verdict = "inconclusive" if stat["groups"] < 30 else ("pass" if passed else "fail")
    fig, ax = plots.figure(6, 3.6)
    if len(mapped):
        clip = np.nanquantile(np.abs(np.r_[mapped["beta_first"], mapped["beta_second"]]), 0.95)
        ax.scatter(mapped["beta_first"].clip(-clip, clip), mapped["beta_second"].clip(-clip, clip), s=8, alpha=0.5,
                   color=plots.ACCENT)
        ax.axhline(0, color=plots.MUTED, lw=1)
        ax.axvline(0, color=plots.MUTED, lw=1)
        ax.set_xlabel("exposure, first half of market life")
        ax.set_ylabel("exposure, second half")
        ax.set_title("Does an asset's exposure to an event keep its sign?")
    headline = (f"Exposure keeps its sign in {0.5 + stat['mean']:.0%} of related market-asset pairs "
                f"(95% CI {0.5 + stat['low']:.0%} to {0.5 + stat['high']:.0%}, {stat['groups']} markets).")
    return ExperimentResult(
        id="v4", title="Stable exposures", verdict=verdict, headline=headline,
        question="If an asset rose with an event's probability early on, does it still do so later?",
        metrics={"main": stat, "pairs": int(len(mapped))}, tables={"pairs": mapped}, figures={"stability": fig},
        notes=["Exposure = slope of hourly asset return on hourly change in the event's log-odds.",
               "Pass rule: sign agreement above 50% with the 95% CI above 50%."])
