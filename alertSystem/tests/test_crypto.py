"""T1 end to end on synthetic data: a planted lead must be found, and none invented."""

from __future__ import annotations

import pytest

from walletlens import io
from walletlens.research.runner import run_suite
from walletlens.topics.crypto import collect
from conftest import FakeApi
from crypto_world import crypto_world, fake_binance


def _configure(settings):
    settings.crypto.closed_from = "2026-03-01"
    settings.crypto.closed_to = "2026-04-20"
    settings.crypto.min_volume_usd = 0
    settings.crypto.per_kind = {"1h": 10_000}
    settings.crypto.min_train_days = 10
    settings.crypto.bootstrap_draws = 300
    return settings


def test_slugs_match_polymarket():
    assert collect.slug_for("BTC", "5m", 1788225000) == "btc-updown-5m-1788225000"
    assert collect.slug_for("ETH", "15m", 1788224400) == "eth-updown-15m-1788224400"
    start = 1788238800                                            # 2026-09-01 05:00 UTC = 1 AM EDT
    assert collect.slug_for("BTC", "1h", start) == "bitcoin-up-or-down-september-1-2026-1am-et"
    assert collect.slug_for("ETH", "1h", start + 12 * 3600) == "ethereum-up-or-down-september-1-2026-1pm-et"
    winter = 1795669200                                           # 2026-11-26 05:00 UTC = 12 AM EST
    assert collect.slug_for("BTC", "1h", winter) == "bitcoin-up-or-down-november-26-2026-12am-et"
    starts = collect.candidate_windows("BTC", "4h", "2026-08-31", "2026-09-01")
    assert 1788206400 in starts                                   # 4 PM EDT window seen on Polymarket


def test_classify_questions():
    assert collect.classify({"question": "Bitcoin Up or Down - November 25, 3PM ET",
                             "endDate": "2026-11-25T21:00:00Z"})["kind"] == "1h"
    assert collect.classify({"question": "Ethereum Up or Down - November 25, 3:00PM-3:15PM ET",
                             "endDate": "2026-11-25T20:15:00Z"})["kind"] == "15m"
    assert collect.classify({"question": "Bitcoin Up or Down - November 25, 12:00PM-4:00PM ET",
                             "endDate": "2026-11-25T21:00:00Z"})["kind"] == "4h"
    assert collect.classify({"question": "Bitcoin Up or Down on November 25?",
                             "endDate": "2026-11-25T17:00:00Z"})["kind"] == "1d"
    assert collect.classify({"question": "Will Bitcoin reach $100k?", "endDate": "2026-11-25T17:00:00Z"}) is None


@pytest.mark.parametrize("lead, expect_pass", [(0.6, True), (0.0, False)])
def test_crypto_suite_detects_lead_only_when_present(settings, lead, expect_pass):
    settings = _configure(settings)
    world = crypto_world(lead=lead)
    collect.run(settings, fetch=FakeApi(world, page_size=1000), fetch_bytes=fake_binance(world))
    manifest = run_suite(settings, "crypto", "crypto", f"lead_{lead}")
    verdicts = manifest["verdicts"]
    assert verdicts["c0"] == "pass"                               # windows align with the spot candles
    assert (verdicts["c1"] == "pass") == expect_pass
    c1 = io.read_json(settings.paths.results / f"lead_{lead}" / "c1" / "summary.json")
    if not expect_pass:
        assert c1["metrics"]["main"]["low"] <= 0
