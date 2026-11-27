"""E4 · H3: could a trader copy skilled wallets after a delay, pay costs, and still make money?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.markout import copy_backtest, first_per_hour
from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research import plots
from walletlens.research.context import ResearchContext
from walletlens.research.result import ExperimentResult


def _signals(trades: pd.DataFrame, tier: str, min_usd: float, band) -> pd.DataFrame:
    chosen = trades[(trades["tier"] == tier) & (trades["notional"] >= min_usd)
                    & (trades["yes_price"] >= band[0]) & (trades["yes_price"] <= band[1])]
    return first_per_hour(chosen.sort_values("ts"))


def run(ctx: ResearchContext) -> ExperimentResult:
    cfg = ctx.cfg
    trades = ctx.period_b_trades
    group = ctx.markets.set_index("market_id")["group_id"]
    rows, curves = [], {}
    for tier in ("top", "ranked_rest"):
        signals = _signals(trades, tier, cfg.signal_min_usd, cfg.signal_price_band)
        for delay in cfg.copy_delays_s:
            for cost in cfg.copy_costs:
                fills = copy_backtest(signals, ctx.markets, ctx.book, delay, cost, cfg.signal_price_band)
                per_market = fills.groupby("market_id")["return_per_dollar"].mean()
                stat = cluster_bootstrap_mean(per_market, per_market.index.map(group), cfg.bootstrap_draws, cfg.seed)
                rows.append({"tier": tier, "delay_s": delay, "cost": cost, "signals": len(signals),
                             "copies": len(fills), "markets": int(per_market.size), "events": stat["groups"],
                             "mean_return": stat["mean"], "low": stat["low"], "high": stat["high"],
                             "hit_rate": float(fills["won"].mean()) if len(fills) else np.nan,
                             "mean_entry_price": float(fills["entry_price"].mean()) if len(fills) else np.nan})
                if delay == max(cfg.copy_delays_s) and cost == min(cfg.copy_costs):
                    curves[tier] = fills.sort_values("entry_ts")
    table = pd.DataFrame(rows)
    main = table[(table["tier"] == "top") & (table["delay_s"] == max(cfg.copy_delays_s))
                 & (table["cost"] == min(cfg.copy_costs))].iloc[0]
    rest = table[(table["tier"] == "ranked_rest") & (table["delay_s"] == main["delay_s"])
                 & (table["cost"] == main["cost"])].iloc[0]
    passed = main["mean_return"] > 0 and main["low"] > 0
    verdict = "inconclusive" if main["events"] < 5 or main["markets"] < 10 else ("pass" if passed else "fail")

    fig, axes = plots.figure(10, 3.6, ncols=2)
    for colour, (tier, fills) in zip((plots.ACCENT, plots.MUTED), curves.items()):
        if len(fills):
            times = pd.to_datetime(fills["entry_ts"], unit="s")
            axes[0].plot(times, fills["return_per_dollar"].cumsum(), color=colour, lw=1.6,
                         label=f"copy {tier} ({len(fills)} trades)")
    axes[0].axhline(0, color=plots.MUTED, lw=1)
    axes[0].set_title(f"Cumulative profit, $1 per copy ({int(main['delay_s'] // 60)} min delay, "
                      f"{main['cost'] * 100:.0f}¢ cost)")
    axes[0].legend()
    axes[0].tick_params(axis="x", rotation=30)
    view = table[table["tier"] == "top"]
    labels = [f"{int(d // 60)}m / {c * 100:.0f}¢" for d, c in zip(view["delay_s"], view["cost"])]
    x = np.arange(len(view))
    axes[1].bar(x, view["mean_return"] * 100, color=plots.ACCENT, width=0.55)
    axes[1].errorbar(x, view["mean_return"] * 100,
                     yerr=[np.clip((view["mean_return"] - view["low"]) * 100, 0, None),
                           np.clip((view["high"] - view["mean_return"]) * 100, 0, None)],
                     fmt="none", ecolor=plots.INK, capsize=4)
    axes[1].axhline(0, color=plots.MUTED, lw=1)
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("mean return per $1 (%)")
    axes[1].set_title("Copying the top tier: delay / cost")

    headline = (f"Copying top-tier wallets {int(main['delay_s'] // 60)} min later with a {main['cost'] * 100:.0f}¢ cost returns "
                f"{main['mean_return']:+.1%} per $1 (95% CI {main['low']:+.1%} to {main['high']:+.1%}; "
                f"{int(main['copies'])} copies in {int(main['markets'])} markets) vs {rest['mean_return']:+.1%} for other ranked wallets.")
    return ExperimentResult(
        id="e4", title="Copy-trading backtest (H3)", verdict=verdict, headline=headline,
        question="After realistic delay and costs, does following skilled wallets make money?",
        metrics={"main": main.to_dict(), "baseline_rest": rest.to_dict()},
        tables={"backtest_grid": table}, figures={"copy_trading": fig},
        notes=[f"Signals: top-tier trades of at least ${cfg.signal_min_usd:.0f} with YES price in "
               f"{cfg.signal_price_band}, one per wallet/market/hour; entry at the last price after the delay "
               "plus the cost; held to resolution.",
               "Pass rule (pre-registered): 60-minute delay, 1¢ cost, mean > 0 with CI above 0."])
