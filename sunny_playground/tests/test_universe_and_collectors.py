import json

import numpy as np
import pandas as pd

from eventlens.analysis import universe
from eventlens.collectors.gamma import parse_market
from eventlens.collectors.prices import _iso
from eventlens.collectors.yahoo import parse_chart


def synthetic_universe(n_markets: int, biased: bool, seed: int = 3):
    """Markets closing over 24 months; if `biased`, longshots win less often than priced."""
    rng = np.random.default_rng(seed)
    close = pd.Timestamp("2024-01-01", tz="UTC") + pd.to_timedelta(rng.uniform(0, 720, n_markets), unit="D")
    price = rng.uniform(0.02, 0.98, n_markets)
    true_p = np.clip(price + (0.6 * (price - 0.5) * (1 - abs(2 * price - 1)) if biased else 0), 0.01, 0.99)
    if biased:
        true_p = np.where(price < 0.15, price * 0.3, np.where(price > 0.85, 1 - (1 - price) * 0.3, true_p))
    won = (rng.uniform(size=n_markets) < true_p).astype(int)
    markets = pd.DataFrame({
        "market_id": [str(i) for i in range(n_markets)], "event_id": [str(i // 2) for i in range(n_markets)],
        "category": "x", "closed_time": close.astype(str), "end_date": close.astype(str),
        "yes_won": won, "volume_usd": 1e5,
    })
    prices = pd.DataFrame({
        "market_id": markets["market_id"], "timestamp_utc": (close - pd.Timedelta(days=10)).astype(str), "yes_price": price,
    })
    return markets, prices


def test_walk_forward_rule_finds_planted_bias_and_not_a_fake_one():
    biased = universe.panel_from_frames(*synthetic_universe(6000, biased=True), horizons_days=(7,))
    fair = universe.panel_from_frames(*synthetic_universe(6000, biased=False), horizons_days=(7,))
    found = universe.walk_forward_rule(biased).iloc[0]
    assert found["mean_return"] > 0.03 and found["ci_low"] > 0
    fair_result = universe.walk_forward_rule(fair)
    assert fair_result.empty or fair_result["trades"].iloc[0] < 100  # stays out of a fairly priced market


def test_walk_forward_never_trains_on_test_month():
    panel = universe.panel_from_frames(*synthetic_universe(3000, biased=True), horizons_days=(7,))
    trades = universe.walk_forward_trades(panel, 7)
    first_test = trades["close_month"].min().to_timestamp().tz_localize("UTC")
    assert first_test > panel["close_time"].min()


def test_parse_market_handles_yes_no_and_rejects_unresolved():
    raw = {"id": 5, "question": "Q", "outcomes": json.dumps(["Yes", "No"]), "outcomePrices": json.dumps(["0", "1"]),
           "clobTokenIds": json.dumps(["111", "222"]), "events": [{"id": 9}], "volumeNum": 100}
    record = parse_market(raw)
    assert record["yes_won"] == 0 and record["yes_token_id"] == "111" and record["event_id"] == "9"
    raw["outcomePrices"] = json.dumps(["0.4", "0.6"])
    assert parse_market(raw) is None


def test_parse_market_finds_yes_when_listed_second():
    raw = {"id": 1, "outcomes": '["No", "Yes"]', "outcomePrices": '["0", "1"]', "clobTokenIds": '["a", "b"]'}
    record = parse_market(raw)
    assert record["yes_token_id"] == "b" and record["yes_won"] == 1


def test_closed_time_format_is_converted():
    assert _iso("2024-11-06 05:12:00+00") == "2024-11-06T05:12:00+00:00"


def test_parse_chart_skips_missing_values():
    payload = {"chart": {"result": [{
        "timestamp": [1704205800, 1704292200],
        "indicators": {"quote": [{"close": [470.0, None]}], "adjclose": [{"adjclose": [465.0, None]}]},
    }]}}
    rows = parse_chart("SPY", payload)
    assert rows == [{"date": "2024-01-02", "ticker": "SPY", "close": 470.0, "adj_close": 465.0}]
