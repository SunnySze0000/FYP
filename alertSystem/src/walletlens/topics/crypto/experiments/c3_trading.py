"""C3 · G3: can a simple spot rule built on the signal make money after delay and fees?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.stats import cluster_bootstrap_mean
from walletlens.analytics.walkforward import walk_forward
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.crypto.context import CryptoContext


def simulate(preds: pd.DataFrame, signal: str, outcome: str, threshold_quantile: float, hold_min: int,
             min_train_days: int) -> pd.DataFrame:
    """Trade sign(signal) when |signal| is above the training-days quantile; one position at a time per asset."""
    trades = []
    for asset, part in preds.groupby("asset"):
        part = part.sort_values("ts")
        days = np.sort(part["day"].unique())
        history = []
        busy_until = -1
        for day in days:
            today = part[part["day"] == day]
            if len(history) >= min_train_days:
                threshold = np.quantile(np.abs(np.concatenate(history)), threshold_quantile)
                for ts, value, result in zip(today["ts"].to_numpy(), today[signal].to_numpy(), today[outcome].to_numpy()):
                    if ts < busy_until or not np.isfinite(value) or not np.isfinite(result) or abs(value) < threshold:
                        continue
                    trades.append({"asset": asset, "ts": int(ts), "day": int(day), "side": int(np.sign(value)),
                                   "gross": float(np.sign(value) * result)})
                    busy_until = ts + hold_min * 60
            history.append(today[signal].dropna().to_numpy())
    return pd.DataFrame(trades)


def run(ctx: CryptoContext) -> ExperimentResult:
    cfg = ctx.cfg
    panel = ctx.panel
    h = cfg.main_horizon_min
    delayed = f"r_delay_{h}"
    preds = walk_forward(panel, f"r_{h}", {"base": ["r_past"], "polymarket": ["r_past", "u"],
                                            "wallets": ["r_past", "u", "flow_all_s", "flow_top_s"]}, cfg.min_train_days)
    if len(preds):
        preds = preds.join(panel[["asset", "ts", delayed]])
        preds["edge_polymarket"] = preds["pred_polymarket"] - preds["pred_base"]
        preds["edge_wallets"] = preds["pred_wallets"] - preds["pred_base"]
    rows, curves = [], {}
    for name in ("edge_polymarket", "edge_wallets"):
        trades = simulate(preds, name, delayed, cfg.signal_quantile, h + cfg.delay_min, cfg.min_train_days) \
            if len(preds) else pd.DataFrame()
        for cost in cfg.costs_bps:
            if trades.empty:
                rows.append({"signal": name, "cost_bps": cost, "trades": 0, "mean_bps": np.nan, "low": np.nan, "high": np.nan})
                continue
            net = trades["gross"] * 1e4 - cost
            stat = cluster_bootstrap_mean(net, trades["day"], cfg.bootstrap_draws, cfg.seed_research)
            rows.append({"signal": name, "cost_bps": cost, "trades": len(trades), "days": stat["groups"],
                         "mean_bps": stat["mean"], "low": stat["low"], "high": stat["high"],
                         "hit_rate": float((trades["gross"] > cost / 1e4).mean()), "gross_bps": float(trades["gross"].mean() * 1e4)})
            if cost == min(cfg.costs_bps):
                curves[name] = trades.assign(net=net).sort_values("ts")
    table = pd.DataFrame(rows)
    main = table[(table["signal"] == "edge_polymarket") & (table["cost_bps"] == min(cfg.costs_bps))].iloc[0]
    best = table[table["cost_bps"] == min(cfg.costs_bps)].sort_values("mean_bps", ascending=False).iloc[0]
    passed = any((r["mean_bps"] > 0) and (r["low"] > 0) for r in table[table["cost_bps"] == min(cfg.costs_bps)].to_dict("records"))
    verdict = "inconclusive" if (main.get("trades", 0) or 0) < 100 else ("pass" if passed else "fail")

    fig, ax = plots.figure(8, 3.6)
    for colour, (name, trades) in zip((plots.ACCENT, plots.THIRD), curves.items()):
        ax.plot(pd.to_datetime(trades["ts"], unit="s"), trades["net"].cumsum(), color=colour, lw=1.5,
                label=f"{name.replace('edge_', '')} ({len(trades)} trades)")
    ax.axhline(0, color=plots.MUTED, lw=1)
    ax.set_ylabel("cumulative net return (bps)")
    ax.set_title(f"Spot rule: {cfg.delay_min} min delay, {h} min hold, {min(cfg.costs_bps)} bps round trip")
    ax.legend()
    ax.tick_params(axis="x", rotation=30)
    headline = (f"Best rule ({best['signal'].replace('edge_', '')}) nets {best['mean_bps']:+.2f} bps per trade at "
                f"{min(cfg.costs_bps)} bps cost (95% CI {best['low']:+.2f} to {best['high']:+.2f}, {int(best['trades'])} trades).")
    return ExperimentResult(
        id="c3", title="G3 · Tradable after costs?", verdict=verdict, headline=headline,
        question="Trading spot when the model's signal is strong, entering one minute late and paying fees: is it profitable?",
        metrics={"main": main.to_dict(), "best": best.to_dict()}, tables={"rules": table}, figures={"pnl": fig},
        notes=[f"Threshold: top {1 - cfg.signal_quantile:.0%} of |signal| on earlier days only; one open position per asset.",
               f"Pass rule: any rule with mean net return > 0 and CI above 0 at {min(cfg.costs_bps)} bps; "
               f"{max(cfg.costs_bps)} bps (retail taker fees) is reported too. < 100 trades = inconclusive."])
