"""V5 · Robustness checks for V2 and V3 (added 2026-11-27 after both passed narrowly).

1. Direction placebo: the V2 rule applied to *unrelated* assets should hit about 50%.
2. V2 without crypto-price markets, and by event group.
3. V3 head to head: does skilled-wallet flow predict the next hour better than everyone else's flow?
   (V3 only tested skilled flow against zero; general momentum would pass that too.)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.context import EventsContext
from walletlens.topics.events.experiments.v3_wallet_lead import MIN_FLOW_USD


def _hit_rate(pairs: pd.DataFrame, ctx: EventsContext) -> dict:
    p = pairs[pairs["direction_attempts"] > 0].groupby("market_id")[["direction_hits", "direction_attempts"]].sum()
    if p.empty:
        return {"hit_rate": np.nan, "low": np.nan, "high": np.nan, "markets": 0}
    stat = cluster_bootstrap_mean(p["direction_hits"] / p["direction_attempts"] - 0.5, p.index,
                                  ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    return {"hit_rate": 0.5 + stat["mean"], "low": 0.5 + stat["low"], "high": 0.5 + stat["high"], "markets": stat["groups"]}


def _wallet_head_to_head(ctx: EventsContext) -> dict:
    universe = ctx.universe
    if universe is None:
        return {}
    trades = universe.trades
    skill = universe.timeline.lookup(trades["wallet"].astype(str), trades["ts"])
    frame = pd.DataFrame({"m": trades["market_id"].astype(str).to_numpy(),
                          "h": (trades["ts"].to_numpy() // 3600 + 1) * 3600,
                          "s": (trades["yes_dir"] * trades["notional"]).to_numpy(), "top": skill["top"].to_numpy()})
    flows = frame.assign(top_flow=np.where(frame["top"], frame["s"], 0.0),
                         rest_flow=np.where(frame["top"], 0.0, frame["s"])) \
        .groupby(["m", "h"])[["top_flow", "rest_flow"]].sum().reset_index()
    prices = pd.concat([ctx.prices, universe.prices.astype({"market_id": str})]).drop_duplicates(["market_id", "ts"])
    rows = []
    for market, part in flows.groupby("m"):
        series = prices[prices["market_id"] == market].sort_values("ts")
        if len(series) < 10:
            continue
        t, v = series["ts"].to_numpy("int64"), series["yes_price"].to_numpy()
        now = np.searchsorted(t, part["h"].to_numpy(), side="right") - 1
        later = np.searchsorted(t, part["h"].to_numpy() + 3600, side="right") - 1
        ok = (now >= 0) & (later > now)
        rows.append(part.assign(dp=np.where(ok, v[np.clip(later, 0, None)] - v[np.clip(now, 0, None)], np.nan)))
    if not rows:
        return {}
    panel = pd.concat(rows)
    per = []
    for market, g in panel.groupby("m"):
        a = g[(g["top_flow"].abs() >= MIN_FLOW_USD) & g["dp"].notna()]
        b = g[(g["rest_flow"].abs() >= MIN_FLOW_USD) & g["dp"].notna()]
        if len(a) and len(b):
            per.append((market, float((np.sign(a["top_flow"]) * a["dp"]).mean()),
                        float((np.sign(b["rest_flow"]) * b["dp"]).mean())))
    per = pd.DataFrame(per, columns=["market_id", "top", "rest"])
    diff = cluster_bootstrap_mean(per["top"] - per["rest"], per["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    q = panel.dropna(subset=["dp"])
    q = q[(q["top_flow"].abs() >= MIN_FLOW_USD) | (q["rest_flow"].abs() >= MIN_FLOW_USD)]
    x = np.column_stack([np.ones(len(q)), np.sign(q["top_flow"]) * (q["top_flow"].abs() >= MIN_FLOW_USD),
                         np.sign(q["rest_flow"]) * (q["rest_flow"].abs() >= MIN_FLOW_USD)])
    beta, *_ = np.linalg.lstsq(x, q["dp"].to_numpy(), rcond=None)
    return {"per_market_top_minus_rest": diff, "markets": int(len(per)),
            "regression_points": {"skilled_flow": float(beta[1]), "other_flow": float(beta[2]), "hours": int(len(q))}}


def run(ctx: EventsContext) -> ExperimentResult:
    pairs = ctx.analysis["pairs"]
    mapped, placebo = pairs[pairs["kind"] == "mapped"], pairs[pairs["kind"] == "placebo"]
    checks = {
        "direction_mapped": _hit_rate(mapped, ctx),
        "direction_placebo": _hit_rate(placebo, ctx),
        "direction_mapped_without_crypto": _hit_rate(mapped[~mapped["groups"].str.contains("crypto")], ctx),
    }
    by_group = (mapped[mapped["direction_attempts"] > 0].assign(group=lambda f: f["groups"].str.split("|").str[0])
                .groupby("group")[["direction_hits", "direction_attempts"]].sum())
    by_group["hit_rate"] = by_group["direction_hits"] / by_group["direction_attempts"]
    wallets = _wallet_head_to_head(ctx)
    placebo_ok = checks["direction_placebo"]["low"] <= 0.5 <= checks["direction_placebo"]["high"]
    v2_holds = placebo_ok and checks["direction_mapped_without_crypto"]["low"] > 0.5
    head = wallets.get("per_market_top_minus_rest", {})
    skilled_better = bool(head) and head.get("low", -1) > 0
    headline = (f"V2 direction holds: placebo assets {checks['direction_placebo']['hit_rate']:.1%} (≈ 50% as it should be), "
                f"related assets without crypto-price markets {checks['direction_mapped_without_crypto']['hit_rate']:.1%}. "
                if v2_holds else "V2 direction does not survive the placebo / no-crypto checks. ")
    if head:
        headline += (f"V3: skilled minus other wallets' flow = {head['mean'] * 100:+.2f} points per market "
                     f"(CI {head['low'] * 100:+.2f} to {head['high'] * 100:+.2f}), so skilled wallets "
                     f"{'do' if skilled_better else 'do not'} move first beyond ordinary order-flow momentum.")
    return ExperimentResult(
        id="v5", title="Robustness of V2 and V3", verdict="pass" if v2_holds else "fail", headline=headline,
        question="Do the narrow V2/V3 passes survive placebo, subgroup and head-to-head checks?",
        metrics={**checks, "wallets": wallets, "v2_holds": v2_holds, "skilled_beat_others": skilled_better},
        tables={"direction_by_group": by_group.reset_index()},
        notes=["Added after V2 and V3 passed narrowly; reported as a robustness check, not a new pass rule.",
               "Verdict reflects V2 only; the wallet head-to-head is reported in the metrics and headline."])
