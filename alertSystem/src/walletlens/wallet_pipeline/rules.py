"""Stage 2: transparent hard rules applied to entities before clustering.

Every rule is a named, configurable threshold; an entity keeps the list of
rules it failed, so filtering is auditable and easy to change.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class RuleConfig:
    min_trades: int = 10
    min_active_days: int = 3
    min_total_notional_usd: float = 100.0
    max_duplicate_fraction: float = 0.05
    max_trades_per_active_day: float | None = 500.0   # very high-frequency bots / market makers
    min_markets_traded: int = 1


def apply_rules(features: pd.DataFrame, config: RuleConfig = RuleConfig()) -> pd.DataFrame:
    checks = {
        "fewer_than_min_trades": features["trades"] < config.min_trades,
        "fewer_than_min_active_days": features["active_days"] < config.min_active_days,
        "below_min_total_notional": features["total_notional_usd"] < config.min_total_notional_usd,
        "duplicate_fraction_above_max": features["duplicate_fraction"] > config.max_duplicate_fraction,
        "fewer_than_min_markets": features["markets_traded"] < config.min_markets_traded,
    }
    if config.max_trades_per_active_day is not None:
        checks["above_max_trades_per_active_day"] = features["trades_per_active_day"] > config.max_trades_per_active_day
    failed = pd.DataFrame(checks)
    out = features.copy()
    names = list(failed.columns)
    out["rule_failures"] = [";".join(n for n, bad in zip(names, row) if bad)
                            for row in failed.to_numpy(dtype=bool)]
    out["eligible"] = ~failed.any(axis=1)
    return out


def rule_counts(filtered: pd.DataFrame) -> dict:
    counts = {"entities": int(len(filtered)), "eligible": int(filtered["eligible"].sum())}
    for reasons in filtered["rule_failures"]:
        for reason in filter(None, reasons.split(";")):
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def config_dict(config: RuleConfig) -> dict:
    return asdict(config)
