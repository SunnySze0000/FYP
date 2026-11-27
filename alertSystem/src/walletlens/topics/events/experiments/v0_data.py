"""V0 · Data: which event markets and assets are covered?"""

from __future__ import annotations

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.context import EventsContext

MIN_MARKETS = 100


def run(ctx: EventsContext) -> ExperimentResult:
    pairs, shocks = ctx.analysis["pairs"], ctx.analysis["shocks"]
    groups = ctx.markets["groups"].str.split("|").explode().value_counts().rename_axis("group").reset_index(name="markets")
    usable = pairs[pairs["kind"] == "mapped"]["market_id"].nunique() if len(pairs) else 0
    fig, axes = plots.figure(10, 3.4, ncols=2)
    axes[0].barh(groups["group"], groups["markets"], color=plots.ACCENT)
    axes[0].set_title("Contested markets by event group")
    if len(shocks):
        axes[1].hist(shocks["dp"], bins=40, color=plots.ACCENT)
        axes[1].set_title(f"Probability shocks (|Δp| ≥ {ctx.cfg.shock_points:.0%} in one hour): {len(shocks):,}")
    metrics = {"markets": int(len(ctx.markets)), "markets_with_aligned_assets": int(usable),
               "pairs": int(len(pairs)), "shock_hours": int(len(shocks)),
               "asset_series": int(ctx.hourly["symbol"].nunique())}
    return ExperimentResult(
        id="v0", title="Data", verdict="pass" if usable >= MIN_MARKETS else "fail",
        headline=f"{usable} event markets aligned with hourly prices of {metrics['asset_series']} assets; {len(shocks):,} shock hours.",
        question="Are there enough contested event markets overlapping with asset trading hours?",
        metrics=metrics, tables={"groups": groups}, figures={"coverage": fig},
        notes=[f"Pass rule: ≥ {MIN_MARKETS} markets with aligned mapped assets."])
