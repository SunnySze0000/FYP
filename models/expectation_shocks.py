"""How do assets react to shifts in Polymarket's expected Fed path?

Fixes the timing problem of the daily snapshots (00:00 UTC vs the 16:00 New
York close) by rebuilding every Fed market's YES price at the US equity close
from trades, for 7 meetings (Aug 2025 - Sep 2026).

1. Close price per market and trading day: median of the last 20 trades in
   the 24 hours before 16:00 America/New_York (robust to bid/ask bounce).
2. Expected move per meeting and day: probability-weighted rate move (bp),
   probabilities renormalised across the meeting's markets.
3. Daily shock: sum over meetings quoted on both days of the change in
   expected move = change in the expected cumulative rate path (bp, + = hawkish).
4. Asset returns close-to-close (adjusted), so shock and return cover the same
   window. OLS with Newey-West (HAC, 5 lags) errors, plus timing placebos:
   shock one day later (lead) and one day earlier (lag = a genuine forecast).
5. Wallet early warning: does the hawkish net flow of wallets that were
   skilled in EARLIER meetings (top quintile, bias-adjusted score) on day d
   predict the shock on day d+1?

    python models/expectation_shocks.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts" / "polymarket"))
import wallet_persistence as wp  # noqa: E402
from outcomes import outcome_move  # noqa: E402

YAHOO = Path("/mnt/user-data/uploads/FYP/sunny_playground/data/raw/yahoo")
ASSETS = ["SPY", "QQQ", "IWM", "DIA", "TLT"]
OUT = ROOT / "models" / "expectation_shocks"
NY = "America/New_York"


def close_prices(trades: pd.DataFrame) -> pd.DataFrame:
    """YES price per market at each NY 16:00 close: median of the last 20 trades in the prior 24 h."""
    t = trades[["market_id", "meeting", "rate_outcome", "timestamp_utc", "yes_price"]].copy()
    local = t["timestamp_utc"].dt.tz_convert(NY)
    # trades after 16:00 belong to the next session's close
    session = local.dt.normalize() + pd.to_timedelta((local.dt.hour >= 16).astype(int), unit="D")
    t["session"] = session.dt.tz_localize(None)
    t["close_ts"] = (session + pd.Timedelta(hours=16)).dt.tz_convert("UTC")
    t = t.loc[t["timestamp_utc"] >= t["close_ts"] - pd.Timedelta(hours=24)]
    t = t.sort_values("timestamp_utc").groupby(["market_id", "session"]).tail(20)
    out = t.groupby(["meeting", "market_id", "rate_outcome", "session"], as_index=False)["yes_price"].median()
    return out.rename(columns={"session": "date"})


def expected_path(prices: pd.DataFrame, markets: pd.DataFrame) -> pd.DataFrame:
    """Expected move per meeting/day, only on days when every market of the meeting is quoted."""
    p = prices.copy()
    p["move"] = outcome_move(p["rate_outcome"])
    n_markets = markets.groupby("meeting_month")["market_id"].nunique()
    full = p.groupby(["meeting", "date"])["market_id"].transform("nunique") == p["meeting"].map(n_markets)
    p = p.loc[full & p["move"].notna()]
    p["pn"] = p["yes_price"] / p.groupby(["meeting", "date"])["yes_price"].transform("sum")
    e = (p["pn"] * p["move"]).groupby([p["meeting"], p["date"]]).sum().rename("expected").reset_index()
    return e


def daily_shock(expected: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.Series:
    """Sum over meetings quoted on two consecutive trading days of the change in expected move."""
    wide = expected.pivot(index="date", columns="meeting", values="expected").reindex(trading_days)
    change = wide.diff()                       # NaN unless quoted on both consecutive trading days
    shock = change.sum(axis=1, min_count=1)
    return shock.rename("shock")


def asset_returns() -> pd.DataFrame:
    frames = []
    for ticker in ASSETS:
        d = pd.read_csv(YAHOO / f"{ticker}.csv", parse_dates=["date"]).sort_values("date")
        frames.append(d.set_index("date")["adj_close"].pct_change().rename(ticker) * 100)
    return pd.concat(frames, axis=1)


def regress(y: pd.Series, x: pd.Series) -> dict:
    d = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    m = sm.OLS(d["y"], sm.add_constant(d["x"])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return dict(n=len(d), beta=m.params["x"], t=m.tvalues["x"], p=m.pvalues["x"], r2=m.rsquared)


def top_wallet_flow(trades: pd.DataFrame, order: list[str]) -> pd.Series:
    """Daily hawkish net flow (shares) of wallets in the top quintile on EARLIER meetings only."""
    t = trades.copy()
    label = t["rate_outcome"].str.lower()
    hawk = np.where(label.str.contains("increase"), 1, np.where(label.str.contains("decrease"), -1, 0))
    no_change = label.eq("no change")
    # buying YES on 'no change' is dovish relative to a priced hike and hawkish relative to a priced cut:
    # leave it out of the directional flow
    t["hawk_flow"] = np.where(no_change, 0, hawk * t["direction"] * t["shares"])
    local = t["timestamp_utc"].dt.tz_convert(NY)
    t["date"] = (local.dt.normalize() + pd.to_timedelta((local.dt.hour >= 16).astype(int), unit="D")).dt.tz_localize(None)
    flows = []
    for k in range(2, len(order)):
        form = wp.wallet_scores(trades.loc[trades["meeting"].isin(order[:k])])
        form = form.loc[form["trades"] >= wp.MIN_TRADES]
        top = set(form.index[form["adj"] >= form["adj"].quantile(.8)])
        part = t.loc[t["meeting"].eq(order[k]) & t["wallet_address"].isin(top)]
        flows.append(part.groupby("date")["hawk_flow"].sum())
    return pd.concat(flows).groupby(level=0).sum().rename("top_flow")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    markets = wp.market_table()
    # prices use every trade (announcement-day closes included); skill uses pre-decision trades only
    trades = pd.concat([wp.load_trade_files([row.file]).assign(meeting=row.meeting_month)
                        for row in markets.itertuples()], ignore_index=True)
    skill_trades = wp.add_adjusted_edge(wp.load_trades(markets))

    returns = asset_returns()
    prices = close_prices(trades)
    expected = expected_path(prices, markets)
    shock = daily_shock(expected, returns.index)
    shock = shock.loc[shock.index >= expected["date"].min()]
    data = returns.join(shock, how="inner").dropna(subset=["shock"])

    rows = []
    for ticker in ASSETS:
        for label_, x in (("same day", data["shock"]), ("placebo: shock 1 day later", data["shock"].shift(-1)),
                          ("forecast: shock 1 day earlier", data["shock"].shift(1))):
            rows.append(dict(asset=ticker, timing=label_, **regress(data[ticker], x)))
    big = data.loc[data["shock"].abs() >= 5]
    res = pd.DataFrame(rows)

    # wallet early warning, walk-forward on skill
    order = list(markets.groupby("meeting_month")["cutoff"].max().sort_values().index)
    flow = top_wallet_flow(skill_trades, order).reindex(data.index).fillna(0)
    flow = (flow - flow.mean()) / flow.std()          # standardised: beta = % return per 1 SD of flow
    joined = pd.concat([flow, shock], axis=1).dropna()
    lead = spearmanr(joined["top_flow"], joined["shock"].shift(-1), nan_policy="omit").statistic
    same = spearmanr(joined["top_flow"], joined["shock"], nan_policy="omit").statistic
    wallet = pd.DataFrame([dict(test="top-wallet hawkish flow on day d vs shock on day d+1 (early warning)", spearman=lead, n=int(joined["shock"].shift(-1).notna().sum())),
                           dict(test="same day (flow moves with the odds)", spearman=same, n=len(joined))])
    flow_ret = [dict(asset=a, **regress(data[a], flow.shift(1))) for a in ASSETS]

    # robustness of the one lead-lag hint: shock on day d-1 vs return on day d
    rng = np.random.default_rng(0)
    robust = []
    lagged = data["shock"].shift(1)
    keep = (data["shock"].abs() <= 10).shift(1, fill_value=True)
    half = len(data) // 2
    for a in ASSETS:
        obs = regress(data[a], lagged)
        perm = [abs(regress(data[a], pd.Series(rng.permutation(data["shock"].to_numpy()), index=data.index).shift(1))["t"])
                for _ in range(500)]
        robust.append(dict(asset=a, beta=obs["beta"], t=obs["t"],
                           t_drop_shocks_over_10bp=regress(data[a][keep], lagged[keep])["t"],
                           t_first_half=regress(data[a].iloc[:half], lagged.iloc[:half])["t"],
                           t_second_half=regress(data[a].iloc[half:], lagged.iloc[half:])["t"],
                           permutation_p=float(np.mean(np.array(perm) >= abs(obs["t"])))))
    pd.DataFrame(robust).to_csv(OUT / "lead_lag_robustness.csv", index=False)
    print(pd.DataFrame(robust).round(3).to_string(index=False))

    res.to_csv(OUT / "asset_sensitivity.csv", index=False)
    data.to_csv(OUT / "daily_shocks_and_returns.csv")
    wallet.to_csv(OUT / "wallet_early_warning.csv", index=False)
    pd.DataFrame(flow_ret).to_csv(OUT / "wallet_flow_vs_next_day_returns.csv", index=False)
    summary = dict(days=len(data), first=str(data.index.min().date()), last=str(data.index.max().date()),
                   big_shock_days=len(big), shock_sd_bp=float(data["shock"].std()))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(summary); print(res.round(4).to_string(index=False)); print(wallet.round(3).to_string(index=False))
    print(pd.DataFrame(flow_ret).round(4).to_string(index=False))
    print("big shock days, mean return % by sign:\n", big.assign(sign=np.sign(big["shock"])).groupby("sign")[ASSETS].mean().round(3))
    return data, res, wallet


if __name__ == "__main__":
    main()
