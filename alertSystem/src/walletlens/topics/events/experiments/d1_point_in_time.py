"""D1 · Do V1, W3 and W5 hold without the hindsight "contested" filter (point-in-time watch rule)?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments import w3_early_warning
from walletlens.topics.events.experiments.w5_wallet_types import _follow
from walletlens.topics.events.panel import ratio_by_market
from walletlens.topics.events.wallet_context import BONFERRONI_TESTS


def v1_stat(pairs: pd.DataFrame, ctx) -> dict:
    wide = ratio_by_market(pairs, "abs_r_shock", "abs_r_normal")
    if len(wide) < 2:
        return {"mean": np.nan, "low": np.nan, "high": np.nan, "groups": int(len(wide))}
    return cluster_bootstrap_mean(wide["mapped"] - wide["placebo"], wide["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed)


def with_hours(ctx, hours, function):
    original = ctx.__dict__.get("hours")
    ctx.__dict__["hours"] = hours
    try:
        return function(ctx)
    finally:
        ctx.__dict__["hours"] = original


def run(ctx: DailyContext) -> ExperimentResult:
    pairs = ctx.watched["pairs"]
    v1 = v1_stat(pairs, ctx)
    volume = pairs.drop_duplicates("market_id")["volume_usd"]
    low_cut = volume.quantile(1 / 3)
    v1_low_volume = v1_stat(pairs[pairs["volume_usd"] <= low_cut], ctx)
    v1_research_only = v1_stat(pairs[pairs["market_id"].isin(set(ctx.markets["market_id"]))], ctx)
    v1_new_markets = v1_stat(pairs[~pairs["market_id"].isin(set(ctx.markets["market_id"]))], ctx)

    hours = ctx.watched_hours
    w3 = with_hours(ctx, hours, w3_early_warning.run).metrics
    later = hours[hours["ts"] >= ctx.split_ts]
    level = 1 - 0.05 / BONFERRONI_TESTS
    retail = _follow(later, "f_retail", ctx, 0.95)
    whale = _follow(later, "f_whale", ctx, level)
    checks = {"a_v1_all_candidates": bool(v1["mean"] > 0 and v1["low"] > 0),
              "b_w3_gain": bool(w3.get("low", np.nan) > 0),
              "c_w5_whale_above_retail": bool(whale["low"] > retail["mean"])}
    verdict = "pass" if all(checks.values()) else "fail"
    headline = (f"Without the hindsight filter ({v1['groups']} markets, watch rule): V1 {v1['mean']:+.2f}× "
                f"(CI {v1['low']:+.2f} to {v1['high']:+.2f}); W3 AUC gain {w3.get('gain', np.nan):+.3f} "
                f"(CI {w3.get('low', np.nan):+.3f} to {w3.get('high', np.nan):+.3f}); W5 whale {whale['mean'] * 100:+.2f} "
                f"(CI low {whale['low'] * 100:+.2f}) vs retail {retail['mean'] * 100:+.2f} points.")
    table = pd.DataFrame([{"slice": k, **v} for k, v in {
        "all candidates (watched)": v1, "research markets only": v1_research_only,
        "markets the hindsight filter dropped": v1_new_markets, "lowest-volume third": v1_low_volume}.items()])
    return ExperimentResult(
        id="d1", title="Point-in-time universe", verdict=verdict, headline=headline,
        question="Do the passed findings hold on every market the app could see at the time, not only hindsight-chosen ones?",
        metrics={"checks": checks, "v1": v1, "v1_slices": table.to_dict("records"), "w3": w3, "w5_whale": whale,
                 "w5_retail": retail, "watched_wallet_hours": int(len(hours)),
                 "low_volume_cut_usd": float(low_cut)},
        tables={"v1_slices": table},
        notes=["Watch rule: >= 24 h of history and probability 1 h earlier in 10-90%.",
               "Pass rule (pre-registered): (a) V1 CI > 0 on all candidates, (b) W3 gain CI > 0, (c) W5 whale CI above retail."])
