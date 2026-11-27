"""T1 research context and the pre-registered decision rule."""

from __future__ import annotations

from functools import cached_property

from walletlens import logs
from walletlens.config import Settings
from walletlens.topics.crypto.build import load_crypto
from walletlens.topics.crypto.panel import build_panel

log = logs.get("crypto.context")


class CryptoContext:
    def __init__(self, settings: Settings, dataset: str = "crypto"):
        self.settings = settings
        self.cfg = settings.crypto
        self.research = settings.research
        data = load_crypto(settings, dataset)
        self.markets, self.trades, self.spot, self.manifest = data["markets"], data["trades"], data["spot"], data["manifest"]
        log.info("crypto data: %d markets, %d trades, %d spot minutes", len(self.markets), len(self.trades), len(self.spot))

    @cached_property
    def built(self) -> dict:
        return build_panel(self.markets, self.trades, self.spot, self.cfg, self.research.top_fraction,
                           min_prior_markets=5, k=self.research.skill_shrinkage_markets)

    @property
    def panel(self):
        return self.built["panel"]

    def describe(self) -> dict:
        built = self.__dict__.get("built")
        return {"window_shifts_s": built["shifts"]} if built else {}


def decide(verdicts: dict) -> str:
    g0, g1, g2, g3 = (verdicts.get(k) for k in ("c0", "c1", "c2", "c3"))
    if g0 != "pass":
        return "G0 failed: not enough aligned data to test T1. Fix the data (see C0) before judging the topic."
    if g1 == "pass" and g3 == "pass":
        extra = " Skilled-wallet flow adds to it (G2 passed)." if g2 == "pass" else " Wallet flow adds nothing beyond the price (G2 not passed)."
        return "T1 works: build a BTC/ETH signal tool from the Polymarket lead." + extra
    if g1 == "pass" or g2 == "pass":
        return ("T1 partly works: Polymarket carries information about the next minutes of spot, but not enough "
                "to trade after costs. Build an insight/risk view, or test T2 next.")
    return "T1 fails: Polymarket crypto markets do not lead spot. Move to T2 (event shocks -> assets)."
