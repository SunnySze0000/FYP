"""Project paths and every tunable parameter, in one place.

Parameters for the study are fixed *before* the research runs (see docs/01_topic.md).
A JSON file in ``config/`` may override them; every run copies the values it used into
its own ``results/<run_id>/manifest.json`` so results can always be traced back.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path


def project_root() -> Path:
    """Folder that holds ``src/``, ``data/`` and ``results/`` (override with WALLETLENS_HOME)."""
    env = os.environ.get("WALLETLENS_HOME")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path:          # untouched API responses
        return self.root / "data" / "raw"

    @property
    def interim(self) -> Path:      # cleaned per-market files
        return self.root / "data" / "interim"

    @property
    def processed(self) -> Path:    # analysis-ready tables, one folder per dataset
        return self.root / "data" / "processed"

    @property
    def results(self) -> Path:      # one folder per research run
        return self.root / "results"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def config(self) -> Path:
        return self.root / "config"

    def dataset(self, name: str) -> Path:
        return self.processed / name


@dataclass
class CollectConfig:
    """Which resolved markets to study and how to download them."""

    closed_from: str = "2025-01-01"          # market end date window (inclusive)
    closed_to: str = "2026-10-31"
    min_volume_usd: float = 100_000          # skip thin markets
    min_duration_days: float = 7             # skip very short markets (single games, 15-minute crypto)
    contested_low: float = 0.15              # "contested" = YES price spent time inside this band ...
    contested_high: float = 0.85
    min_contested_points: int = 3            # ... for at least this many 12-hour points
    sample_size: int = 300                   # markets drawn (in a fixed random order) from the contested set
    seed: int = 20261126
    trade_filter_type: str = "CASH"          # Data API trade filter: only trades worth >= amount
    trade_filter_amount: float = 50
    trade_page_size: int = 1000
    max_trade_pages: int = 100               # per market safety cap (recorded when hit)
    price_bucket_seconds: int = 3600         # hourly YES price for markouts
    screen_bucket_seconds: int = 43_200      # 12-hour price for the contested screen


@dataclass
class ResearchConfig:
    """Pre-registered analysis choices (docs/01_topic.md)."""

    calibration_horizons_days: tuple = (1, 7, 30)
    calibration_bins: int = 10
    skill_shrinkage_markets: float = 5       # shrunk skill = mean edge * n / (n + k)
    persistence_min_markets: int = 5         # per period, for H1 (pilot lowers it, see pilot config)
    top_fraction: float = 0.10               # "skilled" = top decile of prior shrunk skill
    min_prior_markets: int = 3               # a wallet needs this many resolved markets before it is ranked
    markout_horizons_s: tuple = (3600, 86_400)
    signal_min_usd: float = 100              # copy-trade signals: trades at least this big
    signal_price_band: tuple = (0.05, 0.95)  # skip trades with no room left
    copy_delays_s: tuple = (60, 3600)
    copy_costs: tuple = (0.01, 0.02)
    bootstrap_draws: int = 2000
    permutations: int = 1000
    seed: int = 7


@dataclass
class CryptoConfig:
    """Topic T1: Polymarket crypto up/down markets vs BTC/ETH spot."""

    closed_from: str = "2026-03-01"
    closed_to: str = "2026-11-20"
    min_volume_usd: float = 1_000
    assets: tuple = ("BTC", "ETH")
    per_kind: dict = field(default_factory=lambda: {"5m": 800, "15m": 800, "1h": 800, "4h": 300})
    seed: int = 20261126
    trade_filter_type: str = "CASH"
    trade_filter_amount: float = 5
    trade_page_size: int = 1000
    max_trade_pages: int = 25
    binance_data: str = "https://data.binance.vision"
    binance_api: str = "https://api.binance.com"
    # research (pre-registered in docs/00_PLAN.md)
    horizons_min: tuple = (5, 15, 60)
    main_horizon_min: int = 5
    lookback_min: int = 5
    vol_window_min: int = 60
    stale_min: int = 10                 # a Polymarket price older than this is not used
    min_train_days: int = 21
    signal_quantile: float = 0.9        # trade when |signal| is in the top 10% of the training days
    costs_bps: tuple = (5, 20)          # round trip
    delay_min: int = 1
    bootstrap_draws: int = 2000
    seed_research: int = 11


ASSET_GROUPS = {
    # keyword group -> assets that should react, used by topic T2
    "rates": ("TLT", "IEF", "SHY", "UUP", "XLF"),
    "macro": ("SPY", "TLT", "GLD", "IWM"),
    "trade_china": ("FXI", "KWEB", "EEM", "SPY"),
    "energy_mideast": ("USO", "XLE", "GLD"),
    "war_europe": ("ITA", "USO", "EZU", "GLD"),
    "us_politics": ("SPY", "IWM", "XLE", "ITA"),
    "crypto": ("BTC-USD", "ETH-USD", "COIN", "MSTR"),
    "ai_tech": ("NVDA", "SMH", "QQQ", "MSFT"),
}
GROUP_KEYWORDS = {
    # whole words; a trailing * also matches longer words ("iran*" -> "Iranian"). Fixed 2026-11-27 (D-fix-1):
    # plain substring matching linked "Borussia" to Russia, "Senators" to NATO and "Oilers" to oil.
    "rates": ("fed", "fomc", "interest rate*", "rate cut*", "rate hike*", "bps", "powell", "fed chair"),
    "macro": ("recession", "gdp", "cpi", "inflation", "unemployment", "jobs report", "nonfarm", "default"),
    "trade_china": ("tariff*", "china", "chinese", "xi jinping", "trade deal", "taiwan*"),
    "energy_mideast": ("oil", "crude", "opec", "iran*", "israel*", "saudi*", "hormuz", "gaza", "hezbollah", "houthi*"),
    "war_europe": ("russia*", "ukrain*", "putin", "zelensk*", "nato", "ceasefire"),
    "us_politics": ("trump", "senate", "house", "election", "shutdown", "impeach*", "supreme court", "governor"),
    "crypto": ("bitcoin", "btc", "ethereum", "eth", "crypto*", "stablecoin*", "sec", "solana", "etf*"),
    "ai_tech": ("nvidia", "openai", "ai", "gpt*", "chip*", "semiconductor*", "apple", "microsoft", "google"),
}


@dataclass
class EventsConfig:
    """Topic T2: Polymarket probability shocks -> asset returns (risk and hedging)."""

    max_markets: int = 1200
    max_per_group: int = 200
    history_days: int = 180             # hourly history over the last 180 days of each market's life
    price_bucket_seconds: int = 3600
    yahoo_hourly_range: str = "730d"
    yahoo_daily_range: str = "5y"
    extra_assets: tuple = ("QQQ", "^VIX", "VIXY", "HYG")
    shock_points: float = 0.10          # a probability move of at least 10 points in one hour
    trade_filter_amount: float = 250    # wallet study: trades of at least $250 in the event markets
    max_trade_pages: int = 30
    whale_trade_usd: float = 5_000      # wallet types (pre-registered in docs/04_wallet_directions.md)
    new_wallet_days: float = 3
    frequent_wallet_trades: int = 200
    min_markets_per_group: int = 10
    bootstrap_draws: int = 2000
    seed: int = 13


@dataclass
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    live_cache_seconds: int = 60


@dataclass
class Settings:
    paths: Paths
    collect: CollectConfig = field(default_factory=CollectConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    crypto: CryptoConfig = field(default_factory=CryptoConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    app: AppConfig = field(default_factory=AppConfig)

    def to_dict(self) -> dict:
        return {
            "root": str(self.paths.root),
            "collect": asdict(self.collect),
            "research": asdict(self.research),
            "crypto": asdict(self.crypto),
            "events": asdict(self.events),
            "app": asdict(self.app),
        }


def _apply(obj, overrides: dict) -> None:
    names = {f.name for f in fields(obj)}
    for key, value in overrides.items():
        if key not in names:
            raise KeyError(f"Unknown setting {type(obj).__name__}.{key}")
        current = getattr(obj, key)
        if isinstance(current, tuple):
            value = tuple(value)
        setattr(obj, key, value)


def load_settings(profile: str | None = None, root: Path | None = None) -> Settings:
    """Defaults, then ``config/<profile>.json`` if given (sections: collect, research, app)."""
    settings = Settings(paths=Paths(root or project_root()))
    if profile:
        path = settings.paths.config / f"{profile}.json"
        overrides = json.loads(path.read_text(encoding="utf-8"))
        for section, values in overrides.items():
            target = getattr(settings, section)
            if not is_dataclass(target):
                raise KeyError(f"Unknown config section {section}")
            _apply(target, values)
    return settings
