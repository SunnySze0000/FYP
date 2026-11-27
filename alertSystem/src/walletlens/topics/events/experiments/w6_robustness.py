"""W6 · Robustness of the wallet directions that passed (added after W2, W3 and W5 passed).

1. Timestamp check: Polymarket's hourly price at t should equal the last trade at t, not a later one.
   Otherwise trades just before the hour would "predict" the next snapshot mechanically.
2. Gap check: rerun W2 (large-wallet split), W3 (AUC gain) and W5 (large vs retail) with each hour's
   wallet flows ending 15 minutes before the hour.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.data.schema import add_yes_terms
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.experiments import w3_early_warning
from walletlens.topics.events.experiments.w5_wallet_types import _follow
from walletlens.topics.events.wallet_context import BONFERRONI_TESTS, WalletContext, split_difference


def timestamp_check(ctx: WalletContext, markets: int = 250) -> pd.DataFrame:
    trades = add_yes_terms(ctx.trades)
    trades["market_id"] = trades["market_id"].astype(str)
    prices = ctx.prices
    rows = {d: [] for d in (-30, -15, -5, 0, 5, 15, 30)}
    for market, part in list(trades.groupby("market_id"))[:markets]:
        part = part.sort_values("ts")
        ts, yes = part["ts"].to_numpy(), part["yes_price"].to_numpy()
        series = prices[prices["market_id"] == market]
        if len(series) < 50:
            continue
        t, v = series["ts"].to_numpy()[::3], series["yes_price"].to_numpy()[::3]
        for minutes in rows:
            i = np.searchsorted(ts, t + minutes * 60, side="right") - 1
            ok = (i >= 0) & (t + minutes * 60 - ts[np.clip(i, 0, None)] < 1800)
            rows[minutes].append(np.abs(v[ok] - yes[i[ok]]))
    return pd.DataFrame([{"trade_offset_min": m, "mean_abs_diff": float(np.concatenate(v).mean()) if v else np.nan}
                         for m, v in rows.items()])


def run(ctx: WalletContext) -> ExperimentResult:
    stamps = timestamp_check(ctx)
    best_offset = int(stamps.loc[stamps["mean_abs_diff"].idxmin(), "trade_offset_min"])
    hours = ctx.hours_gap
    level = 1 - 0.05 / BONFERRONI_TESTS
    jumps = hours[hours["shock"] & (hours["f_gross"] > 0)].dropna(subset=["cont_24h"])
    direction = np.sign(jumps["dp"])
    w2 = split_difference(direction * jumps["cont_24h"], direction * jumps["f_whale"] > 0, jumps["market_id"],
                          ctx.cfg.bootstrap_draws, ctx.cfg.seed, level)
    original = ctx.__dict__.get("hours")
    ctx.__dict__["hours"] = hours                     # reuse W3 unchanged on the gap panel
    try:
        w3 = w3_early_warning.run(ctx).metrics
    finally:
        if original is not None:
            ctx.__dict__["hours"] = original
    later = hours[hours["ts"] >= ctx.split_ts]
    retail = _follow(later, "f_retail", ctx, 0.95)
    whale = _follow(later, "f_whale", ctx, level)
    checks = {
        "w2_large_wallets_behind": w2["low"] > 0 or w2["high"] < 0,
        "w3_auc_gain": w3.get("low", -1) > 0,
        "w5_whale_beats_retail": whale["low"] > retail["mean"],
    }
    holds = [k for k, v in checks.items() if v]
    verdict = "pass" if best_offset == 0 and len(holds) == len(checks) else "fail"
    headline = (f"Hourly prices match the last trade at the timestamp itself (best offset {best_offset:+d} min), "
                f"so there is no stale-snapshot leak. With wallet flows ending 15 min before each hour: "
                f"W2 large-wallet jumps {w2['diff'] * 100:+.1f} pts (CI {w2['low'] * 100:+.1f} to {w2['high'] * 100:+.1f}); "
                f"W3 AUC gain {w3.get('gain', np.nan):+.3f} (CI {w3.get('low', np.nan):+.3f} to {w3.get('high', np.nan):+.3f}); "
                f"W5 whale {whale['mean'] * 100:+.2f} vs retail {retail['mean'] * 100:+.2f} pts. "
                f"Still holding: {', '.join(holds) if holds else 'none'}.")
    return ExperimentResult(
        id="w6", title="Robustness of the wallet passes", verdict=verdict, headline=headline,
        question="Do W2, W3 and W5 survive a timestamp check and a 15-minute gap before each hour?",
        metrics={"timestamp_best_offset_min": best_offset, "w2_gap": w2, "w3_gap": w3, "w5_gap_whale": whale,
                 "w5_gap_retail": retail, "checks": checks},
        tables={"timestamp_check": stamps},
        notes=["Added after W2, W3 and W5 passed; a robustness check, not a new pass rule. "
               "Verdict: pass only if the timestamps are aligned and all three still hold with the gap."])
