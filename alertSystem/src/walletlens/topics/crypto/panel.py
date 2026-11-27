"""Minute-by-minute panel for T1.

For every asset and every minute ``t`` inside at least one sampled market's candle window:

* ``S(t)``      spot price = open of the 1-minute candle starting at t (known at t)
* ``p``         latest Polymarket P(Up) from trades strictly before t (not older than ``stale_min``)
* ``q``         P(Up) implied by spot alone: Phi( ln(S(t)/S(start)) / (sigma * sqrt(minutes left)) ),
                with sigma the per-minute volatility of the previous ``vol_window_min`` minutes
* ``u``         logit(p) - logit(q): what Polymarket "knows" beyond the spot path so far
                (averaged over all active markets of the asset)
* ``r_past``    ln S(t)/S(t - lookback)
* ``r_<h>``     ln S(t+h)/S(t): the future return to predict
* ``flow_top``  net Up-dollars traded by top-tier wallets in [t - lookback, t)   (point-in-time skill)
* ``flow_all``  the same for every wallet
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from walletlens import logs
from walletlens.analytics.calibration import FairValue
from walletlens.analytics.skill import SkillTimeline, wallet_market_edges
from walletlens.config import CryptoConfig
from walletlens.data.schema import add_yes_terms

log = logs.get("crypto.panel")
EPS = 0.01


def _norm_cdf(x):
    x = np.asarray(x, float)
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def _logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


class SpotSeries:
    """Per-asset minute grid of opens (and closes), forward-filled across missing minutes."""

    def __init__(self, spot: pd.DataFrame):
        self.series, self.closes = {}, {}
        for asset, part in spot.groupby("asset"):
            part = part.sort_values("ts")
            start, end = int(part["ts"].iloc[0]), int(part["ts"].iloc[-1])
            grid = np.arange(start, end + 60, 60)
            values = pd.Series(part["open"].to_numpy(), index=part["ts"].to_numpy()).reindex(grid).ffill()
            closes = pd.Series(part["close"].to_numpy(), index=part["ts"].to_numpy()).reindex(grid).ffill()
            self.series[asset] = (start, values.to_numpy())
            self.closes[asset] = (start, closes.to_numpy())

    def close_before(self, asset: str, ts) -> np.ndarray:
        """Close of the 1-minute candle that ends at ``ts`` (Binance's definition of a window's close)."""
        ts = np.asarray(ts, "int64") - 60
        if asset not in self.closes:
            return np.full(len(ts), np.nan)
        start, values = self.closes[asset]
        index = (ts - start) // 60
        ok = (index >= 0) & (index < len(values))
        out = np.full(len(ts), np.nan)
        out[ok] = values[index[ok]]
        return out

    def at(self, asset: str, ts) -> np.ndarray:
        ts = np.asarray(ts, "int64")
        if asset not in self.series:
            return np.full(len(ts), np.nan)
        start, values = self.series[asset]
        index = (ts - start) // 60
        ok = (index >= 0) & (index < len(values))
        out = np.full(len(ts), np.nan)
        out[ok] = values[index[ok]]
        return out

    def log_returns(self, asset: str) -> tuple[int, np.ndarray]:
        start, values = self.series[asset]
        return start, np.diff(np.log(values), prepend=np.nan)


def check_alignment(markets: pd.DataFrame, spot: SpotSeries) -> tuple[pd.DataFrame, dict]:
    """Does 'Up' match spot(close) >= spot(open) over the assumed window? Try shifts if not.

    Returns per-kind agreement for each shift and the best shift (seconds) per kind.
    """
    rows, best = [], {}
    for (asset, kind), part in markets.groupby(["asset", "kind"]):
        length = int((part["window_end"] - part["window_start"]).median())
        candidates = sorted({0, 3600, -3600, 4 * 3600, -4 * 3600, 5 * 3600, -5 * 3600, length, -length,
                             900, -900, 60, -60})
        for shift in candidates:
            start = part["window_start"].to_numpy("int64") + shift
            end = part["window_end"].to_numpy("int64") + shift
            s0, s1 = spot.at(asset, start), spot.close_before(asset, end)
            ok = np.isfinite(s0) & np.isfinite(s1)
            outcome = part["outcome_yes"].to_numpy()
            match = (s1 >= s0).astype(int) == outcome
            # near-ties can flip between price sources (some markets settle on Chainlink, not Binance)
            clear = ok & (np.abs(np.log(np.where(ok, s1, 1) / np.where(ok, s0, 1))) >= 0.0002)
            rows.append({"asset": asset, "kind": kind, "shift_s": shift, "markets": int(ok.sum()),
                         "agreement": float(match[ok].mean()) if ok.any() else np.nan,
                         "clear_markets": int(clear.sum()),
                         "agreement_clear": float(match[clear].mean()) if clear.any() else np.nan})
    table = pd.DataFrame(rows)
    for (asset, kind), part in table.groupby(["asset", "kind"]):
        zero = part[part["shift_s"] == 0]["agreement_clear"].iloc[0]
        top = part.sort_values("agreement_clear", ascending=False).iloc[0]
        # only move away from the documented window when it is clearly better
        best[f"{asset}-{kind}"] = int(top["shift_s"]) if top["agreement_clear"] > (zero if np.isfinite(zero) else 0) + 0.05 else 0
    return table, best


def _volatility(spot: SpotSeries, asset: str, ts: np.ndarray, window: int) -> np.ndarray:
    start, returns = spot.log_returns(asset)
    squared = pd.Series(returns ** 2).rolling(window, min_periods=window // 2).mean().to_numpy()
    index = (np.asarray(ts, "int64") - start) // 60
    ok = (index >= 0) & (index < len(squared))
    out = np.full(len(index), np.nan)
    out[ok] = np.sqrt(squared[index[ok]])
    return out


def build_panel(markets: pd.DataFrame, trades: pd.DataFrame, spot_frame: pd.DataFrame, cfg: CryptoConfig,
                top_fraction: float = 0.10, min_prior_markets: int = 5, k: float = 5) -> dict:
    spot = SpotSeries(spot_frame)
    alignment, shifts = check_alignment(markets, spot)
    markets = markets.copy()
    for key, shift in shifts.items():
        asset, kind = key.split("-", 1)
        mask = (markets["asset"] == asset) & (markets["kind"] == kind)
        markets.loc[mask, ["window_start", "window_end"]] += shift
    trades = add_yes_terms(trades)
    trades["market_id"] = trades["market_id"].astype(str)

    # point-in-time wallet skill from earlier-resolved crypto markets (coin flips: fair value = price)
    markets_for_skill = markets.assign(close_ts=markets["window_end"])
    wm = wallet_market_edges(trades, markets_for_skill, FairValue(), min_notional=5)
    timeline = SkillTimeline(wm, k, min_prior_markets, top_fraction)
    skill = timeline.lookup(trades["wallet"].astype(str), trades["ts"])
    trades["top"] = skill["top"].to_numpy()
    trades["signed_usd"] = trades["yes_dir"] * trades["notional"]

    rows = []
    trades_by_market = {m: g.sort_values("ts") for m, g in trades.groupby("market_id")}
    for market in markets.itertuples(index=False):
        part = trades_by_market.get(market.market_id)
        minutes = np.arange(market.window_start + 60, market.window_end, 60, dtype="int64")
        if part is None or len(minutes) == 0:
            continue
        times = part["ts"].to_numpy("int64")
        position = np.searchsorted(times, minutes, side="left") - 1      # trades strictly before t
        has = position >= 0
        p = np.full(len(minutes), np.nan)
        age = np.full(len(minutes), np.inf)
        p[has] = part["yes_price"].to_numpy()[position[has]]
        age[has] = (minutes[has] - times[position[has]]) / 60
        p[age > cfg.stale_min] = np.nan
        s_now = spot.at(market.asset, minutes)
        s_open = spot.at(market.asset, np.array([market.window_start]))[0]
        sigma = _volatility(spot, market.asset, minutes, cfg.vol_window_min)
        left = (market.window_end - minutes) / 60
        z = np.log(s_now / s_open) / (sigma * np.sqrt(np.maximum(left, 1e-9)))
        q = _norm_cdf(np.clip(z, -8, 8))
        cumulative = np.concatenate([[0.0], np.cumsum(part["signed_usd"].to_numpy())])
        cumulative_top = np.concatenate([[0.0], np.cumsum(np.where(part["top"], part["signed_usd"], 0.0))])
        lo = np.searchsorted(times, minutes - cfg.lookback_min * 60, side="left")
        hi = np.searchsorted(times, minutes, side="left")
        rows.append(pd.DataFrame({
            "asset": market.asset, "ts": minutes, "market_id": market.market_id, "kind": market.kind,
            "p": p, "q": q, "flow_all": cumulative[hi] - cumulative[lo], "flow_top": cumulative_top[hi] - cumulative_top[lo],
        }))
    per_market = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    per_market["u"] = _logit(per_market["p"]) - _logit(per_market["q"])
    per_market.loc[per_market["p"].isna() | per_market["q"].isna(), "u"] = np.nan

    panel = per_market.groupby(["asset", "ts"]).agg(
        u=("u", "mean"), markets=("u", "count"), flow_all=("flow_all", "sum"), flow_top=("flow_top", "sum"),
        p_mean=("p", "mean"), q_mean=("q", "mean")).reset_index()
    panel = panel[panel["markets"] > 0].copy()
    for asset, index in panel.groupby("asset").groups.items():
        ts = panel.loc[index, "ts"].to_numpy("int64")
        s_now = spot.at(asset, ts)
        panel.loc[index, "r_past"] = np.log(s_now / spot.at(asset, ts - cfg.lookback_min * 60))
        for h in cfg.horizons_min:
            panel.loc[index, f"r_{h}"] = np.log(spot.at(asset, ts + h * 60) / s_now)
        panel.loc[index, f"r_delay_{cfg.main_horizon_min}"] = np.log(
            spot.at(asset, ts + (cfg.delay_min + cfg.main_horizon_min) * 60) / spot.at(asset, ts + cfg.delay_min * 60))
    for column in ("flow_all", "flow_top"):
        panel[column + "_s"] = np.sign(panel[column]) * np.log1p(np.abs(panel[column]))
    panel["day"] = panel["ts"] // 86_400
    panel = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=["u", "r_past", f"r_{cfg.main_horizon_min}"])
    log.info("panel: %d asset-minutes over %d days (%s)", len(panel), panel["day"].nunique(),
             panel.groupby("asset").size().to_dict())
    return {"panel": panel.reset_index(drop=True), "per_market": per_market, "alignment": alignment,
            "shifts": shifts, "markets": markets, "wallet_markets": wm, "timeline": timeline, "spot": spot}
