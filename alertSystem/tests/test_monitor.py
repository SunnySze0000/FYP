"""EventLens monitor: keyword links, live features and the forward journal."""

from walletlens.monitor.engine import early_warning, hourly_grid, wallet_hours
from walletlens.monitor.journal import Journal
from walletlens.topics.events.collect import groups_for


def test_keywords_match_whole_words():
    assert groups_for("Will the Edmonton Oilers win the Stanley Cup?") == []
    assert groups_for("Will BV Borussia 09 Dortmund win?") == []
    assert groups_for("Will the Ottawa Senators win?") == []
    assert groups_for("Will the Iranian regime fall?") == ["energy_mideast"]
    assert "trade_china" in groups_for("Trump’s tariffs on China above 50%?")


MODEL = {"features": ["abs_dp", "recent_vol", "gross_z", "whale_z", "wallets_z", "imbalance"],
         "mean": [0] * 6, "std": [1] * 6, "beta": [-6, 0, 0, 0.1, 0, 1, 0], "threshold": -4.0,
         "jump_rate_all": 0.003, "trailing_hours": 48}


def test_wallet_surge_raises_the_early_warning():
    now = 100 * 3600.0
    quiet = [{"ts": int(now - k * 3600 - 60), "usd": 300, "yes_dir": 1, "wallet": "a"} for k in range(1, 49)]
    surge = [{"ts": int(now - 60 - i), "usd": 300, "yes_dir": 1, "wallet": f"w{i}"} for i in range(40)]
    calm = early_warning(MODEL, 0.0, 0.0, wallet_hours(quiet, now, 49, 5000))
    busy = early_warning(MODEL, 0.0, 0.0, wallet_hours(quiet + surge, now, 49, 5000))
    assert not calm["flag"] and busy["flag"] and busy["driver"] == "wallets_z"


def test_grid_uses_last_known_price():
    grid = hourly_grid([(0, 0.2), (3600, 0.5)], 3 * 3600, 2)
    assert grid == [(3600, 0.5), (7200, 0.5), (10800, 0.5)]


def test_journal_logs_once_and_scores(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    scan = {"ok": True, "source": "live", "updated_at": 10 * 3600 + 100, "markets": [
        {"id": "1", "question": "q", "alert": True, "dp_1h": 0.12, "assets": ["SPY"], "reliable": True,
         "warning": {"flag": False}, "pressure_usd": 0.0}]}
    assert journal.record(scan) == 1 and journal.record(scan) == 0
    bars = {"SPY": [(9 * 3600, 100.0), (10 * 3600, 102.0), (11 * 3600, 102.0)]}
    assert journal.score(bars, {"SPY": {"big_threshold": 0.01}}, 20 * 3600) == 1
    summary = journal.summary()
    assert summary["scored_pairs"] == 1 and summary["big_moves"] == 1


def test_portfolio_links_and_terms():
    from walletlens.monitor.holdings import candidate_groups, decide_links, mention_terms, mentions
    voo = {"symbol": "VOO", "type": "ETF", "name": "Vanguard S&P 500 ETF", "sector": None, "industry": None}
    assert "trade_china" in candidate_groups(voo)[0]
    xom = {"symbol": "XOM", "type": "EQUITY", "name": "Exxon Mobil Corporation", "sector": "Energy", "industry": "Oil & Gas Integrated"}
    assert candidate_groups(xom)[0][0] == "energy_mideast"
    tsla = {"symbol": "TSLA", "type": "EQUITY", "name": "Tesla, Inc.", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"}
    terms = mention_terms(tsla)
    assert mentions("Will Elon Musk tweet 500 times?", terms) and mentions("Tesla deliveries above 400k?", terms)
    assert not mentions("Will the Edmonton Oilers win?", terms)
    links = decide_links(["rates", "macro", "us_politics"], {
        "rates": {"effect": 0.3, "low": 0.05, "high": 0.5, "jump_hours": 40},
        "macro": {"effect": -0.2, "low": -0.4, "high": 0.0, "jump_hours": 30},
        "crypto": {"effect": 0.5, "low": 0.3, "high": 0.7, "jump_hours": 200}})
    assert links == {"rates": "confirmed", "macro": "dropped", "us_politics": "weak"}     # history never adds crypto


def test_cross_market_signal_fires():
    import numpy as np
    import pandas as pd
    from walletlens.monitor.holding_wallets import window_signals
    rows = []
    for h in range(60):                                   # quiet: one wallet, one market per hour
        rows.append({"ts": h * 3600 + 100, "wallet": "a", "market_id": "m1", "notional": 300, "cluster_id": "none"})
    for i in range(6):                                    # last hour: 6 wallets each trade two markets
        for m in ("m1", "m2"):
            rows.append({"ts": 60 * 3600 + 200 + i, "wallet": f"w{i}", "market_id": m, "notional": 300, "cluster_id": "none"})
    flags = window_signals(pd.DataFrame(rows), np.array([60 * 3600, 61 * 3600], dtype=np.int64))
    assert not flags["cross"][0] and flags["cross"][1]
