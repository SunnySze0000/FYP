"""Phase 3b: do some wallets trade with information, and can we follow them?

Method (all on the June 2026 Fed event, five markets):

1. Build an hourly and a daily volume-weighted YES price per market.
2. For every trade compute its *markout*: how far the YES price moved in the
   trader's favour `h` hours later, per share. Positive means the trade was
   followed by a move in its direction (an informed or lucky trade).
3. Score each wallet on a formation period using only trades and price moves
   that occurred before the formation end, shrinking small samples to zero.
4. Test the scores out-of-sample in a later period: do high-score wallets
   keep earning positive markouts and better resolution P&L, and does their
   net flow predict the next day's price change?
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from eventlens.stats import spearman_test

ANNOUNCEMENT_UTC = pd.Timestamp("2026-06-17 18:00", tz="UTC")


@dataclass(frozen=True)
class StudyWindows:
    formation_start: pd.Timestamp
    formation_end: pd.Timestamp
    test_end: pd.Timestamp


DEFAULT_WINDOWS = StudyWindows(
    formation_start=pd.Timestamp("2025-12-01", tz="UTC"),
    formation_end=pd.Timestamp("2026-05-15", tz="UTC"),
    test_end=ANNOUNCEMENT_UTC - pd.Timedelta(hours=24),
)

#: Windows for contested-price trades (5-95 cents). The June outcome became
#: near-certain after the March meeting, so contested trading ends in April.
CONTESTED_WINDOWS = StudyWindows(
    formation_start=pd.Timestamp("2025-12-01", tz="UTC"),
    formation_end=pd.Timestamp("2026-03-01", tz="UTC"),
    test_end=pd.Timestamp("2026-05-01", tz="UTC"),
)


def price_bars(trades: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Volume-weighted YES price per market and bar, labelled by bar end."""
    frame = trades[["market_id", "timestamp_utc", "yes_price", "shares"]].copy()
    frame["bar_end"] = frame["timestamp_utc"].dt.floor(freq) + pd.Timedelta(freq)
    frame["weighted"] = frame["yes_price"] * frame["shares"]
    bars = frame.groupby(["market_id", "bar_end"]).agg(weighted=("weighted", "sum"), shares=("shares", "sum"))
    bars["vwap"] = bars["weighted"] / bars["shares"]
    return bars[["vwap", "shares"]].reset_index()


def add_markouts(trades: pd.DataFrame, hourly_bars: pd.DataFrame, horizons_h: tuple[int, ...] = (1, 24)) -> pd.DataFrame:
    """Add `markout_{h}h` (per share) and `markout_{h}h_usd` for each horizon.

    The reference price is the VWAP of the latest hourly bar ending at or
    before trade time + h. Trades without a later bar get NaN.
    """
    result = trades.copy()
    result["_row"] = np.arange(len(result))
    bars = hourly_bars.sort_values("bar_end")
    for hours in horizons_h:
        probe = result[["_row", "market_id", "timestamp_utc"]].copy()
        probe["at"] = probe["timestamp_utc"] + pd.Timedelta(hours=hours)
        probe = probe.sort_values("at")
        matched = pd.merge_asof(
            probe, bars.rename(columns={"bar_end": "at"})[["market_id", "at", "vwap"]],
            on="at", by="market_id", direction="backward",
        ).set_index("_row")["vwap"]
        reference = matched.reindex(result["_row"]).to_numpy()
        result[f"markout_{hours}h"] = result["direction"] * (reference - result["yes_price"])
        result[f"markout_{hours}h_usd"] = result[f"markout_{hours}h"] * result["shares"]
    return result.drop(columns="_row")


def add_resolution_pnl(trades: pd.DataFrame, final_yes: dict[str, int]) -> pd.DataFrame:
    """P&L per trade if held to resolution: direction x (final YES value - YES price) x shares."""
    result = trades.copy()
    final = result["market_id"].map(final_yes).astype(float)
    result["resolution_pnl_usd"] = result["direction"] * (final - result["yes_price"]) * result["shares"]
    return result


def contested(trades: pd.DataFrame, low: float = 0.05, high: float = 0.95) -> pd.DataFrame:
    """Trades at prices where the outcome was genuinely uncertain.

    Trades at 1-2 cents are dominated by longshot selling and tick-size
    effects; information about the outcome matters most in between.
    """
    return trades.loc[trades["yes_price"].between(low, high)]


def wallet_scores(trades: pd.DataFrame, value_column: str, prior_shares: float = 2000.0) -> pd.DataFrame:
    """Shrunk edge-per-share score for each wallet (in probability points).

    score = sum(value) / (sum(shares) + prior_shares). Dividing by shares
    rather than dollars avoids rewarding trades at extreme prices, where a
    tiny absolute gain is a large percentage. The prior pulls wallets with
    little trading towards zero.
    """
    valid = trades.dropna(subset=[value_column])
    grouped = valid.groupby("wallet_address").agg(
        trades=(value_column, "size"),
        shares=("shares", "sum"),
        notional_usd=("notional_usd", "sum"),
        value_usd=(value_column, "sum"),
        markets=("market_id", "nunique"),
    )
    grouped["score"] = grouped["value_usd"] / (grouped["shares"] + prior_shares)
    return grouped.reset_index()


def split_periods(trades: pd.DataFrame, windows: StudyWindows = DEFAULT_WINDOWS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Formation trades whose 24h markout is fully observed before formation end, and test trades."""
    time = trades["timestamp_utc"]
    formation = trades.loc[
        (time >= windows.formation_start) & (time < windows.formation_end - pd.Timedelta(hours=24))
    ]
    test = trades.loc[(time >= windows.formation_end) & (time < windows.test_end)]
    return formation, test


def persistence(
    formation_scores: pd.DataFrame, test_scores: pd.DataFrame, min_trades: int = 20, groups: int = 5
) -> tuple[dict, pd.DataFrame]:
    """Rank correlation of formation and test scores, plus a quintile table."""
    left = formation_scores.loc[formation_scores["trades"] >= min_trades]
    right = test_scores.loc[test_scores["trades"] >= min_trades]
    joined = left.merge(right, on="wallet_address", suffixes=("_formation", "_test"))
    if len(joined) < 3 * groups:
        raise ValueError(f"Only {len(joined)} wallets active in both periods; too few to test persistence")
    estimate = spearman_test(joined["score_formation"], joined["score_test"], resamples=2000)
    joined["formation_group"] = pd.qcut(joined["score_formation"].rank(method="first"), groups, labels=False) + 1
    table = joined.groupby("formation_group").agg(
        wallets=("wallet_address", "size"),
        formation_score=("score_formation", "mean"),
        test_value_usd=("value_usd_test", "sum"),
        test_shares=("shares_test", "sum"),
        test_notional_usd=("notional_usd_test", "sum"),
    )
    table["test_edge_per_share"] = table["test_value_usd"] / table["test_shares"]
    table["test_return_per_dollar"] = table["test_value_usd"] / table["test_notional_usd"]
    return estimate.as_dict("rho_") | {"wallets": len(joined)}, table.reset_index()


def assign_groups(formation_scores: pd.DataFrame, min_trades: int, top_share: float = 0.1) -> pd.Series:
    """Label eligible wallets 'top', 'bottom' or 'middle' by formation score."""
    eligible = formation_scores.loc[formation_scores["trades"] >= min_trades].set_index("wallet_address")["score"]
    high, low = eligible.quantile(1 - top_share), eligible.quantile(top_share)
    labels = pd.Series("middle", index=eligible.index)
    labels[eligible >= high] = "top"
    labels[eligible <= low] = "bottom"
    return labels


def flow_signal(test_trades: pd.DataFrame, daily_bars: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """Does a group's net YES flow on day d predict the YES price change on day d+1?

    Daily flow is the sum of direction x shares for the group's trades. The
    target is the change in daily VWAP from day d to day d+1, so the signal
    uses only information available by the end of day d.
    """
    frame = test_trades.assign(group=test_trades["wallet_address"].map(groups).fillna("unscored"))
    frame["day"] = frame["timestamp_utc"].dt.floor("1D") + pd.Timedelta("1D")
    frame["signed_shares"] = frame["direction"] * frame["shares"]
    flows = frame.pivot_table(index=["market_id", "day"], columns="group", values="signed_shares", aggfunc="sum", fill_value=0.0)
    prices = daily_bars.rename(columns={"bar_end": "day"}).set_index(["market_id", "day"])["vwap"]
    data = flows.join(prices, how="inner").reset_index().sort_values(["market_id", "day"])
    data["next_change"] = data.groupby("market_id")["vwap"].shift(-1) - data["vwap"]
    rows = []
    for group in [column for column in ("top", "bottom", "middle", "unscored") if column in data]:
        estimate = spearman_test(data[group], data["next_change"], resamples=2000)
        rows.append({"wallet_group": group, **estimate.as_dict("rho_")})
    return pd.DataFrame(rows)


def wallet_profiles(trades: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """Describe each wallet group's trading style.

    `netting_ratio` = |net signed shares| / gross shares per wallet and
    market. Near 0 means two-sided, market-maker-like trading; near 1 means
    one-directional bets.
    """
    frame = trades.assign(group=trades["wallet_address"].map(groups)).dropna(subset=["group"])
    frame = frame.assign(signed=frame["direction"] * frame["shares"])
    per_wallet_market = frame.groupby(["group", "wallet_address", "market_id"]).agg(
        net=("signed", "sum"), gross=("shares", "sum"))
    per_wallet_market["netting_ratio"] = per_wallet_market["net"].abs() / per_wallet_market["gross"]
    per_wallet = frame.groupby(["group", "wallet_address"]).agg(
        trades=("shares", "size"), median_trade_usd=("notional_usd", "median"),
        notional_usd=("notional_usd", "sum"), markets=("market_id", "nunique"),
        mean_entry_yes_price=("yes_price", "mean"))
    per_wallet["netting_ratio"] = per_wallet_market.groupby(["group", "wallet_address"])["netting_ratio"].mean()
    return per_wallet.groupby("group").median().reset_index()


def follow_with_delay(
    trades: pd.DataFrame, hourly_bars: pd.DataFrame, groups: pd.Series, group: str,
    delay_h: int = 1, hold_h: int = 24, cost_per_share: float = 0.01,
) -> dict:
    """Copy each trade of `group` wallets `delay_h` hours later and hold `hold_h` hours.

    Entry and exit use hourly VWAP bars, so the copier never trades at the
    original wallet's price. Returns are per share after `cost_per_share`.
    """
    copied = trades.loc[trades["wallet_address"].map(groups).eq(group), ["market_id", "timestamp_utc", "direction"]]
    bars = hourly_bars.sort_values("bar_end")[["market_id", "bar_end", "vwap"]]
    prices = {}
    for label, offset in (("entry", delay_h), ("exit", delay_h + hold_h)):
        probe = copied.assign(at=copied["timestamp_utc"] + pd.Timedelta(hours=offset)).reset_index().sort_values("at")
        matched = pd.merge_asof(probe, bars.rename(columns={"bar_end": "at"}), on="at", by="market_id", direction="backward")
        prices[label] = matched.set_index("index")["vwap"].reindex(copied.index)
    pnl = (copied["direction"] * (prices["exit"] - prices["entry"])).dropna()
    net = pnl - cost_per_share
    return {
        "group": group, "delay_h": delay_h, "hold_h": hold_h, "copied_trades": len(pnl),
        "mean_move_per_share": float(pnl.mean()), "mean_net_per_share": float(net.mean()),
        "share_profitable_after_cost": float((net > 0).mean()),
    }
