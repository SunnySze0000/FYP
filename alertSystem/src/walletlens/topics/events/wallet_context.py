"""Context and decision rule for the wallet directions W1-W5 (suite ``wallets``)."""

from __future__ import annotations

from functools import cached_property

import numpy as np
import pandas as pd

from walletlens import io, logs
from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.topics.events.context import EventsContext
from walletlens.topics.events.wallets import FlowBook, market_hours, tag_trades

log = logs.get("events.wallet_context")
BONFERRONI_TESTS = 4          # W2 and W5 each compare four splits / types


class WalletContext(EventsContext):
    def __init__(self, settings, dataset: str = "events"):
        super().__init__(settings, dataset)
        path = settings.paths.dataset(dataset) / "trades.pkl.gz"
        self.trades = io.read_table(path) if path.exists() else pd.DataFrame()
        log.info("event trades: %d", len(self.trades))

    @cached_property
    def split_ts(self) -> int:
        """Earlier half of the event markets (by close) fits the frozen behaviour clusters."""
        return int(self.markets["close_ts"].median())

    @cached_property
    def pipeline(self) -> tuple[pd.DataFrame, dict]:
        """The team's sniper grouping, hard rules and behaviour clustering, on trades before the split."""
        try:
            from walletlens.data.schema import add_yes_terms
            from walletlens.wallet_pipeline.adapter import run_pipeline
            return run_pipeline(add_yes_terms(self.trades), self.split_ts)
        except ImportError as error:              # scikit-learn missing: skip clusters, keep the rest
            log.warning("wallet pipeline skipped (%s); run `run.ps1 setup`", error)
            return pd.DataFrame(), {"skipped": str(error)}

    @cached_property
    def tagged(self) -> pd.DataFrame:
        return tag_trades(self.trades, self.markets, self.cfg, self.pipeline[0])

    @cached_property
    def flows(self) -> FlowBook:
        return FlowBook(self.tagged)

    @cached_property
    def hours(self) -> pd.DataFrame:
        panel = market_hours(self.prices, self.flows, self.cfg.shock_points)
        log.info("market-hour panel: %d hours, %d shocks", len(panel), int(panel["shock"].sum()) if len(panel) else 0)
        return panel

    @cached_property
    def hours_gap(self) -> pd.DataFrame:
        """Same panel with each hour's wallet flows ending 15 minutes before the hour (robustness)."""
        return market_hours(self.prices, self.flows, self.cfg.shock_points, gap_s=900)

    @cached_property
    def asset_shocks(self) -> pd.DataFrame:
        """V1/V2 shock rows (market x related asset) with the wallet flow of the shock hour attached."""
        shocks = self.analysis["shocks"]
        shocks = shocks[shocks["kind"] == "mapped"].copy()
        parts = []
        for market, part in shocks.groupby("market_id"):
            window = self.flows.window(market, part["ts"].to_numpy() - 3600, part["ts"].to_numpy())
            parts.append(pd.concat([part.reset_index(drop=True), window.add_prefix("f_")], axis=1))
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def split_difference(values: pd.Series, high: pd.Series, groups: pd.Series, draws: int, seed: int,
                     level: float = 0.95) -> dict:
    """mean(values | high) - mean(values | not high), CI by resampling groups (markets)."""
    frame = pd.DataFrame({"v": np.asarray(values, float), "h": np.asarray(high, bool), "g": np.asarray(groups)}).dropna()
    if frame["h"].sum() < 10 or (~frame["h"]).sum() < 10:
        return {"diff": np.nan, "low": np.nan, "high": np.nan, "n_high": int(frame["h"].sum()),
                "n_low": int((~frame["h"]).sum()), "markets": int(frame["g"].nunique())}
    keys = frame["g"].unique()
    index = {k: frame.index[frame["g"] == k].to_numpy() for k in keys}
    rng = np.random.default_rng(seed)
    v, h = frame["v"].to_numpy(), frame["h"].to_numpy()
    position = {i: n for n, i in enumerate(frame.index)}
    rows = {k: np.array([position[i] for i in idx]) for k, idx in index.items()}
    boot = []
    for _ in range(draws):
        pick = np.concatenate([rows[k] for k in rng.choice(keys, len(keys))])
        hh, vv = h[pick], v[pick]
        if hh.any() and (~hh).any():
            boot.append(vv[hh].mean() - vv[~hh].mean())
    alpha = (1 - level) / 2
    return {"diff": float(v[h].mean() - v[~h].mean()), "low": float(np.quantile(boot, alpha)),
            "high": float(np.quantile(boot, 1 - alpha)), "mean_high_group": float(v[h].mean()),
            "mean_low_group": float(v[~h].mean()), "n_high": int(h.sum()), "n_low": int((~h).sum()),
            "markets": int(len(keys))}


def mean_ci(values, groups, draws: int, seed: int) -> dict:
    return cluster_bootstrap_mean(pd.Series(values), pd.Series(groups), draws, seed)


def decide(verdicts: dict) -> str:
    useful = {"w1": "weight alerts by large-wallet backing", "w2": "label jumps likely to stick or revert by who is behind them",
              "w3": "early warning from unusual wallet activity", "w4": "sharpen the direction hint with large-wallet agreement",
              "w5": "highlight the wallet type whose buying leads the price"}
    passed = [k for k in ("w1", "w2", "w3", "w4", "w5") if verdicts.get(k) == "pass"]
    if verdicts.get("w0") != "pass":
        return "W0 failed: not enough wallet data in the event markets to test the wallet directions."
    if not passed:
        return "No wallet direction passed: keep wallets as descriptive context only (who is moving a market)."
    text = "Passed: " + "; ".join(f"{k.upper()} ({useful[k]})" for k in passed) + "."
    if verdicts.get("w6") == "fail":
        text += " W6 robustness: not all of them survive the 15-minute gap; only those listed in W6 go into the product."
    elif verdicts.get("w6") == "pass":
        text += " All survive the W6 robustness checks."
    return text
