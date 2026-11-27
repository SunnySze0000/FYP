"""E1 · H0: are prices calibrated, and does a fair-value map fitted on period A help in period B?"""

from __future__ import annotations

import numpy as np

from walletlens.analytics.calibration import brier, calibration_table, log_loss
from walletlens.research import plots
from walletlens.research.context import ResearchContext
from walletlens.research.result import ExperimentResult


def run(ctx: ResearchContext) -> ExperimentResult:
    points = ctx.calibration_points
    table = calibration_table(points, ctx.cfg.calibration_bins)
    scores = brier(points)
    fair = ctx.fair
    test = points[points["market_id"].isin(ctx.split["b_markets"])]
    market_loss = log_loss(test["yes_price"], test["outcome_yes"])
    fair_loss = log_loss(fair(test["yes_price"]), test["outcome_yes"])

    fig, axes = plots.figure(10, 3.8, ncols=2)
    axes[0].plot([0, 1], [0, 1], color=plots.MUTED, lw=1, ls="--", label="perfect")
    for colour, (horizon, part) in zip(plots.SERIES, table.groupby("horizon_days")):
        axes[0].errorbar(part["mean_price"], part["yes_rate"],
                         yerr=[np.clip(part["yes_rate"] - part["yes_rate_low"], 0, None),
                               np.clip(part["yes_rate_high"] - part["yes_rate"], 0, None)],
                         color=colour, marker="o", ms=4, lw=1.2, capsize=2, label=f"{horizon} d before close")
    axes[0].set_xlabel("market YES price")
    axes[0].set_ylabel("share that resolved YES")
    axes[0].set_title("Reliability: price vs outcome")
    axes[0].legend()
    grid = np.linspace(0.01, 0.99, 99)
    axes[1].plot(grid, grid, color=plots.MUTED, lw=1, ls="--", label="price")
    axes[1].plot(grid, fair(grid), color=plots.ACCENT, lw=2, label=f"fair value (a={fair.a:.2f}, b={fair.b:.2f})")
    axes[1].set_xlabel("market YES price")
    axes[1].set_ylabel("fair probability")
    axes[1].set_title("Fair-value map (fitted on period A)" if fair.fitted else "Fair value = price (too little data)")
    axes[1].legend()

    gaps = table.assign(abs_gap=table["gap"].abs())
    weighted_gap = float((gaps["abs_gap"] * gaps["n"]).sum() / gaps["n"].sum()) if len(gaps) else float("nan")
    metrics = {
        "points": int(len(points)), "markets": int(points["market_id"].nunique()),
        "mean_abs_gap": weighted_gap,
        "brier_by_horizon": {f"{r.horizon_days}d": float(r.brier) for r in scores.itertuples()},
        "fair_value": fair.to_dict(),
        "period_b_logloss_market": market_loss, "period_b_logloss_fair": fair_loss,
        "period_b_logloss_improvement": market_loss - fair_loss,
    }
    if fair.fitted:
        better = fair_loss < market_loss
        headline = (f"Prices are off by {weighted_gap:.1%} on average across buckets; the fair-value map "
                    f"(b = {fair.b:.2f}) {'improves' if better else 'does not improve'} period-B log loss "
                    f"({market_loss:.4f} → {fair_loss:.4f}).")
    else:
        headline = (f"Only {fair.n} period-A calibration points (< 100): fair value is the market price itself. "
                    f"Average bucket gap {weighted_gap:.1%}.")
    return ExperimentResult(
        id="e1", title="Calibration and fair value (H0)", verdict="descriptive", headline=headline,
        question="Do YES prices match how often YES happens, and can a simple recalibration improve them?",
        metrics=metrics, tables={"reliability": table, "brier": scores}, figures={"calibration": fig},
        notes=["Fair value is fitted on period A only and used for every edge measure in E2–E4.",
               "Points from different horizons of the same market are not independent."])
