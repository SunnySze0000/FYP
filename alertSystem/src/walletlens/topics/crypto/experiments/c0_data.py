"""C0 · G0: is there enough correctly aligned data to test T1?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.crypto.context import CryptoContext

MIN_MARKETS = 500
MIN_AGREEMENT = 0.95


def run(ctx: CryptoContext) -> ExperimentResult:
    built = ctx.built
    markets, panel, alignment = built["markets"], built["panel"], built["alignment"]
    trades_per_market = ctx.trades.groupby("market_id", observed=True).size()
    with_trades = int((trades_per_market > 0).sum())
    shifted = alignment.merge(pd.DataFrame([{"key": k, "chosen": v} for k, v in built["shifts"].items()]),
                              left_on=alignment["asset"] + "-" + alignment["kind"], right_on="key", how="left")
    chosen = shifted[shifted["shift_s"] == shifted["chosen"]]
    weighted = float((chosen["agreement_clear"] * chosen["clear_markets"]).sum() / max(chosen["clear_markets"].sum(), 1))
    weighted_all = float((chosen["agreement"] * chosen["markets"]).sum() / max(chosen["markets"].sum(), 1))
    coverage = panel.groupby(["asset"]).agg(minutes=("ts", "size"), days=("day", "nunique"),
                                            mean_markets=("markets", "mean")).reset_index()
    by_kind = markets.groupby(["asset", "kind"]).size().rename("markets").reset_index()
    passed = with_trades >= MIN_MARKETS and weighted >= MIN_AGREEMENT and len(panel) > 0

    fig, axes = plots.figure(10, 3.4, ncols=2)
    labels = [f"{a} {k}" for a, k in zip(by_kind["asset"], by_kind["kind"])]
    axes[0].bar(labels, by_kind["markets"], color=plots.ACCENT)
    axes[0].set_title("Markets with trades, by asset and window")
    axes[0].tick_params(axis="x", rotation=30)
    if len(panel):
        sample = panel.sample(min(len(panel), 20_000), random_state=0)
        axes[1].scatter(sample["q_mean"], sample["p_mean"], s=2, alpha=0.25, color=plots.ACCENT)
        axes[1].plot([0, 1], [0, 1], color=plots.MUTED, ls="--", lw=1)
        axes[1].set_xlabel("P(Up) implied by spot path so far")
        axes[1].set_ylabel("Polymarket P(Up)")
        axes[1].set_title("Polymarket vs spot-implied probability")

    metrics = {"markets_sampled": int(len(markets)), "markets_with_trades": with_trades,
               "trades": int(len(ctx.trades)), "wallets": int(ctx.trades["wallet"].nunique()) if len(ctx.trades) else 0,
               "panel_minutes": int(len(panel)), "panel_days": int(panel["day"].nunique()) if len(panel) else 0,
               "outcome_vs_spot_agreement": weighted, "agreement_including_near_ties": weighted_all,
               "window_shifts_s": built["shifts"],
               "corr_p_q": float(np.corrcoef(panel["p_mean"], panel["q_mean"])[0, 1]) if len(panel) > 2 else float("nan")}
    headline = (f"{with_trades} markets with trades, {len(panel):,} asset-minutes over {metrics['panel_days']} days; "
                f"resolution matches Binance spot in {weighted:.1%} of markets that moved ≥ 2 bps "
                f"({weighted_all:.1%} including near-ties).")
    return ExperimentResult(
        id="c0", title="G0 · Data and alignment", verdict="pass" if passed else "fail", headline=headline,
        question="Do we have enough crypto markets, and do their windows line up with the spot candles?",
        metrics=metrics, tables={"alignment": alignment, "coverage": coverage, "by_kind": by_kind},
        figures={"data": fig},
        notes=[f"Pass rule: ≥ {MIN_MARKETS} markets with trades and ≥ {MIN_AGREEMENT:.0%} agreement between the "
               "resolution and Binance close ≥ open over the market window, on markets whose spot move was at least "
               "2 bps (some markets settle on Chainlink prices, so exact ties can differ).",
               "A window shift is applied only if it beats the documented window by 5+ points of agreement."])
