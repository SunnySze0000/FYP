import pandas as pd
import pytest

from eventlens.analysis import wallets
from eventlens.data.loaders import _add_yes_equivalents


def make_trades(rows):
    frame = pd.DataFrame(rows, columns=["timestamp_utc", "market_id", "wallet_address", "token_outcome",
                                        "side", "shares", "price", "signed_yes_shares"])
    frame["rate_outcome"] = "no change"
    frame["notional_usd"] = frame["shares"] * frame["price"]
    return _add_yes_equivalents(frame)


def test_no_token_trades_convert_to_yes_terms():
    trades = make_trades([("2026-03-01T00:00:00Z", "m", "w", "NO", "BUY", 10, 0.3, -10)])
    assert trades.loc[0, "yes_price"] == pytest.approx(0.7)
    assert trades.loc[0, "direction"] == -1


def test_markout_is_positive_when_price_moves_in_trade_direction():
    trades = make_trades([
        ("2026-03-01T00:10:00Z", "m", "buyer", "YES", "BUY", 10, 0.40, 10),
        ("2026-03-01T00:10:00Z", "m", "seller", "YES", "SELL", 10, 0.40, -10),
        ("2026-03-02T01:30:00Z", "m", "other", "YES", "BUY", 10, 0.60, 10),
    ])
    bars = wallets.price_bars(trades, "1h")
    result = wallets.add_markouts(trades, bars, horizons_h=(24,)).set_index("wallet_address")
    assert result.loc["buyer", "markout_24h"] == pytest.approx(0.0)  # only the 00:00-01:00 bar is known by 00:10+24h
    later = wallets.add_markouts(trades, bars, horizons_h=(26,)).set_index("wallet_address")
    assert later.loc["buyer", "markout_26h"] == pytest.approx(0.20)
    assert later.loc["seller", "markout_26h"] == pytest.approx(-0.20)


def test_resolution_pnl_sign():
    trades = make_trades([("2026-03-01T00:00:00Z", "m", "w", "YES", "BUY", 10, 0.4, 10)])
    result = wallets.add_resolution_pnl(trades, {"m": 1})
    assert result.loc[0, "resolution_pnl_usd"] == pytest.approx(6.0)


def test_scores_shrink_small_samples():
    trades = pd.DataFrame({
        "wallet_address": ["lucky", "steady", "steady"], "market_id": ["m"] * 3,
        "shares": [10, 5000, 5000], "notional_usd": [5, 2500, 2500], "value": [5, 500, 500],
    })
    scores = wallets.wallet_scores(trades, "value", prior_shares=2000).set_index("wallet_address")["score"]
    assert scores["steady"] > scores["lucky"]


def test_formation_period_excludes_trades_whose_markout_ends_after_cutoff():
    windows = wallets.StudyWindows(pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-02-01", tz="UTC"),
                                   pd.Timestamp("2026-03-01", tz="UTC"))
    stamps = pd.to_datetime(["2026-01-30T12:00:00Z", "2026-01-31T12:00:00Z", "2026-02-05T00:00:00Z"])
    trades = pd.DataFrame({"timestamp_utc": stamps})
    formation, test = wallets.split_periods(trades, windows)
    assert len(formation) == 1 and len(test) == 1


def test_persistence_refuses_tiny_samples():
    scores = pd.DataFrame({"wallet_address": list("abc"), "trades": [50] * 3, "score": [0.1, 0.2, 0.3],
                           "value_usd": [1.0] * 3, "shares": [1.0] * 3, "notional_usd": [1.0] * 3})
    with pytest.raises(ValueError):
        wallets.persistence(scores, scores, min_trades=1)
