"""Everything experiments share, computed once and cached: the data, the period split,
the fair-value map fitted on period A, wallet-market edges and the point-in-time skill timeline."""

from __future__ import annotations

from functools import cached_property

import numpy as np
import pandas as pd

from walletlens import logs
from walletlens.analytics.calibration import FairValue, calibration_points, fit_fair_value
from walletlens.analytics.markout import PriceBook
from walletlens.analytics.skill import SkillTimeline, wallet_market_edges
from walletlens.config import Settings
from walletlens.data.build import load_dataset
from walletlens.data.schema import add_yes_terms

log = logs.get("context")


class ResearchContext:
    def __init__(self, settings: Settings, dataset: str):
        self.settings = settings
        self.cfg = settings.research
        data = load_dataset(settings, dataset)
        self.dataset = dataset
        self.manifest = data["manifest"]
        self.markets = data["markets"]
        self.prices = data["prices"]
        self.trades = add_yes_terms(data["trades"])
        log.info("loaded %s: %d markets, %d trades", dataset, len(self.markets), len(self.trades))

    # ---------------------------------------------------------------- period split
    @cached_property
    def split(self) -> dict:
        """Earlier half of events = period A, later half = period B (an event never straddles)."""
        groups = self.markets.groupby("group_id")["close_ts"].agg(["min", "max"]).sort_values("max")
        cut = int(np.ceil(len(groups) / 2))
        a_groups, b_groups = list(groups.index[:cut]), list(groups.index[cut:])
        split_ts = int(groups.loc[b_groups, "min"].min()) if b_groups else int(groups["max"].max()) + 1
        a = self.markets[self.markets["group_id"].isin(a_groups)]
        b = self.markets[self.markets["group_id"].isin(b_groups)]
        log.info("split: period A %d events / %d markets, period B %d events / %d markets",
                 len(a_groups), len(a), len(b_groups), len(b))
        return {"split_ts": split_ts, "a_markets": set(a["market_id"]), "b_markets": set(b["market_id"]),
                "a_groups": a_groups, "b_groups": b_groups}

    # ---------------------------------------------------------------- calibration
    @cached_property
    def price_series(self) -> pd.DataFrame:
        """Downloaded prices plus the hourly last trade price (fills gaps where no history was served)."""
        from walletlens.data.build import hourly_prices_from_trades
        combined = pd.concat([self.prices, hourly_prices_from_trades(self.trades)], ignore_index=True)
        return combined.astype({"market_id": str, "ts": "int64"}).sort_values(["market_id", "ts"])

    @cached_property
    def calibration_points(self) -> pd.DataFrame:
        return calibration_points(self.price_series, self.markets, self.cfg.calibration_horizons_days)

    @cached_property
    def fair(self) -> FairValue:
        points = self.calibration_points[self.calibration_points["market_id"].isin(self.split["a_markets"])]
        fair = fit_fair_value(points["yes_price"], points["outcome_yes"])
        log.info("fair value fitted on period A: %s", fair.to_dict())
        return fair

    # ---------------------------------------------------------------- skill
    @cached_property
    def wallet_markets(self) -> pd.DataFrame:
        table = wallet_market_edges(self.trades, self.markets, self.fair)
        log.info("wallet-market rows: %d (%d wallets)", len(table), table["wallet"].nunique())
        return table

    @cached_property
    def timeline(self) -> SkillTimeline:
        return SkillTimeline(self.wallet_markets, self.cfg.skill_shrinkage_markets,
                             self.cfg.min_prior_markets, self.cfg.top_fraction)

    @cached_property
    def book(self) -> PriceBook:
        return PriceBook(self.prices, self.trades)

    @cached_property
    def period_b_trades(self) -> pd.DataFrame:
        """Trades in period-B markets, each tagged with its wallet's skill *at that moment*."""
        trades = self.trades[self.trades["market_id"].astype(str).isin(self.split["b_markets"])]
        skill = self.timeline.lookup(trades["wallet"].astype(str), trades["ts"])
        out = pd.concat([trades.reset_index(drop=True), skill.reset_index(drop=True)], axis=1)
        out["tier"] = np.where(out["top"], "top", np.where(out["ranked"], "ranked_rest", "unranked"))
        group = self.markets.set_index("market_id")["group_id"]
        out["group_id"] = out["market_id"].astype(str).map(group).to_numpy()
        log.info("period B trades: %d (top tier %d)", len(out), int(out["top"].sum()))
        return out
