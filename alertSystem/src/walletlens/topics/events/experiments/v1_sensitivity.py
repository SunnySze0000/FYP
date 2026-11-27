"""V1 · Do probability shocks move the *related* assets more than unrelated ones (same hour)?"""

from __future__ import annotations

import numpy as np

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.context import EventsContext
from walletlens.topics.events.panel import ratio_by_market


def run(ctx: EventsContext) -> ExperimentResult:
    pairs = ctx.analysis["pairs"]
    wide = ratio_by_market(pairs, "abs_r_shock", "abs_r_normal")
    diff = wide["mapped"] - wide["placebo"] if len(wide) else wide
    stat = cluster_bootstrap_mean(diff, wide["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed) if len(wide) else \
        {"mean": np.nan, "low": np.nan, "high": np.nan, "groups": 0}
    by_group = (pairs[(pairs["shocks"] > 0) & (pairs["abs_r_normal"] > 0)]
                .assign(ratio=lambda f: f["abs_r_shock"] / f["abs_r_normal"],
                        group=lambda f: f["groups"].str.split("|").str[0])
                .groupby(["group", "kind"])["ratio"].agg(["mean", "count"]).reset_index())
    # robustness: crypto-price markets ("Will BTC reach $X?") move *because* BTC moves, so they say little about
    # events moving assets; report the test with and without them
    robustness = {}
    for name, part in (("without_crypto_price_markets", pairs[~pairs["groups"].str.contains("crypto")]),
                       ("crypto_price_markets_only", pairs[pairs["groups"].str.contains("crypto")])):
        sub = ratio_by_market(part, "abs_r_shock", "abs_r_normal")
        robustness[name] = cluster_bootstrap_mean(sub["mapped"] - sub["placebo"], sub["market_id"],
                                                  ctx.cfg.bootstrap_draws, ctx.cfg.seed) if len(sub) else {}
    passed = stat["mean"] > 0 and stat["low"] > 0
    verdict = "inconclusive" if stat["groups"] < 30 else ("pass" if passed else "fail")

    fig, ax = plots.figure(8, 3.6)
    view = by_group.pivot(index="group", columns="kind", values="mean")
    x = np.arange(len(view))
    for offset, (kind, colour) in enumerate((("mapped", plots.ACCENT), ("placebo", plots.MUTED))):
        if kind in view:
            ax.bar(x + (offset - 0.5) * 0.38, view[kind], width=0.38, color=colour, label=kind)
    ax.axhline(1, color=plots.INK, lw=1, ls="--")
    ax.set_xticks(x, view.index, rotation=25)
    ax.set_ylabel("|return| in shock hours ÷ normal hours")
    ax.set_title("Do assets move more when a related event probability jumps?")
    ax.legend()
    no_crypto = robustness.get("without_crypto_price_markets") or {}
    headline = (f"In shock hours, related assets move {stat['mean']:+.2f}× (of normal-hour size) more than unrelated "
                f"assets (95% CI {stat['low']:+.2f} to {stat['high']:+.2f}, {stat['groups']} markets). Without crypto-price "
                f"markets: {no_crypto.get('mean', float('nan')):+.2f}× (CI {no_crypto.get('low', float('nan')):+.2f} to "
                f"{no_crypto.get('high', float('nan')):+.2f}).")
    return ExperimentResult(
        id="v1", title="Same-hour sensitivity", verdict=verdict, headline=headline,
        question="When an event's probability jumps, do the assets linked to that event move more than unrelated assets?",
        metrics={"main": stat, **robustness}, tables={"by_group": by_group, "per_market": wide}, figures={"sensitivity": fig},
        notes=["Direction-free test (a market's YES can be good or bad news for an asset).",
               "Pass rule: mapped-minus-placebo ratio > 0 with the 95% CI above 0 (bootstrap over markets); "
               "fewer than 30 markets = inconclusive."])
