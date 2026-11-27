"""W1 · Do assets react more to probability jumps that large wallets back?"""

from __future__ import annotations

import numpy as np

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import WalletContext, split_difference


def run(ctx: WalletContext) -> ExperimentResult:
    shocks = ctx.asset_shocks
    shocks = shocks[(shocks["abs_r_normal"] > 0) & (shocks["f_gross"] > 0)].copy()
    shocks["reaction"] = shocks["r"].abs() / shocks["abs_r_normal"]
    direction = np.sign(shocks["dp"])
    shocks["whale_backed"] = direction * shocks["f_whale"] > 0
    shocks["linked_backed"] = direction * shocks["f_linked"] > 0
    main = split_difference(shocks["reaction"], shocks["whale_backed"], shocks["market_id"],
                            ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    linked = split_difference(shocks["reaction"], shocks["linked_backed"], shocks["market_id"],
                              ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    passed = np.isfinite(main["diff"]) and main["low"] > 0
    verdict = "inconclusive" if main.get("markets", 0) < 30 or not np.isfinite(main["diff"]) else ("pass" if passed else "fail")
    fig, ax = plots.figure(6, 3.4)
    labels = ["whale-backed", "not whale-backed"]
    values = [main.get("mean_high_group", np.nan), main.get("mean_low_group", np.nan)]
    ax.bar(labels, values, color=[plots.ACCENT, plots.MUTED], width=0.5)
    ax.axhline(1, color=plots.INK, ls="--", lw=1)
    ax.set_ylabel("asset |return| ÷ its normal hour")
    ax.set_title("Asset reaction to a probability jump")
    headline = (f"Related assets react {main['diff']:+.2f}× (of a normal hour) more when large wallets back the jump "
                f"(95% CI {main['low']:+.2f} to {main['high']:+.2f}; {main['n_high']} vs {main['n_low']} jump-asset pairs, "
                f"{main['markets']} markets). Same-owner groups backing it: {linked['diff']:+.2f}× "
                f"(CI {linked['low']:+.2f} to {linked['high']:+.2f}).")
    return ExperimentResult(
        id="w1", title="Large-wallet confirmation", verdict=verdict, headline=headline,
        question="When a jump is pushed by trades of ≥ $5,000 in its direction, do the related assets move more?",
        metrics={"whale_backed": main, "same_owner_group_backed": linked}, figures={"confirmation": fig},
        notes=["Pass rule (pre-registered): whale-backed minus other jumps > 0, 95% CI above 0, resampling markets.",
               "Same-owner groups come from the team's sniper grouping; reported as secondary."])
