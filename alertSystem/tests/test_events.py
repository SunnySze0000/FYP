"""T2 on synthetic data: a planted event->asset link must be found, and none invented."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from walletlens import io
from walletlens.research.runner import run_suite
from walletlens.topics.events.collect import groups_for

T0 = 1_740_000_000 // 86_400 * 86_400


def _write_world(settings, link: float, seed: int = 2, markets: int = 120, days: int = 40):
    rng = np.random.default_rng(seed)
    hours = np.arange(T0, T0 + days * 86_400, 3600)
    market_rows, price_rows = [], []
    dlogit_by_market = {}
    for i in range(markets):
        logit = np.cumsum(rng.normal(0, 0.05, len(hours)) + (rng.random(len(hours)) < 0.02) * rng.normal(0, 1.2, len(hours)))
        p = 1 / (1 + np.exp(-(logit - logit[0])))
        market_id = str(10_000 + i)
        market_rows.append({"market_id": market_id, "condition_id": f"0x{i:064x}", "question": "Will the Fed cut rates?",
                            "category": "economics", "group_id": market_id, "yes_token": f"{i}1", "no_token": f"{i}2",
                            "start_ts": int(hours[0]), "end_ts": int(hours[-1]), "close_ts": int(hours[-1]),
                            "outcome_yes": 1, "volume_usd": 1e6, "resolution_source": "synthetic", "groups": "rates"})
        price_rows += [(market_id, int(t), float(v)) for t, v in zip(hours, p)]
        dlogit_by_market[market_id] = np.diff(np.log(np.clip(p, .01, .99) / (1 - np.clip(p, .01, .99))), prepend=0)
    # one shared driver: the average event move drives the related assets each hour (with link > 0)
    driver = np.sum([dlogit_by_market[m] for m in dlogit_by_market], axis=0)
    asset_rows = []
    for symbol in ("TLT", "IEF", "SHY", "UUP", "XLF", "SPY", "FXI", "KWEB", "EEM", "USO", "XLE", "GLD", "ITA", "EZU",
                   "IWM", "NVDA", "SMH", "QQQ", "MSFT", "BTC-USD", "ETH-USD", "COIN", "MSTR"):
        related = symbol in ("TLT", "IEF", "SHY", "UUP", "XLF")
        returns = rng.normal(0, 0.002, len(hours)) + (link * driver if related else 0)
        close = 100 * np.exp(np.cumsum(returns))
        session = [(h % 86_400) // 3600 in range(14, 21) and ((h // 86_400) + 4) % 7 < 5 for h in hours]
        asset_rows += [(symbol, int(t) - 3600, int(t), float(c)) for t, c, s in zip(hours, close, session) if s]
    folder = settings.paths.dataset("events")
    io.write_csv(folder / "markets.csv", pd.DataFrame(market_rows))
    io.write_table(folder / "prices.pkl.gz", pd.DataFrame(price_rows, columns=["market_id", "ts", "yes_price"]))
    hourly = pd.DataFrame(asset_rows, columns=["symbol", "start_ts", "end_ts", "close"])
    io.write_table(folder / "assets_hourly.pkl.gz", hourly)
    io.write_table(folder / "assets_daily.pkl.gz", hourly.iloc[:0])
    io.write_json(folder / "manifest.json", {"dataset": "events", "markets": markets})


def test_keyword_groups():
    assert "rates" in groups_for("Will the Fed cut interest rates in March?")
    assert "trade_china" in groups_for("Will Trump raise tariffs on China?")
    assert groups_for("Will it rain in Paris?") == []


@pytest.mark.parametrize("link, expect", [(0.01, "pass"), (0.0, "fail")])
def test_events_suite(settings, link, expect):
    settings.events.bootstrap_draws = 300
    _write_world(settings, link)
    manifest = run_suite(settings, "events", "events", f"events_{link}")
    assert manifest["verdicts"]["v0"] == "pass"
    assert manifest["verdicts"]["v1"] == expect
    assert manifest["verdicts"]["v3"] == "inconclusive"         # no topic-F trades in this world


def test_events_collector_end_to_end(settings, world):
    from walletlens.collect import pipeline
    from walletlens.topics.events import collect as events_collect
    from conftest import FakeApi
    for market in world["gamma"]:
        market["question"] = "Will the Fed cut interest rates? " + market["question"]
    api = FakeApi(world)
    pipeline.run(settings, stages=("universe",), fetch=api)
    events_collect.run(settings, fetch=api)
    manifest = io.read_json(settings.paths.dataset("events") / "manifest.json")
    assert manifest["markets"] > 0 and manifest["assets_hourly"]
