"""Unit tests for the building blocks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from walletlens.analytics.calibration import fit_fair_value, sigmoid, logit
from walletlens.analytics.markout import PriceBook, add_markouts, copy_backtest
from walletlens.analytics.skill import SkillTimeline
from walletlens.analytics.stats import cluster_bootstrap_mean, spearman_test
from walletlens.collect.common import collect_window
from walletlens.data.markets import market_row, parse_time
from walletlens.data.schema import add_yes_terms


def test_yes_terms_cover_all_four_trade_types():
    trades = pd.DataFrame({"token": ["YES", "YES", "NO", "NO"], "side": ["BUY", "SELL", "BUY", "SELL"],
                           "price": [0.3, 0.3, 0.7, 0.7], "shares": [10.0] * 4})
    out = add_yes_terms(trades)
    assert out["yes_dir"].tolist() == [1, -1, -1, 1]
    assert np.allclose(out["yes_price"], 0.3)
    # profit if YES wins = yes_dir * shares * (1 - yes_price): buyer of YES and seller of NO gain 7
    assert np.allclose(out["yes_dir"] * 10 * (1 - out["yes_price"]), [7, -7, -7, 7])


def test_gamma_times_and_outcomes():
    assert parse_time("2026-07-29 20:01:42+00") == parse_time("2026-07-29T20:01:42Z")
    row, reason = market_row({"id": 1, "question": "Will the Fed cut?", "conditionId": "0xAB",
                              "outcomes": '["Yes", "No"]', "outcomePrices": '["0", "1"]',
                              "clobTokenIds": '["1", "2"]', "startDate": "2026-01-01T00:00:00Z",
                              "closedTime": "2026-02-01 00:00:00+00"})
    assert reason == "ok" and row["outcome_yes"] == 0 and row["category"] == "economics"
    _, reason = market_row({"id": 2, "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]',
                            "clobTokenIds": '["1", "2"]'})
    assert reason == "unresolved_or_ambiguous"


def test_skill_timeline_never_looks_ahead():
    wm = pd.DataFrame({"wallet": ["w"] * 3, "close_ts": [100, 200, 300], "edge": [0.5, 0.5, -0.5]})
    timeline = SkillTimeline(wm, k=0, min_markets=1, top_fraction=0.5)
    looked = timeline.lookup(pd.Series(["w", "w", "w", "w"]), pd.Series([100, 101, 250, 301]))
    assert looked["prior_markets"].tolist() == [0, 1, 2, 3]          # a market closing AT ts is not yet known
    assert np.allclose(looked["prior_skill"], [0, 0.5, 0.5, 0.5 / 3])


def test_fair_value_recovers_known_miscalibration():
    rng = np.random.default_rng(0)
    price = rng.uniform(0.02, 0.98, 20_000)
    truth = sigmoid(0.2 + 0.8 * logit(price))
    fair = fit_fair_value(price, rng.random(20_000) < truth)
    assert fair.fitted and abs(fair.a - 0.2) < 0.06 and abs(fair.b - 0.8) < 0.06
    assert not fit_fair_value(price[:50], (rng.random(50) < 0.5)).fitted   # too little data -> identity


def test_markouts_and_copy_backtest():
    markets = pd.DataFrame({"market_id": ["m"], "close_ts": [10_000], "outcome_yes": [1], "group_id": ["g"]})
    prices = pd.DataFrame({"market_id": ["m", "m", "m"], "ts": [0, 1000, 5000], "yes_price": [0.4, 0.5, 0.8]})
    book = PriceBook(prices)
    trades = add_yes_terms(pd.DataFrame({"market_id": ["m"], "ts": [500], "token": ["YES"], "side": ["BUY"],
                                         "price": [0.4], "shares": [1.0]}))
    out = add_markouts(trades, markets, book, [600, 20_000])
    assert out["markout_600"].iloc[0] == pytest.approx(0.1)       # price 0.5 at t=1100
    assert out["markout_20000"].iloc[0] == pytest.approx(0.6)     # past close -> resolution
    fills = copy_backtest(trades, markets, book, delay_s=600, cost=0.01, band=(0.05, 0.95))
    assert fills["entry_price"].iloc[0] == pytest.approx(0.51)
    assert fills["return_per_dollar"].iloc[0] == pytest.approx(1 / 0.51 - 1)


def test_stats_behave():
    rng = np.random.default_rng(1)
    x = rng.normal(size=300)
    assert spearman_test(x, x + rng.normal(size=300), 300, 0)["p_one_sided"] < 0.01
    assert spearman_test(x, rng.normal(size=300), 300, 0)["p_one_sided"] > 0.01
    groups = np.repeat(np.arange(30), 10)
    stat = cluster_bootstrap_mean(rng.normal(1, 1, 300), groups, 500, 0)
    assert stat["low"] < 1 < stat["high"] and stat["groups"] == 30


def test_gamma_window_splits_at_offset_cap(settings):
    """A window with more markets than the offset cap is split, and nothing is lost."""
    from datetime import datetime, timezone
    markets = [{"id": i, "endDate": f"2025-01-{1 + i % 28:02d}T00:00:00Z"} for i in range(2500)]

    def fetch(url, params):
        chosen = [m for m in markets if params["end_date_min"] <= m["endDate"] < params["end_date_max"]]
        return chosen[params["offset"]: params["offset"] + params["limit"]]

    left = datetime(2025, 1, 1, tzinfo=timezone.utc)
    right = datetime(2025, 1, 29, tzinfo=timezone.utc)
    got = collect_window(settings.paths.raw / 'gamma', {}, left, right, fetch)
    again = collect_window(settings.paths.raw / 'gamma', {}, left, right, lambda *a: 1 / 0)   # fully cached
    assert sorted(m["id"] for m in got) == list(range(2500))
    assert sorted(m["id"] for m in again) == list(range(2500))
