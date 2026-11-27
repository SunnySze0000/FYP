"""T2: align each event market's hourly probability with the hourly returns of related assets.

For each market and each asset (mapped = in one of the market's keyword groups; placebo =
two assets from unrelated groups), evaluated at the asset's hourly bar ends x:

* ``dp``      = P(x) - P(x_prev)            (probability change over the same hour)
* ``dlogit``  = logit P(x) - logit P(x_prev)
* ``r``       = ln close(x) / close(x_prev)  (asset return over that hour)
* ``r_next``  = ln close(x_next) / close(x) (the following hour)

Overnight and weekend gaps are excluded. A *shock* is |dp| >= ``shock_points``.
Per (market, asset) pair it returns compact statistics, so millions of hours never sit in memory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens import logs
from walletlens.config import ASSET_GROUPS, EventsConfig

log = logs.get("events.panel")
EPS = 0.01


class AssetBook:
    def __init__(self, hourly: pd.DataFrame):
        self.series = {s: (g["end_ts"].to_numpy("int64"), g["close"].to_numpy(float))
                       for s, g in hourly.sort_values("end_ts").groupby("symbol")}

    def symbols(self) -> list[str]:
        return sorted(self.series)


def _price_at(times: np.ndarray, values: np.ndarray, at: np.ndarray, max_age: int) -> np.ndarray:
    position = np.searchsorted(times, at, side="right") - 1
    ok = position >= 0
    out = np.full(len(at), np.nan)
    out[ok] = values[position[ok]]
    age = np.where(ok, at - times[np.clip(position, 0, None)], np.inf)
    out[age > max_age] = np.nan
    return out


def _logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _beta(x: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 5 or np.var(x) == 0:
        return np.nan
    return float(np.cov(x, y)[0, 1] / np.var(x, ddof=1))


def placebo_assets(market_id: str, mapped: set[str], pool: list[str], n: int = 2) -> list[str]:
    candidates = [a for a in pool if a not in mapped]
    rng = np.random.default_rng(int(market_id) % (2 ** 32) if market_id.isdigit() else abs(hash(market_id)) % (2 ** 32))
    return list(rng.choice(candidates, size=min(n, len(candidates)), replace=False)) if candidates else []


def analyse(markets: pd.DataFrame, prices: pd.DataFrame, hourly: pd.DataFrame, cfg: EventsConfig) -> dict:
    book = AssetBook(hourly)
    pool = [s for s in book.symbols() if s in {a for members in ASSET_GROUPS.values() for a in members}]
    price_groups = {m: (g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float))
                    for m, g in prices.sort_values("ts").groupby("market_id")}
    pairs, shocks = [], []
    for market in markets.itertuples(index=False):
        if market.market_id not in price_groups:
            continue
        p_times, p_values = price_groups[market.market_id]
        groups = [g for g in str(market.groups).split("|") if g]
        mapped = {a for g in groups for a in ASSET_GROUPS.get(g, ())}
        for asset, kind in [(a, "mapped") for a in sorted(mapped)] + \
                           [(a, "placebo") for a in placebo_assets(market.market_id, mapped, pool)]:
            if asset not in book.series:
                continue
            ends, closes = book.series[asset]
            inside = (ends > p_times[0] + 3600) & (ends <= min(market.close_ts, p_times[-1] + 3600))
            index = np.nonzero(inside)[0]
            index = index[(index >= 1) & (index < len(ends) - 1)]
            if len(index) < 10:
                continue
            x, x_prev, x_next = ends[index], ends[index - 1], ends[index + 1]
            same_session = (x - x_prev <= 3600) & (x_next - x <= 3600)
            p_now = _price_at(p_times, p_values, x, 2 * 3600)
            p_before = _price_at(p_times, p_values, x_prev, 2 * 3600)
            dp = p_now - p_before
            dlogit = _logit(p_now) - _logit(p_before)
            r = np.log(closes[index] / closes[index - 1])
            r_next = np.log(closes[index + 1] / closes[index])
            ok = same_session & np.isfinite(dp) & np.isfinite(r) & np.isfinite(r_next)
            if ok.sum() < 10:
                continue
            dp, dlogit, r, r_next, x = dp[ok], dlogit[ok], r[ok], r_next[ok], x[ok]
            shock = np.abs(dp) >= cfg.shock_points
            half = len(x) // 2
            # walk-forward direction: sign learned from this pair's earlier co-movement only
            hits = attempts = 0
            predicted = {}
            for i in np.nonzero(shock)[0]:
                beta = _beta(dlogit[:i], r[:i])
                if np.isfinite(beta) and beta != 0 and r_next[i] != 0:
                    attempts += 1
                    hit = int(np.sign(beta) * np.sign(dlogit[i]) == np.sign(r_next[i]))
                    hits += hit
                    predicted[i] = hit
            pairs.append({
                "market_id": market.market_id, "asset": asset, "kind": kind, "groups": market.groups,
                "hours": int(len(x)), "shocks": int(shock.sum()),
                "abs_r_normal": float(np.abs(r[~shock]).mean()) if (~shock).any() else np.nan,
                "abs_r_shock": float(np.abs(r[shock]).mean()) if shock.any() else np.nan,
                "abs_next_normal": float(np.abs(r_next[~shock]).mean()) if (~shock).any() else np.nan,
                "abs_next_shock": float(np.abs(r_next[shock]).mean()) if shock.any() else np.nan,
                "beta_all": _beta(dlogit, r),
                "beta_first": _beta(dlogit[:half], r[:half]), "beta_second": _beta(dlogit[half:], r[half:]),
                "shocks_first": int(shock[:half].sum()), "shocks_second": int(shock[half:].sum()),
                "direction_hits": hits, "direction_attempts": attempts,
            })
            for i in np.nonzero(shock)[0]:
                shocks.append({"market_id": market.market_id, "asset": asset, "kind": kind, "ts": int(x[i]),
                               "dp": float(dp[i]), "r": float(r[i]), "r_next": float(r_next[i]),
                               "abs_r_normal": float(np.abs(r[~shock]).mean()) if (~shock).any() else np.nan,
                               "direction_hit": predicted.get(i, np.nan)})
    pairs = pd.DataFrame(pairs)
    log.info("events: %d market-asset pairs (%d mapped), %d shock hours", len(pairs),
             int((pairs["kind"] == "mapped").sum()) if len(pairs) else 0, len(shocks))
    return {"pairs": pairs, "shocks": pd.DataFrame(shocks)}


def ratio_by_market(pairs: pd.DataFrame, shock_col: str, normal_col: str) -> pd.DataFrame:
    """Per market: mean (shock / normal) |return| ratio for mapped and for placebo assets."""
    usable = pairs[(pairs["shocks"] > 0) & (pairs[normal_col] > 0)].copy()
    usable["ratio"] = usable[shock_col] / usable[normal_col]
    wide = usable.pivot_table(index="market_id", columns="kind", values="ratio", aggfunc="mean")
    return wide.dropna(subset=[c for c in ("mapped", "placebo") if c in wide.columns]).reset_index()
