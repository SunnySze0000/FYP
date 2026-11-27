"""D3 · Is an alert informative, and how many would a user get per day?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.config import ASSET_GROUPS
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import BIG_QUANTILE, PORTFOLIO, DailyContext


def run(ctx: DailyContext) -> ExperimentResult:
    shocks = ctx.watched["shocks"]
    per = shocks.pivot_table(index="market_id", columns="kind", values="big", aggfunc="mean").dropna()
    value = cluster_bootstrap_mean(per["mapped"] - per["placebo"], per.index.to_series(), ctx.cfg.bootstrap_draws, ctx.cfg.seed)
    mapped_rate, placebo_rate = float(per["mapped"].mean()), float(per["placebo"].mean())

    alerts = ctx.alerts
    in_portfolio = lambda g: any(a in PORTFOLIO for grp in str(g).split("|") for a in ASSET_GROUPS.get(grp, ()))
    alerts = alerts[alerts["groups"].map(in_portfolio)]
    end = int(alerts["ts"].max())
    window = alerts[alerts["ts"] > end - 180 * 86_400].copy()
    window["day"] = pd.to_datetime(window["ts"], unit="s").dt.floor("D")
    days = pd.date_range(window["day"].min(), window["day"].max(), freq="D")
    per_day = window[~window["quiet"]].groupby("day")["market_id"].nunique().reindex(days, fill_value=0)
    watched_per_day = window.groupby("day")["market_id"].nunique().reindex(days, fill_value=0)
    share_days = float((per_day >= 1).mean())
    p95 = float(per_day.quantile(0.95))
    checks = {"a_alert_value": bool(value["mean"] > 0 and value["low"] > 0),
              "b_load_some_days": share_days >= 0.5, "b_load_not_spam": p95 <= 30}
    verdict = "pass" if all(checks.values()) else "fail"

    fig, ax = plots.figure(9, 3.2)
    ax.bar(per_day.index, per_day.to_numpy(), color=plots.ACCENT, width=1.0)
    ax.set_ylabel("markets alerting")
    ax.set_title("Alerts per day for SPY/QQQ/TLT/GLD/USO/BTC holders (last 180 days of data)")
    headline = (f"An alert is followed by a big move (top {100 - BIG_QUANTILE * 100:.0f}% of the asset's hours) "
                f"{mapped_rate:.0%} of the time for related assets vs {placebo_rate:.0%} for unrelated ones "
                f"(difference {value['mean'] * 100:+.1f} points, CI {value['low'] * 100:+.1f} to {value['high'] * 100:+.1f}). "
                f"Reference portfolio: at least one alert on {share_days:.0%} of days, median {per_day.median():.0f}/day, "
                f"95th percentile {p95:.0f}/day.")
    return ExperimentResult(
        id="d3", title="Alert value and load", verdict=verdict, headline=headline,
        question="Does an alert carry information, and would a daily user get a usable number of them?",
        metrics={"checks": checks, "value": value, "mapped_big_rate": mapped_rate, "placebo_big_rate": placebo_rate,
                 "share_days_with_alert": share_days, "median_per_day": float(per_day.median()), "p95_per_day": p95,
                 "mean_watched_markets_per_day": float(watched_per_day.mean()),
                 "window": [str(days[0].date()), str(days[-1].date())]},
        tables={"alerts_per_day": pd.DataFrame({"day": days.date, "alerts": per_day.to_numpy(),
                                                "watched_markets": watched_per_day.to_numpy()})},
        figures={"alerts_per_day": fig},
        notes=["Counts are a lower bound: only a sample of markets was collected (limitation L5).",
               "Pass rule (pre-registered): big-move rate mapped − placebo CI > 0; >= 1 alert on >= 50% of days; "
               "95th percentile <= 30 alerts/day."])
