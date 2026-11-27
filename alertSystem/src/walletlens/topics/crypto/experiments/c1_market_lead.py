"""C1 · G1: does Polymarket's view beyond the spot path predict the next minutes of spot?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.walkforward import daily_ic, final_coefficients, r2_gain, walk_forward
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.crypto.context import CryptoContext


def lead_lag(ctx: CryptoContext, lags=range(-10, 11)) -> pd.DataFrame:
    """corr(change in Polymarket logit at t, spot return at t + lag). Positive lags = Polymarket first."""
    panel, spot = ctx.panel, ctx.built["spot"]
    rows = []
    for asset, part in panel.groupby("asset"):
        part = part.sort_values("ts")
        p = np.clip(part["p_mean"].to_numpy(), 0.01, 0.99)
        logit = np.log(p / (1 - p))
        ts = part["ts"].to_numpy("int64")
        consecutive = np.diff(ts, prepend=ts[0]) == 60
        dp = np.where(consecutive, np.diff(logit, prepend=logit[0]), np.nan)
        for lag in lags:
            start = spot.at(asset, ts + lag * 60)
            end = spot.at(asset, ts + (lag + 1) * 60)
            r = np.log(end / start)
            ok = np.isfinite(dp) & np.isfinite(r)
            rows.append({"asset": asset, "lag_min": lag, "corr": float(np.corrcoef(dp[ok], r[ok])[0, 1]) if ok.sum() > 30 else np.nan})
    return pd.DataFrame(rows)


def run(ctx: CryptoContext) -> ExperimentResult:
    cfg = ctx.cfg
    panel = ctx.panel
    results, ics = {}, {}
    for h in cfg.horizons_min:
        target = f"r_{h}"
        preds = walk_forward(panel, target, {"base": ["r_past"], "polymarket": ["r_past", "u"]}, cfg.min_train_days)
        results[h] = r2_gain(preds, target, "polymarket", "base", cfg.bootstrap_draws, cfg.seed_research) \
            if len(preds) else {"gain": np.nan, "low": np.nan, "high": np.nan, "days": 0}
        ics[h] = daily_ic(panel, "u", target, cfg.bootstrap_draws, cfg.seed_research)
    main = results[cfg.main_horizon_min]
    passed = np.isfinite(main["gain"]) and main["gain"] > 0 and main["low"] > 0
    verdict = "inconclusive" if main.get("days", 0) < 20 else ("pass" if passed else "fail")
    lags = lead_lag(ctx)
    coefficients = final_coefficients(panel, f"r_{cfg.main_horizon_min}", ["r_past", "u"])

    table = pd.DataFrame([{"horizon_min": h, **{f"r2_{k}": v for k, v in results[h].items()},
                           **{f"ic_{k}": v for k, v in ics[h].items()}} for h in cfg.horizons_min])
    fig, axes = plots.figure(10, 3.6, ncols=2)
    for colour, (asset, part) in zip(plots.SERIES, lags.groupby("asset")):
        axes[0].plot(part["lag_min"], part["corr"], marker="o", ms=3, color=colour, label=asset)
    axes[0].axvline(0, color=plots.MUTED, lw=1)
    axes[0].axhline(0, color=plots.MUTED, lw=1)
    axes[0].set_xlabel("spot return lag (minutes; > 0 = after the Polymarket move)")
    axes[0].set_title("Who moves first? corr(Δ Polymarket, spot return)")
    axes[0].legend()
    x = np.arange(len(table))
    axes[1].bar(x, table["r2_gain"] * 100, color=plots.ACCENT, width=0.5)
    axes[1].errorbar(x, table["r2_gain"] * 100, yerr=[np.clip((table["r2_gain"] - table["r2_low"]) * 100, 0, None),
                                                      np.clip((table["r2_high"] - table["r2_gain"]) * 100, 0, None)],
                     fmt="none", ecolor=plots.INK, capsize=4)
    axes[1].axhline(0, color=plots.MUTED, lw=1)
    axes[1].set_xticks(x, [f"{h} min" for h in table["horizon_min"]])
    axes[1].set_ylabel("out-of-sample R² gain (%)")
    axes[1].set_title("Adding Polymarket to a spot-only model")

    ic = ics[cfg.main_horizon_min]
    headline = (f"At {cfg.main_horizon_min} min, adding Polymarket's view changes out-of-sample R² by "
                f"{main['gain']:+.3%} (95% CI {main['low']:+.3%} to {main['high']:+.3%}, {main.get('days', 0)} test days); "
                f"daily rank correlation {ic['ic']:+.3f}.")
    return ExperimentResult(
        id="c1", title="G1 · Does Polymarket lead spot?", verdict=verdict, headline=headline,
        question="Beyond what the spot path already says, does the Polymarket price predict the next spot return?",
        metrics={"main": main, "ic_main": ic, "coefficients_full_sample": coefficients,
                 "peak_lead_lag": lags.loc[lags["corr"].abs().idxmax()].to_dict() if lags["corr"].notna().any() else {}},
        tables={"by_horizon": table, "lead_lag": lags}, figures={"lead": fig},
        notes=["Signal u = logit(Polymarket P(Up)) − logit(P(Up) implied by the spot path and recent volatility).",
               f"Walk-forward by day (≥ {cfg.min_train_days} training days); CI by resampling test days.",
               "Pass rule: R² gain > 0 with the 95% CI above 0 at the main horizon; < 20 test days = inconclusive."])
