"""Export what the live monitor needs from the research data (run after the ``daily`` suite passed).

Writes ``data/app/model.json`` and ``data/app/wallet_clusters.csv``:

* per asset: normal and shock-hour |return|, big-move threshold, number of shocks (V1 / D3)
* per group: research verdict and whether its link is reliable (D6)
* early-warning model (W3) refitted with the features the live app can compute exactly, its out-of-time
  check, and the alert threshold (top 5% of training scores)
* large-wallet pressure facts (W5) and the team's behaviour-cluster names and wallet lookup
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from walletlens import io, logs
from walletlens.config import ASSET_GROUPS, GROUP_KEYWORDS, Settings
from walletlens.topics.events.daily import BIG_QUANTILE, DailyContext, hourly_book
from walletlens.topics.events.experiments.w3_early_warning import _auc, _features, _fit_logistic

log = logs.get("monitor.export")
BASE = ["abs_dp", "recent_vol"]
LIVE_WALLET = ["gross_z", "whale_z", "wallets_z", "imbalance"]      # new_z needs full wallet history: left out
CLUSTER_NAMES = {"C0": ("Market makers", "Active on many days and markets, trade both sides"),
                 "C1": ("Patient traders", "Long gaps between trades, few trades a day"),
                 "C2": ("Burst traders", "Most activity on one day and in one market")}
WEAK_GROUPS = {"us_politics"}          # D6: negative effect, shown as "weak link"


def early_warning(ctx: DailyContext) -> dict:
    frame = _features(ctx.watched_hours).dropna(subset=BASE + LIVE_WALLET + ["shock_next"])
    early = frame[frame["ts"] < ctx.split_ts]
    late = frame[frame["ts"] >= ctx.split_ts]
    cols = BASE + LIVE_WALLET

    def fit(train):
        mean, std = train[cols].mean(), train[cols].std().replace(0, 1)
        beta = _fit_logistic(((train[cols] - mean) / std).to_numpy(), train["shock_next"].to_numpy(float))
        return mean, std, beta

    def score(f, mean, std, beta):
        return np.column_stack([np.ones(len(f)), ((f[cols] - mean) / std).to_numpy()]) @ beta

    mean, std, beta = fit(early)                       # out-of-time check of the live feature set
    base_mean, base_std = early[BASE].mean(), early[BASE].std().replace(0, 1)
    base_beta = _fit_logistic(((early[BASE] - base_mean) / base_std).to_numpy(), early["shock_next"].to_numpy(float))
    y = late["shock_next"].to_numpy(float)
    auc_full = _auc(score(late, mean, std, beta), y)
    auc_base = _auc(np.column_stack([np.ones(len(late)), ((late[BASE] - base_mean) / base_std).to_numpy()]) @ base_beta, y)
    mean, std, beta = fit(frame)                       # final model on everything
    scores = score(frame, mean, std, beta)
    threshold = float(np.quantile(scores, 0.95))
    top = frame["shock_next"].to_numpy(float)[scores >= threshold].mean()
    base_rate = float(frame["shock_next"].mean())
    # D-fix-2: one threshold per activity level (share of the previous 48 h with any $250+ trade), so busy
    # markets are not flagged far more often than quiet ones; each level flags its own top 5%
    active = (frame["f_trades"] > 0).astype(float)
    frame = frame.assign(act48=active.groupby(frame["market_id"]).transform(
        lambda x: x.shift(1).rolling(48, min_periods=12).mean()), score=scores)
    edges = [-0.01, 0.1, 0.25, 0.5, 0.75, 1.0]
    frame = frame.dropna(subset=["act48"])
    frame["level"] = pd.cut(frame["act48"], edges, labels=False)
    levels = [{"upper": edges[i + 1], "threshold": float(part["score"].quantile(0.95)),
               "jump_rate": float(part["shock_next"].mean()),
               "jump_rate_flagged": float(part.loc[part["score"] >= part["score"].quantile(0.95), "shock_next"].mean())}
              for i, part in frame.groupby("level")]
    log.info("live early-warning model: out-of-time AUC %.3f vs %.3f price-only", auc_full, auc_base)
    return {"features": cols, "mean": mean.round(6).tolist(), "std": std.round(6).tolist(),
            "beta": np.round(beta, 6).tolist(), "threshold": threshold, "levels": levels,
            "jump_rate_flagged": float(top), "jump_rate_all": base_rate,
            "check": {"auc_with_wallets": auc_full, "auc_price_only": auc_base, "gain": auc_full - auc_base},
            "trailing_hours": 48, "min_trade_usd": ctx.cfg.trade_filter_amount, "whale_trade_usd": ctx.cfg.whale_trade_usd}


def assets(ctx: DailyContext) -> list[dict]:
    pairs = ctx.watched["pairs"]
    mapped = pairs[(pairs["kind"] == "mapped") & (pairs["shocks"] > 0)]
    book = hourly_book(ctx.hourly)
    rows = []
    for asset, part in mapped.groupby("asset"):
        w = part["shocks"]
        rows.append({"asset": asset, "normal_abs_r": float(part["abs_r_normal"].mean()),
                     "shock_abs_r": float(np.average(part["abs_r_shock"], weights=w)),
                     "big_threshold": book.big.get(asset), "big_rate_shock": float(np.average(part["big_rate_shock"], weights=w)),
                     "big_rate_normal": float(part["big_rate_normal"].mean()), "shocks": int(w.sum()),
                     "markets": int(part["market_id"].nunique())})
    return rows


def group_jumps(ctx: DailyContext) -> pd.DataFrame:
    """Every watched 10-point jump in the research data, by topic group: the history the per-holding check uses."""
    from walletlens.topics.events.daily import WATCH_AGE, WATCH_HIGH, WATCH_LOW
    rows = []
    groups = ctx.all_markets.set_index("market_id")["groups"]
    for market_id, g in ctx.all_prices.sort_values("ts").groupby("market_id"):
        if market_id not in groups.index:
            continue
        ts, p = g["ts"].to_numpy("int64"), g["yes_price"].to_numpy(float)
        grid = np.arange(ts[0] // 3600 * 3600 + 3600, ts[-1] + 1, 3600)
        now = p[np.searchsorted(ts, grid, side="right") - 1]
        j = np.searchsorted(ts, grid - 3600, side="right") - 1
        prev = np.where(j >= 0, p[np.maximum(j, 0)], np.nan)
        hit = (prev >= WATCH_LOW) & (prev <= WATCH_HIGH) & (grid - 3600 - ts[0] >= WATCH_AGE) & (np.abs(now - prev) >= ctx.cfg.shock_points)
        for t in grid[hit]:
            for grp in str(groups[market_id]).split("|"):
                rows.append({"ts": int(t), "group": grp, "market_id": market_id})
    return pd.DataFrame(rows)


def export(settings: Settings, research_run: str | None = None) -> dict:
    ctx = DailyContext(settings, "events")
    groups_result = {}
    if research_run:
        d6 = io.read_json(settings.paths.results / research_run / "d6" / "summary.json")["metrics"]["by_group"]
        groups_result = {row["group"]: row["mean"] for row in d6}
    model = {
        "created_at": datetime.now(timezone.utc).isoformat(), "research_run": research_run,
        "shock_points": ctx.cfg.shock_points, "watch": {"low": 0.10, "high": 0.90, "min_age_hours": 24},
        "big_quantile": BIG_QUANTILE,
        "groups": {g: {"assets": list(a), "keywords": list(GROUP_KEYWORDS.get(g, ())), "effect": groups_result.get(g),
                       "reliable": g not in WEAK_GROUPS} for g, a in ASSET_GROUPS.items()},
        "assets": assets(ctx), "early_warning": early_warning(ctx),
        "pressure": {"min_flow_usd": 500, "whale_follow_points": 0.82, "retail_follow_points": 0.09},
        "clusters": {k: {"name": v[0], "description": v[1]} for k, v in CLUSTER_NAMES.items()},
    }
    folder = settings.paths.root / "data" / "app"
    io.write_json(folder / "model.json", model)
    group_jumps(ctx).to_csv(folder / "group_jumps.csv", index=False)
    table = ctx.pipeline[0]
    if len(table):
        lookup = table[table["eligible"].astype(bool)][["wallet", "cluster_id"]]
        io.write_csv(folder / "wallet_clusters.csv", lookup)
        log.info("cluster lookup: %d wallets", len(lookup))
    log.info("monitor model written to %s", folder)
    return model
