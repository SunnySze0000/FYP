"""V3 · Do skilled wallets move event probabilities before everyone else?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.context import EventsContext

MIN_FLOW_USD = 500


def run(ctx: EventsContext) -> ExperimentResult:
    universe = ctx.universe
    if universe is None:
        return ExperimentResult(id="v3", title="Skilled wallets lead the probability", verdict="inconclusive",
                                headline="Topic F's trade data has not been collected yet, so this cannot be tested.",
                                question="Does net buying by skilled wallets predict the next hour's probability move?")
    trades = universe.trades
    skill = universe.timeline.lookup(trades["wallet"].astype(str), trades["ts"])
    frame = pd.DataFrame({"market_id": trades["market_id"].astype(str).to_numpy(),
                          "hour_end": (trades["ts"].to_numpy() // 3600 + 1) * 3600,
                          "signed": (trades["yes_dir"] * trades["notional"]).to_numpy(),
                          "top": skill["top"].to_numpy()})
    flows = frame.assign(top_flow=np.where(frame["top"], frame["signed"], 0.0),
                         rest_flow=np.where(frame["top"], 0.0, frame["signed"])) \
        .groupby(["market_id", "hour_end"])[["top_flow", "rest_flow"]].sum().reset_index()
    prices = pd.concat([ctx.prices, universe.prices.astype({"market_id": str})]).drop_duplicates(["market_id", "ts"])
    rows = []
    for market_id, part in flows.groupby("market_id"):
        series = prices[prices["market_id"] == market_id].sort_values("ts")
        if len(series) < 10:
            continue
        times, values = series["ts"].to_numpy("int64"), series["yes_price"].to_numpy(float)
        now = np.searchsorted(times, part["hour_end"].to_numpy(), side="right") - 1
        later = np.searchsorted(times, part["hour_end"].to_numpy() + 3600, side="right") - 1
        ok = (now >= 0) & (later > now)
        dp_next = np.where(ok, values[np.clip(later, 0, None)] - values[np.clip(now, 0, None)], np.nan)
        rows.append(part.assign(dp_next=dp_next))
    panel = pd.concat(rows) if rows else pd.DataFrame(columns=["market_id", "top_flow", "rest_flow", "dp_next"])
    results = {}
    for name in ("top_flow", "rest_flow"):
        use = panel[(panel[name].abs() >= MIN_FLOW_USD) & panel["dp_next"].notna()]
        signed = np.sign(use[name]) * use["dp_next"]
        results[name] = cluster_bootstrap_mean(signed, use["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed) \
            if len(use) else {"mean": np.nan, "low": np.nan, "high": np.nan, "groups": 0, "n": 0}
    top = results["top_flow"]
    passed = top["mean"] > 0 and top["low"] > 0
    verdict = "inconclusive" if top.get("groups", 0) < 30 else ("pass" if passed else "fail")

    fig, ax = plots.figure(6, 3.4)
    names = ["skilled wallets", "everyone else"]
    values = [results["top_flow"], results["rest_flow"]]
    x = np.arange(2)
    ax.bar(x, [v["mean"] * 100 for v in values], color=[plots.ACCENT, plots.MUTED], width=0.5)
    ax.errorbar(x, [v["mean"] * 100 for v in values], yerr=[[max((v["mean"] - v["low"]) * 100, 0) for v in values],
                                                             [max((v["high"] - v["mean"]) * 100, 0) for v in values]],
                fmt="none", ecolor=plots.INK, capsize=4)
    ax.axhline(0, color=plots.MUTED, lw=1)
    ax.set_xticks(x, names)
    ax.set_ylabel("next-hour move in the flow's direction (points)")
    ax.set_title("Does the price follow where the money went?")
    headline = (f"After an hour of net skilled-wallet buying (≥ ${MIN_FLOW_USD}), the probability moves "
                f"{top['mean'] * 100:+.2f} points their way next hour (95% CI {top['low'] * 100:+.2f} to "
                f"{top['high'] * 100:+.2f}, {top.get('groups', 0)} markets); everyone else: {results['rest_flow']['mean'] * 100:+.2f}.")
    return ExperimentResult(
        id="v3", title="Skilled wallets lead the probability", verdict=verdict, headline=headline,
        question="Does net buying by skilled wallets predict the next hour's probability move?",
        metrics=results, figures={"wallet_lead": fig},
        notes=["Skill is point-in-time (topic F's timeline: markets closed before each trade).",
               "Pass rule: skilled-flow signed next-hour move > 0 with the 95% CI above 0; < 30 markets = inconclusive."])
