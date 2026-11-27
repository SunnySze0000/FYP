"""D4 · Live feasibility, read from the newest laptop run of ``python -m walletlens live-check``."""

from __future__ import annotations

from walletlens import io
from walletlens.research.result import ExperimentResult


def run(ctx) -> ExperimentResult:
    runs = sorted(ctx.settings.paths.results.glob("*_live_check/d4_live_check.json"))
    if not runs:
        return ExperimentResult(id="d4", title="Live feasibility", verdict="inconclusive",
                                headline="No live check found: double-click livecheck.bat on a machine with internet.",
                                question="Can the app get the live data it needs, fresh and fast enough?")
    r = io.read_json(runs[-1])
    headline = (f"{runs[-1].parent.name}: refresh {r['refresh_seconds']} s for {r['watched_markets']} watched markets; "
                f"median latest-trade age {r['median_trade_age_min'] if r['median_trade_age_min'] is None else round(r['median_trade_age_min'], 1)} min; "
                f"BTC bar age {r['btc_bar_age_min'] if r['btc_bar_age_min'] is None else round(r['btc_bar_age_min'], 1)} min; "
                f"sources {r['reachable']}.")
    return ExperimentResult(id="d4", title="Live feasibility", verdict=r["verdict"], headline=headline,
                            question="Can the app get the live data it needs, fresh and fast enough?",
                            metrics={k: v for k, v in r.items() if k not in ("markets", "assets")},
                            notes=["Pass rule (pre-registered): all sources reachable; median trade age <= 60 min; "
                                   "BTC bar <= 90 min; refresh <= 120 s."])
