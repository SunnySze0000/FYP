"""W5 · Whose buying does the probability follow next hour? Types and the team's behaviour clusters, head to head."""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import BONFERRONI_TESTS, WalletContext, mean_ci

MIN_FLOW_USD = 500
MAIN_TYPES = ("whale", "skilled", "new", "frequent")


def _follow(hours: pd.DataFrame, column: str, ctx: WalletContext, level: float) -> dict:
    use = hours[(hours[column].abs() >= MIN_FLOW_USD) & hours["dp_next"].notna()]
    if len(use) < 50:
        return {"mean": np.nan, "low": np.nan, "high": np.nan, "n": int(len(use)), "groups": 0}
    signed = np.sign(use[column]) * use["dp_next"]
    stat = mean_ci(signed, use["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    if level != 0.95:                       # widen to the Bonferroni level with the normal approximation
        half = (stat["high"] - stat["low"]) / 2 / 1.96 * 2.734      # z for a 99.375% two-sided interval
        stat = {**stat, "low": stat["mean"] - half, "high": stat["mean"] + half}
    return stat


def run(ctx: WalletContext) -> ExperimentResult:
    hours = ctx.hours
    later = hours[hours["ts"] >= ctx.split_ts]           # clusters are frozen on the earlier half
    level = 1 - 0.05 / BONFERRONI_TESTS
    baseline = _follow(later, "f_retail", ctx, 0.95)
    rows = [{"type": "retail (baseline)", **baseline}]
    for kind in MAIN_TYPES:
        rows.append({"type": kind, **_follow(later, f"f_{kind}", ctx, level)})
    for cluster in ctx.flows.clusters:
        rows.append({"type": f"cluster {cluster} (secondary)", **_follow(later, f"f_{cluster}", ctx, 0.95)})
    rows.append({"type": "same-owner groups (secondary)", **_follow(later, "f_linked", ctx, 0.95)})
    table = pd.DataFrame(rows)

    # head to head: every type's signed flow in one regression on the next-hour move
    columns = ["f_retail"] + [f"f_{k}" for k in MAIN_TYPES]
    q = later.dropna(subset=["dp_next"])
    q = q[(q[columns].abs() >= MIN_FLOW_USD).any(axis=1)]
    x = np.column_stack([np.ones(len(q))] + [np.sign(q[c]) * (q[c].abs() >= MIN_FLOW_USD) for c in columns])
    beta = np.linalg.lstsq(x, q["dp_next"].to_numpy(), rcond=None)[0] if len(q) > 100 else np.full(len(columns) + 1, np.nan)
    coefficients = dict(zip(["intercept"] + columns, np.round(beta * 100, 3).tolist()))   # points

    main = table[table["type"].isin(MAIN_TYPES)]
    beats = main[main["low"] > baseline["mean"]]
    verdict = "inconclusive" if baseline.get("groups", 0) < 30 else ("pass" if len(beats) else "fail")
    explanations = ctx.pipeline[1].get("cluster_explanations", {})

    fig, ax = plots.figure(9, 3.6)
    y = np.arange(len(table))
    ax.barh(y, table["mean"] * 100, color=[plots.MUTED] + [plots.ACCENT] * len(MAIN_TYPES)
            + [plots.THIRD] * (len(table) - 1 - len(MAIN_TYPES)))
    ax.errorbar(table["mean"] * 100, y, xerr=[np.clip((table["mean"] - table["low"]) * 100, 0, None),
                                              np.clip((table["high"] - table["mean"]) * 100, 0, None)],
                fmt="none", ecolor=plots.INK, capsize=3)
    ax.axvline(baseline["mean"] * 100, color=plots.INK, ls="--", lw=1)
    ax.set_yticks(y, table["type"])
    ax.set_xlabel("next-hour probability move in the flow's direction (points)")
    ax.set_title("Whose buying does the price follow? (later half, out of sample)")
    headline = (f"After retail buying the price follows {baseline['mean'] * 100:+.2f} points next hour. "
                + ("Beating that (Bonferroni CI above retail): " + ", ".join(
                    f"{r.type} {r.mean * 100:+.2f}" for r in beats.itertuples())
                   if len(beats) else "No wallet type beats retail: " + ", ".join(
                    f"{r.type} {r.mean * 100:+.2f}" for r in main.itertuples())) + ".")
    return ExperimentResult(
        id="w5", title="Whose buying leads?", verdict=verdict, headline=headline,
        question="Is there a wallet type (or behaviour cluster) whose buying the probability follows more than retail's?",
        metrics={"by_type": table.to_dict("records"), "regression_points": coefficients,
                 "cluster_explanations": explanations},
        tables={"by_type": table}, figures={"types": fig},
        notes=["Tested on the later half of the data only, since the behaviour clusters are fitted on the earlier half.",
               f"Pass rule (pre-registered): a main type ({', '.join(MAIN_TYPES)}) whose {level:.2%} CI lies above "
               "retail's mean. Behaviour clusters and same-owner groups (team pipeline) are reported as secondary."])
