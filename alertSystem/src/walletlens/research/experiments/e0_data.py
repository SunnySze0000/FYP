"""E0 · What is in the dataset? Coverage, concentration and whether wallets repeat across markets."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from walletlens.research import plots
from walletlens.research.context import ResearchContext
from walletlens.research.result import ExperimentResult


def run(ctx: ResearchContext) -> ExperimentResult:
    trades, markets = ctx.trades, ctx.markets
    per_market = trades.groupby("market_id", observed=True).agg(
        trades=("ts", "size"), wallets=("wallet", "nunique"), notional=("notional", "sum"),
        first_ts=("ts", "min"), last_ts=("ts", "max")).reset_index()
    per_market["market_id"] = per_market["market_id"].astype(str)
    table = markets.merge(per_market, on="market_id", how="left")
    table["close_date"] = pd.to_datetime(table["close_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    table["period"] = np.where(table["market_id"].isin(ctx.split["a_markets"]), "A", "B")

    wm = ctx.wallet_markets
    markets_per_wallet = wm.groupby("wallet")["market_id"].nunique()
    groups_per_wallet = wm.groupby("wallet")["group_id"].nunique()
    wallet_notional = trades.groupby("wallet", observed=True)["notional"].sum().sort_values(ascending=False)
    top1 = wallet_notional.head(max(1, len(wallet_notional) // 100)).sum() / wallet_notional.sum()

    repeat = pd.DataFrame({"min_markets": [1, 2, 3, 5, 10, 20]})
    repeat["wallets"] = [int((markets_per_wallet >= k).sum()) for k in repeat["min_markets"]]
    repeat["wallets_min_events"] = [int((groups_per_wallet >= k).sum()) for k in repeat["min_markets"]]

    fig, axes = plots.figure(10, 3.4, ncols=2)
    order = table.sort_values("close_ts")
    axes[0].bar(range(len(order)), order["trades"].fillna(0), color=[plots.ACCENT if p == "A" else plots.SECOND
                                                                     for p in order["period"]])
    axes[0].set_title("Trades per market (blue = period A, red = period B)")
    axes[0].set_xlabel("markets, by close date")
    axes[1].bar(repeat["min_markets"].astype(str), repeat["wallets"], color=plots.ACCENT, label="≥ k markets")
    axes[1].bar(repeat["min_markets"].astype(str), repeat["wallets_min_events"], color=plots.THIRD, alpha=0.8,
                label="≥ k events")
    axes[1].set_yscale("log")
    axes[1].set_title("Wallets active in at least k markets / events")
    axes[1].legend()

    to_date = lambda ts: datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    metrics = {
        "markets": int(len(markets)), "events": int(markets["group_id"].nunique()),
        "trades": int(len(trades)), "wallets": int(trades["wallet"].nunique()),
        "first_close": to_date(markets["close_ts"].min()), "last_close": to_date(markets["close_ts"].max()),
        "split_date": to_date(ctx.split["split_ts"]),
        "period_a_markets": len(ctx.split["a_markets"]), "period_b_markets": len(ctx.split["b_markets"]),
        "top_1pct_wallets_share_of_volume": float(top1),
        "wallets_with_5plus_markets": int((markets_per_wallet >= 5).sum()),
        "wallets_with_3plus_events": int((groups_per_wallet >= 3).sum()),
        "yes_resolution_rate": float(markets["outcome_yes"].mean()),
    }
    headline = (f"{metrics['markets']} markets in {metrics['events']} events, {metrics['trades']:,} trades by "
                f"{metrics['wallets']:,} wallets; {metrics['wallets_with_5plus_markets']:,} wallets traded 5+ markets "
                f"and the top 1% of wallets did {top1:.0%} of the volume.")
    columns = ["market_id", "question", "category", "group_id", "close_date", "period", "outcome_yes",
               "volume_usd", "trades", "wallets", "notional"]
    return ExperimentResult(
        id="e0", title="Dataset overview", verdict="descriptive", headline=headline,
        question="What does the data cover, and do enough wallets trade many markets to measure skill?",
        metrics=metrics, tables={"markets": table[columns], "wallet_repeat": repeat},
        figures={"coverage": fig},
        notes=["Trade rows are participant records: each fill appears once for every wallet in it.",
               f"Dataset source: {ctx.manifest.get('source', {}).get('kind')}"])
