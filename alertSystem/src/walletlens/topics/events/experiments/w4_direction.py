"""W4 · Is the next-hour direction hint more reliable when large wallets agree with the jump?"""

from __future__ import annotations

import numpy as np

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import WalletContext, mean_ci, split_difference


def run(ctx: WalletContext) -> ExperimentResult:
    shocks = ctx.asset_shocks.dropna(subset=["direction_hit"]).copy()
    shocks = shocks[shocks["f_gross"] > 0]
    agree = np.sign(shocks["dp"]) * shocks["f_whale"] > 0
    main = split_difference(shocks["direction_hit"], agree, shocks["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    agree_rate = mean_ci(shocks.loc[agree, "direction_hit"] - 0.5, shocks.loc[agree, "market_id"],
                         ctx.cfg.bootstrap_draws, ctx.cfg.seed) if agree.sum() else {}
    passed = np.isfinite(main["diff"]) and main["low"] > 0
    verdict = "inconclusive" if main.get("markets", 0) < 30 or not np.isfinite(main["diff"]) else ("pass" if passed else "fail")
    fig, ax = plots.figure(6, 3.4)
    ax.bar(["large wallets agree", "do not"], [main.get("mean_high_group", np.nan) * 100, main.get("mean_low_group", np.nan) * 100],
           color=[plots.ACCENT, plots.MUTED], width=0.5)
    ax.axhline(50, color=plots.INK, ls="--", lw=1)
    ax.set_ylabel("next-hour direction hit rate (%)")
    ax.set_title("Direction hint by large-wallet agreement")
    headline = (f"Direction hint hit rate {main.get('mean_high_group', np.nan):.1%} when large wallets agree vs "
                f"{main.get('mean_low_group', np.nan):.1%} otherwise (difference {main['diff'] * 100:+.1f} points, "
                f"95% CI {main['low'] * 100:+.1f} to {main['high'] * 100:+.1f}; {main['n_high']} vs {main['n_low']}).")
    return ExperimentResult(
        id="w4", title="Large wallets and the direction hint", verdict=verdict, headline=headline,
        question="Does V2's next-hour direction hint work better when large wallets push the jump?",
        metrics={"agree_vs_not": main, "agree_hit_rate_minus_half": agree_rate}, figures={"direction": fig},
        notes=["Pass rule (pre-registered): agree minus not-agree hit rate > 0 with the 95% CI above 0 (markets resampled)."])
