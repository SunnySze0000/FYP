"""T2 research context and the pre-registered decision rule."""

from __future__ import annotations

from functools import cached_property

from walletlens import logs
from walletlens.config import Settings
from walletlens.topics.events.build import load_events
from walletlens.topics.events.panel import analyse

log = logs.get("events.context")


class EventsContext:
    def __init__(self, settings: Settings, dataset: str = "events"):
        self.settings = settings
        self.cfg = settings.events
        data = load_events(settings, dataset)
        self.markets, self.prices = data["markets"], data["prices"]
        self.hourly, self.daily, self.manifest = data["assets_hourly"], data["assets_daily"], data["manifest"]
        log.info("events data: %d markets, %d price points, %d asset series", len(self.markets), len(self.prices),
                 self.hourly["symbol"].nunique())

    @cached_property
    def analysis(self) -> dict:
        return analyse(self.markets, self.prices, self.hourly, self.cfg)

    @cached_property
    def universe(self):
        """Topic F's dataset (trades + wallet skill), if it has been collected."""
        from walletlens.research.context import ResearchContext
        if not (self.settings.paths.dataset("universe") / "manifest.json").exists():
            return None
        return ResearchContext(self.settings, "universe")


def decide(verdicts: dict) -> str:
    v0, v1, v2, v3 = verdicts.get("v0"), verdicts.get("v1"), verdicts.get("v2"), verdicts.get("v3")
    v5 = verdicts.get("v5")
    if v0 != "pass":
        return "V0 failed: not enough event markets with hourly prices to test T2. Fix the data before judging."
    if v1 != "pass":
        return ("T2 fails: event shocks do not move the mapped assets more than unrelated ones. "
                "Fall back to topic F (smart money inside Polymarket).")
    parts = ["T2 works as a risk tool: Polymarket shocks move the assets they relate to (event exposure monitor)."]
    if v2 == "pass" and v5 != "fail":
        parts.append("Shocks also lean on the next hour's direction (weak; see V5): show it as a hint, not a signal.")
    else:
        parts.append("No reliable next-hour directional lead: risk view only, no trade signals.")
    if v3 == "pass":
        parts.append("Prices keep moving with net wallet flow; whether *skilled* wallets add to that is checked in V5.")
    return " ".join(parts)
