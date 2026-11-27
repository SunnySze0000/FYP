"""D6 · Is the effect broad across event types, not one lucky group?"""

from __future__ import annotations

import pandas as pd

from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.d1_point_in_time import v1_stat


def run(ctx: DailyContext) -> ExperimentResult:
    pairs = ctx.watched["pairs"].copy()
    pairs["group"] = pairs["groups"].str.split("|").str[0]
    rows = []
    for group, part in pairs.groupby("group"):
        stat = v1_stat(part, ctx)
        if stat.get("groups", 0) >= 10:
            rows.append({"group": group, **stat})
    by_group = pd.DataFrame(rows)
    leave_out = pd.DataFrame([{"left_out": g, **v1_stat(pairs[pairs["group"] != g], ctx)} for g in by_group["group"]])
    share = float((by_group["mean"] > 0).mean()) if len(by_group) else 0.0
    checks = {"half_of_groups_positive": share >= 0.5, "no_group_drives_it": bool((leave_out["low"] > 0).all())}
    verdict = "pass" if all(checks.values()) else "fail"
    headline = (f"Positive in {(by_group['mean'] > 0).sum()} of {len(by_group)} event groups ("
                + ", ".join(f"{r.group} {r.mean:+.2f}" for r in by_group.itertuples())
                + f"); leaving out any one group, the smallest lower CI is {leave_out['low'].min():+.2f}.")
    return ExperimentResult(id="d6", title="Generality across event types", verdict=verdict, headline=headline,
                            question="Does the effect hold across event types, not only one group?",
                            metrics={"checks": checks, "by_group": by_group.to_dict("records"),
                                     "leave_one_out": leave_out.to_dict("records")},
                            tables={"by_group": by_group, "leave_one_out": leave_out},
                            notes=["Pass rule (pre-registered): > 0 in >= half of groups with >= 10 markets; "
                                   "every leave-one-group-out CI > 0."])
