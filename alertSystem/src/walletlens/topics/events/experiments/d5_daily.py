"""D5 · Does the effect survive for someone who only looks once a day (daily resolution)?"""

from __future__ import annotations

from walletlens.research.result import ExperimentResult
from walletlens.topics.events.daily import DailyContext
from walletlens.topics.events.experiments.d1_point_in_time import v1_stat


def run(ctx: DailyContext) -> ExperimentResult:
    pairs = ctx.watched_daily["pairs"]
    stat = v1_stat(pairs, ctx)
    no_crypto = v1_stat(pairs[~pairs["groups"].str.contains("crypto")], ctx)
    verdict = "pass" if stat["mean"] > 0 and stat["low"] > 0 else "fail"
    headline = (f"Day level: on days a related market moves ≥ 10 points, related assets' daily move exceeds unrelated by "
                f"{stat['mean']:+.2f}× (CI {stat['low']:+.2f} to {stat['high']:+.2f}, {stat['groups']} markets); "
                f"without crypto-price markets {no_crypto['mean']:+.2f}× (CI {no_crypto['low']:+.2f} to {no_crypto['high']:+.2f}).")
    return ExperimentResult(id="d5", title="Daily resolution", verdict=verdict, headline=headline,
                            question="Is a once-a-day summary still informative?",
                            metrics={"main": stat, "without_crypto_price_markets": no_crypto},
                            notes=["Probability sampled at each asset's daily close (16:00 ET stocks, 00:00 UTC crypto).",
                                   "Pass rule: CI > 0. Not required to build; decides the daily digest."])
