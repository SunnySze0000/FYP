"""W2 · Does who is behind a jump predict whether it sticks or snaps back over the next 24 hours?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import BONFERRONI_TESTS, WalletContext, split_difference


def run(ctx: WalletContext) -> ExperimentResult:
    hours = ctx.hours
    jumps = hours[hours["shock"] & (hours["f_gross"] > 0)].dropna(subset=["cont_24h"]).copy()
    direction = np.sign(jumps["dp"])
    jumps["continuation"] = direction * jumps["cont_24h"]            # > 0: kept going, < 0: snapped back
    gross = jumps["f_gross"].replace(0, np.nan)
    splits = {
        "large_wallets_behind": direction * jumps["f_whale"] > 0,
        "skilled_wallets_behind": direction * jumps["f_skilled"] > 0,
        "many_wallets": jumps["f_wallets"] >= jumps["f_wallets"].median(),
        "new_wallets_driven": (jumps["f_new_gross"] / gross) >= (jumps["f_new_gross"] / gross).median(),
    }
    level = 1 - 0.05 / BONFERRONI_TESTS
    rows = []
    for name, high in splits.items():
        stat = split_difference(jumps["continuation"], high, jumps["market_id"], ctx.cfg.bootstrap_draws, ctx.cfg.seed, level)
        rows.append({"split": name, **stat})
    extra = {}
    for name, column in (("same_owner_groups_behind", "f_linked"), ("filtered_out_wallets_behind", "f_filtered_out")):
        extra[name] = split_difference(jumps["continuation"], direction * jumps[column] > 0, jumps["market_id"],
                                       ctx.cfg.bootstrap_draws, ctx.cfg.seed, level)
        rows.append({"split": name + " (secondary)", **extra[name]})
    table = pd.DataFrame(rows)
    main = table.iloc[:4]
    significant = main[(main["low"] > 0) | (main["high"] < 0)]
    verdict = "inconclusive" if len(jumps) < 200 or main["diff"].isna().all() else ("pass" if len(significant) else "fail")
    base = float(jumps["continuation"].mean()) if len(jumps) else np.nan

    fig, ax = plots.figure(8, 3.6)
    x = np.arange(len(table))
    ax.bar(x, table["diff"] * 100, color=[plots.ACCENT] * 4 + [plots.MUTED] * (len(table) - 4), width=0.55)
    ax.errorbar(x, table["diff"] * 100, yerr=[np.clip((table["diff"] - table["low"]) * 100, 0, None),
                                              np.clip((table["high"] - table["diff"]) * 100, 0, None)],
                fmt="none", ecolor=plots.INK, capsize=4)
    ax.axhline(0, color=plots.MUTED, lw=1)
    ax.set_xticks(x, [s.replace("_", " ") for s in table["split"]], rotation=25, ha="right")
    ax.set_ylabel("extra 24 h continuation (points)")
    ax.set_title(f"Does the jump stick? (average jump continues {base * 100:+.1f} points)")
    best = table.iloc[:4].assign(abs_diff=lambda f: f["diff"].abs()).sort_values("abs_diff", ascending=False).iloc[0]
    headline = (f"{len(jumps)} jumps; on average they continue {base * 100:+.1f} points over 24 h. "
                + ("Significant (Bonferroni): " + "; ".join(f"{r.split.replace('_', ' ')} {r.diff * 100:+.1f} pts "
                                                            f"(CI {r.low * 100:+.1f} to {r.high * 100:+.1f})"
                                                            for r in significant.itertuples())
                   if len(significant) else f"No split is significant; largest is {best['split'].replace('_', ' ')} "
                                            f"{best['diff'] * 100:+.1f} pts (CI {best['low'] * 100:+.1f} to {best['high'] * 100:+.1f})."))
    return ExperimentResult(
        id="w2", title="Will the jump stick?", verdict=verdict, headline=headline,
        question="Do jumps backed by large, skilled, many or new wallets hold up better (or worse) over the next day?",
        metrics={"jumps": int(len(jumps)), "mean_continuation": base, "splits": table.to_dict("records")},
        tables={"splits": table}, figures={"persistence": fig},
        notes=[f"Pass rule (pre-registered): any of the four main splits with a {level:.2%} CI (Bonferroni for 4 tests) "
               "excluding 0, in either direction; a reliable 'likely to revert' label is as useful as 'likely to stick'.",
               "Same-owner groups and filtered-out wallets (team pipeline) are reported as secondary splits."])
