"""C2 · G2: does flow from skilled wallets add to the Polymarket price?"""

from __future__ import annotations

import numpy as np

from walletlens.analytics.walkforward import daily_ic, r2_gain, walk_forward
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.crypto.context import CryptoContext


def run(ctx: CryptoContext) -> ExperimentResult:
    cfg = ctx.cfg
    panel = ctx.panel
    target = f"r_{cfg.main_horizon_min}"
    models = {"price": ["r_past", "u"], "price_flow": ["r_past", "u", "flow_all_s"],
              "price_flow_skill": ["r_past", "u", "flow_all_s", "flow_top_s"]}
    preds = walk_forward(panel, target, models, cfg.min_train_days)
    if len(preds):
        skill_gain = r2_gain(preds, target, "price_flow_skill", "price_flow", cfg.bootstrap_draws, cfg.seed_research)
        flow_gain = r2_gain(preds, target, "price_flow", "price", cfg.bootstrap_draws, cfg.seed_research)
    else:
        skill_gain = flow_gain = {"gain": np.nan, "low": np.nan, "high": np.nan, "days": 0}
    ic_top = daily_ic(panel[panel["flow_top"] != 0], "flow_top", target, cfg.bootstrap_draws, cfg.seed_research)

    # skill persistence among crypto wallets (style is weak here: markets open near 50/50)
    wm = ctx.built["wallet_markets"].sort_values("close_ts")
    cut = wm["close_ts"].quantile(0.5)
    a = wm[wm["close_ts"] <= cut].groupby("wallet")["edge"].agg(["size", "mean"])
    b = wm[wm["close_ts"] > cut].groupby("wallet")["edge"].agg(["size", "mean"])
    pairs = a.merge(b, left_index=True, right_index=True, suffixes=("_a", "_b"), how="inner")
    pairs = pairs[(pairs["size_a"] >= 10) & (pairs["size_b"] >= 10)]
    rho = float(pairs["mean_a"].rank().corr(pairs["mean_b"].rank())) if len(pairs) > 10 else float("nan")

    passed = np.isfinite(skill_gain["gain"]) and skill_gain["gain"] > 0 and skill_gain["low"] > 0
    verdict = "inconclusive" if skill_gain.get("days", 0) < 20 else ("pass" if passed else "fail")
    fig, axes = plots.figure(10, 3.6, ncols=2)
    if len(pairs):
        axes[0].scatter(pairs["mean_a"].rank(pct=True), pairs["mean_b"].rank(pct=True), s=5, alpha=0.4, color=plots.ACCENT)
        axes[0].set_title(f"Crypto wallets: edge rank, first vs second half (ρ = {rho:.2f}, n = {len(pairs)})")
        axes[0].set_xlabel("first half")
        axes[0].set_ylabel("second half")
    names = ["plain flow vs price", "skilled flow vs plain flow"]
    values = [flow_gain, skill_gain]
    x = np.arange(2)
    axes[1].bar(x, [v["gain"] * 100 for v in values], color=[plots.MUTED, plots.ACCENT], width=0.5)
    axes[1].errorbar(x, [v["gain"] * 100 for v in values],
                     yerr=[[max((v["gain"] - v["low"]) * 100, 0) for v in values],
                           [max((v["high"] - v["gain"]) * 100, 0) for v in values]], fmt="none", ecolor=plots.INK, capsize=4)
    axes[1].axhline(0, color=plots.MUTED, lw=1)
    axes[1].set_xticks(x, names)
    axes[1].set_ylabel("out-of-sample R² gain (%)")
    axes[1].set_title(f"Wallet flow, {cfg.main_horizon_min}-minute spot return")
    headline = (f"Skilled-wallet flow changes out-of-sample R² by {skill_gain['gain']:+.3%} beyond plain flow "
                f"(95% CI {skill_gain['low']:+.3%} to {skill_gain['high']:+.3%}); crypto wallet edge persistence ρ = {rho:.2f} "
                f"({len(pairs)} wallets).")
    return ExperimentResult(
        id="c2", title="G2 · Do skilled wallets lead?", verdict=verdict, headline=headline,
        question="Does net buying by wallets with a proven record (judged only on earlier markets) predict spot?",
        metrics={"skill_over_flow": skill_gain, "flow_over_price": flow_gain, "ic_top_flow": ic_top,
                 "persistence_rho": rho, "persistence_wallets": int(len(pairs))},
        tables={"wallet_pairs": pairs.reset_index()}, figures={"wallets": fig},
        notes=["Top tier = top 10% of shrunk edge among wallets with ≥ 5 resolved crypto markets before the trade.",
               "Pass rule: skilled flow's R² gain over plain flow > 0 with the 95% CI above 0."])
