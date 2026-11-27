"""W0 · Wallet data in the event markets, and what the team's pipeline makes of it."""

from __future__ import annotations

import pandas as pd

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import WalletContext
from walletlens.topics.events.wallets import TYPES

MIN_MARKETS = 100
MIN_SHOCKS = 300


def run(ctx: WalletContext) -> ExperimentResult:
    if ctx.trades.empty:
        return ExperimentResult(id="w0", title="Wallet data", verdict="fail", headline="No event-market trades collected.",
                                question="Is there wallet data for the event markets?")
    tagged, hours = ctx.tagged, ctx.hours
    pipeline_table, pipeline_summary = ctx.pipeline
    shocks_with_flow = int((hours["shock"] & (hours["f_trades"] > 0)).sum())
    markets = int(tagged["market_id"].nunique())
    shares = pd.DataFrame({"type": list(TYPES),
                           "share_of_trades": [float(tagged[t].mean()) for t in TYPES],
                           "share_of_dollars": [float(tagged.loc[tagged[t], "notional"].sum() / tagged["notional"].sum())
                                                for t in TYPES]})
    clusters = tagged["cluster_id"].value_counts().rename_axis("cluster_id").reset_index(name="trades")
    fig, axes = plots.figure(10, 3.4, ncols=2)
    axes[0].barh(shares["type"], shares["share_of_dollars"] * 100, color=plots.ACCENT)
    axes[0].set_xlabel("share of dollars traded (%)")
    axes[0].set_title("Who trades the event markets")
    axes[1].bar(clusters["cluster_id"], clusters["trades"], color=plots.THIRD)
    axes[1].set_title("Trades by behaviour cluster (team pipeline, frozen)")
    axes[1].tick_params(axis="x", rotation=30)
    passed = markets >= MIN_MARKETS and shocks_with_flow >= MIN_SHOCKS
    return ExperimentResult(
        id="w0", title="Wallet data", verdict="pass" if passed else "fail",
        headline=(f"{len(tagged):,} trades by {tagged['wallet'].nunique():,} wallets in {markets} event markets; "
                  f"{shocks_with_flow} probability jumps with trades in the same hour. Team pipeline: "
                  f"{pipeline_summary.get('merged_entities', 0)} same-owner groups, "
                  f"{pipeline_summary.get('rule_counts', {}).get('eligible', 0)} entities pass the hard rules, "
                  f"{pipeline_summary.get('clustering', {}).get('selected_k', 0)} behaviour clusters."),
        question="Is there enough wallet-level data around probability jumps to test W1-W5?",
        metrics={"trades": int(len(tagged)), "wallets": int(tagged["wallet"].nunique()), "markets": markets,
                 "market_hours": int(len(hours)), "shocks_with_flow": shocks_with_flow,
                 "pipeline": {k: v for k, v in pipeline_summary.items() if k != "cluster_explanations"},
                 "cluster_explanations": pipeline_summary.get("cluster_explanations", {})},
        tables={"type_shares": shares, "clusters": clusters,
                "pipeline_wallets": pipeline_table.head(50_000) if len(pipeline_table) else pd.DataFrame()},
        figures={"wallets": fig},
        notes=[f"Pass rule: ≥ {MIN_MARKETS} markets with trades and ≥ {MIN_SHOCKS} jumps with same-hour trades.",
               "Behaviour clusters are fitted on trades before the median market close and then frozen (team pipeline).",
               "Types are not exclusive except retail; trade shares: "
               + ", ".join(f"{t} {v:.1%}" for t, v in zip(shares['type'], shares['share_of_trades'])) + "."])
