"""E3 · H2: after a top-tier wallet trades, does the price move its way more than after other trades?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.markout import add_markouts
from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research import plots
from walletlens.research.context import ResearchContext
from walletlens.research.result import ExperimentResult


def _per_market(trades: pd.DataFrame, column: str, weight: str | None) -> pd.DataFrame:
    """Per market: mean markout of top-tier trades, of all other trades, and the difference."""
    frame = trades[["market_id", "group_id", "top", column] + ([weight] if weight else [])].copy()
    frame["market_id"] = frame["market_id"].astype(str)
    frame["w"] = frame[weight] if weight else 1.0
    frame["wx"] = frame["w"] * frame[column]
    sums = frame.groupby(["market_id", "group_id", "top"], observed=True)[["wx", "w"]].sum().reset_index()
    sums["mean"] = sums["wx"] / sums["w"]
    wide = sums.pivot_table(index=["market_id", "group_id"], columns="top", values="mean").reset_index()
    wide = wide.rename(columns={True: "top", False: "rest"}).dropna(subset=["top", "rest"])
    wide["diff"] = wide["top"] - wide["rest"]
    return wide


def run(ctx: ResearchContext) -> ExperimentResult:
    cfg = ctx.cfg
    trades = add_markouts(ctx.period_b_trades, ctx.markets, ctx.book, cfg.markout_horizons_s)
    low, high = cfg.signal_price_band
    banded = trades[(trades["yes_price"] >= low) & (trades["yes_price"] <= high)]
    columns = [f"markout_{h}" for h in cfg.markout_horizons_s] + ["markout_res"]

    rows, per_market_main = [], None
    for label, subset in (("band", banded), ("all", trades)):
        for weight in (None, "notional"):
            for column in columns:
                wide = _per_market(subset, column, weight)
                stat = cluster_bootstrap_mean(wide["diff"], wide["group_id"], cfg.bootstrap_draws, cfg.seed)
                rows.append({"sample": label, "weighting": weight or "equal", "horizon": column,
                             "top_mean": float(wide["top"].mean()) if len(wide) else np.nan,
                             "rest_mean": float(wide["rest"].mean()) if len(wide) else np.nan,
                             "diff": stat["mean"], "low": stat["low"], "high": stat["high"],
                             "p": stat["p_two_sided"], "markets": len(wide), "events": stat["groups"]})
                if label == "band" and weight is None and column == "markout_res":
                    per_market_main = wide
    table = pd.DataFrame(rows)

    tiers = (banded.groupby("tier")[columns].mean() * 100).reset_index()
    counts = banded["tier"].value_counts().rename("trades").reset_index()
    tiers = tiers.merge(counts, on="tier")

    main = table[(table["sample"] == "band") & (table["weighting"] == "equal") & (table["horizon"] == "markout_res")].iloc[0]
    events = int(main["events"])
    passed = main["diff"] > 0 and main["low"] > 0
    verdict = "inconclusive" if events < 5 or main["markets"] < 10 else ("pass" if passed else "fail")

    fig, ax = plots.figure(7.5, 3.6)
    labels = {f"markout_{h}": f"+{h // 3600} h" for h in cfg.markout_horizons_s} | {"markout_res": "to resolution"}
    view = table[(table["sample"] == "band") & (table["weighting"] == "equal")]
    x = np.arange(len(view))
    ax.bar(x, view["diff"] * 100, color=plots.ACCENT, width=0.55)
    ax.errorbar(x, view["diff"] * 100, yerr=[np.clip((view["diff"] - view["low"]) * 100, 0, None),
                                             np.clip((view["high"] - view["diff"]) * 100, 0, None)],
                fmt="none", ecolor=plots.INK, capsize=4)
    ax.axhline(0, color=plots.MUTED, lw=1)
    ax.set_xticks(x, [labels[h] for h in view["horizon"]])
    ax.set_ylabel("top tier minus rest (probability points)")
    ax.set_title("Price move in the trader's favour after the trade")

    headline = (f"Top-tier trades beat other trades by {main['diff'] * 100:+.2f} points to resolution "
                f"(95% CI {main['low'] * 100:+.2f} to {main['high'] * 100:+.2f}; {int(main['markets'])} markets, "
                f"{events} events).")
    top_share = float(banded["top"].mean()) if len(banded) else float("nan")
    metrics = {"main": main.to_dict(), "top_tier_share_of_trades": top_share,
               "period_b_trades": int(len(trades)), "banded_trades": int(len(banded))}
    return ExperimentResult(
        id="e3", title="Information in skilled wallets' trades (H2)", verdict=verdict, headline=headline,
        question="Is the price more likely to move in a trade's direction when the trader has proven skill?",
        metrics=metrics, tables={"markout_tests": table, "tier_means_pct_points": tiers,
                                 "per_market_main": per_market_main if per_market_main is not None else pd.DataFrame()},
        figures={"markouts": fig},
        notes=["Skill tier is decided with markets closed before each trade (walk-forward).",
               "Main test (pre-registered): trades with YES price in the band, equal weight, to resolution; "
               "per-market differences, bootstrap over events. Fewer than 5 events or 10 markets = inconclusive."])
