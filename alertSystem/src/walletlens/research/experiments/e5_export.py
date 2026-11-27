"""E5 · Package what the app needs: wallet track records, fair value, and per-market evidence.

The app itself then needs no pandas: it reads these CSV/JSON files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.skill import skill_table
from walletlens.research.context import ResearchContext
from walletlens.research.result import ExperimentResult

TOP_WALLETS = 2000
PRICE_POINTS = 400
WALLETS_PER_MARKET = 20


def _downsample(times: np.ndarray, values: np.ndarray, limit: int) -> list:
    if len(times) > limit:
        keep = np.unique(np.linspace(0, len(times) - 1, limit).astype(int))
        times, values = times[keep], values[keep]
    return [[int(t), round(float(v), 4)] for t, v in zip(times, values)]


def _market_files(ctx: ResearchContext, tiers: pd.Series, scores: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    prices = ctx.prices.sort_values("ts")
    by_market_prices = {m: g for m, g in prices.groupby("market_id")}
    pit = ctx.period_b_trades[["market_id", "top", "yes_dir", "notional"]].copy()
    pit["market_id"] = pit["market_id"].astype(str)
    pit_net = (pit[pit["top"]].assign(net=lambda f: f["yes_dir"] * f["notional"])
               .groupby("market_id")["net"].sum())
    files, index = {}, []
    for market in ctx.markets.itertuples(index=False):
        trades = ctx.trades[ctx.trades["market_id"].astype(str) == market.market_id]
        if trades.empty:
            continue
        wallet = trades["wallet"].astype(str)
        tier = wallet.map(tiers).fillna("unranked").to_numpy()
        signed = (trades["yes_dir"] * trades["notional"]).to_numpy()
        day = (trades["ts"] // 86_400 * 86_400).to_numpy()
        flows = (pd.DataFrame({"day": day, "top": np.where(tier == "top", signed, 0.0),
                               "rest": np.where(tier != "top", signed, 0.0)})
                 .groupby("day").sum().reset_index())
        per_wallet = (pd.DataFrame({"wallet": wallet.to_numpy(), "net_yes_usd": signed,
                                    "notional": trades["notional"].to_numpy(), "tier": tier,
                                    "pnl": (trades["yes_dir"] * trades["shares"]
                                            * (market.outcome_yes - trades["yes_price"])).to_numpy()})
                      .groupby(["wallet", "tier"]).sum().reset_index()
                      .sort_values("notional", ascending=False).head(WALLETS_PER_MARKET))
        per_wallet = per_wallet.join(scores[["rank", "shrunk", "markets"]], on="wallet")
        series = by_market_prices.get(market.market_id)
        price_list = _downsample(series["ts"].to_numpy(), series["yes_price"].to_numpy(), PRICE_POINTS) \
            if series is not None else []
        top_net = float(flows["top"].sum())
        out_of_sample = market.market_id in ctx.split["b_markets"]
        pit_value = float(pit_net.get(market.market_id, 0.0)) if out_of_sample else None
        record = {
            "market": {"id": market.market_id, "question": market.question, "category": market.category,
                       "group": market.group_id, "close_ts": int(market.close_ts), "outcome_yes": int(market.outcome_yes),
                       "volume_usd": float(market.volume_usd), "period": "B" if out_of_sample else "A"},
            "prices": price_list,
            "flows": [[int(r.day), round(float(r.top), 2), round(float(r.rest), 2)] for r in flows.itertuples()],
            "wallets": per_wallet.replace({np.nan: None}).to_dict("records"),
            "summary": {"trades": int(len(trades)), "wallets": int(wallet.nunique()),
                        "top_net_yes_usd": top_net, "all_net_yes_usd": float(signed.sum()),
                        "point_in_time_top_net_yes_usd": pit_value},
        }
        files[f"markets/{market.market_id}.json"] = record
        index.append({"market_id": market.market_id, "question": market.question, "category": market.category,
                      "group_id": market.group_id, "close_ts": int(market.close_ts), "outcome_yes": int(market.outcome_yes),
                      "volume_usd": float(market.volume_usd), "period": record["market"]["period"],
                      "trades": int(len(trades)), "top_net_yes_usd": top_net, "pit_top_net_yes_usd": pit_value,
                      "last_price": price_list[-1][1] if price_list else None})
    return files, pd.DataFrame(index)


def run(ctx: ResearchContext) -> ExperimentResult:
    cfg = ctx.cfg
    wm = ctx.wallet_markets
    table = skill_table(wm, cfg.skill_shrinkage_markets)
    table = table[table["markets"] >= cfg.min_prior_markets]
    threshold = float(table["shrunk"].quantile(1 - cfg.top_fraction)) if len(table) else np.inf
    table["tier"] = np.where((table["shrunk"] >= threshold) & (table["shrunk"] > 0), "top", "ranked")
    table["rank"] = np.arange(1, len(table) + 1)
    wallets = table.head(TOP_WALLETS).reset_index()

    recent = wm.sort_values("close_ts").groupby("wallet").tail(12)
    recent = recent[recent["wallet"].isin(set(wallets["wallet"]))]
    questions = ctx.markets.set_index("market_id")["question"]
    recent = recent.assign(question=recent["market_id"].map(questions))[
        ["wallet", "market_id", "question", "close_ts", "notional", "pnl", "edge", "trades"]]

    files, market_index = _market_files(ctx, table["tier"], table)

    # out-of-sample evidence: in period-B markets, did the point-in-time top tier's net side win?
    oos = market_index.dropna(subset=["pit_top_net_yes_usd"])
    oos = oos[oos["pit_top_net_yes_usd"].abs() > 0]
    sided_yes = oos["pit_top_net_yes_usd"] > 0
    hit_rate = float((sided_yes == (oos["outcome_yes"] == 1)).mean()) if len(oos) else float("nan")
    # baseline: the side the market itself favoured halfway through each market's life
    info = ctx.markets.set_index("market_id")
    middle = ((info.loc[oos["market_id"], "start_ts"] + info.loc[oos["market_id"], "close_ts"]) // 2).to_numpy()
    favourite_yes = ctx.book.at(oos["market_id"].to_numpy(), middle) > 0.5
    favourite_hit = float((favourite_yes == (oos["outcome_yes"] == 1).to_numpy()).mean()) if len(oos) else float("nan")

    metrics = {"ranked_wallets": int(len(table)), "top_wallets": int((table["tier"] == "top").sum()),
               "top_threshold": threshold, "exported_wallets": int(len(wallets)), "markets": int(len(market_index)),
               "out_of_sample_markets_with_top_flow": int(len(oos)), "top_net_side_hit_rate": hit_rate,
               "market_favourite_hit_rate": favourite_hit,
               "fair_value": ctx.fair.to_dict()}
    return ExperimentResult(
        id="e5", title="App export", verdict="descriptive",
        headline=(f"Exported {len(wallets)} wallet track records ({metrics['top_wallets']} in the top tier) and "
                  f"{len(market_index)} market pages. Out of sample, the top tier's net side won in "
                  f"{hit_rate:.0%} of {len(oos)} markets (the market's own mid-life favourite: {favourite_hit:.0%})."),
        question="What does the trading helper load?", metrics=metrics,
        tables={"wallet_scores": wallets, "wallet_recent_markets": recent, "market_index": market_index},
        artifacts=files,
        notes=["Wallet scores use every resolved market (the app looks forward from today), so historical "
               "market pages contain hindsight; the out-of-sample hit rate uses point-in-time tiers only."])
