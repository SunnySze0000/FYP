"""Shared fixtures: a synthetic Polymarket with *planted* skilled wallets, and a fake API.

If the pipeline is correct, the research must find the planted skill (and nothing in a
world without it). This is the end-to-end check that the maths and the plumbing agree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from walletlens.config import load_settings  # noqa: E402

DAY = 86_400
T0 = 1_735_689_600  # 2025-01-01


def synthetic_world(seed: int = 1, events: int = 16, markets_per_event: int = 3, skilled: int = 30,
                    noise: int = 300, skill_strength: float = 0.25, trades_per_market: int = 900):
    """Gamma-like markets, Data-API-like trade records and hourly price points.

    A skilled wallet trades in the direction of the true outcome with probability
    0.5 + skill_strength; everyone else trades at random.
    """
    rng = np.random.default_rng(seed)
    wallets = [f"0x{i:040x}" for i in range(skilled + noise)]
    gamma, trade_records, prices = [], {}, {}
    market_id = 1000
    for event in range(events):
        start = T0 + event * 20 * DAY
        close = start + 18 * DAY
        for _ in range(markets_per_event):
            market_id += 1
            truth = float(rng.uniform(0.2, 0.8))
            outcome = int(rng.random() < truth)
            yes_token, no_token = f"{market_id}1", f"{market_id}2"
            condition = f"0x{market_id:064x}"
            gamma.append({
                "id": str(market_id), "question": f"Synthetic event {event} market {market_id}?",
                "conditionId": condition, "outcomes": '["Yes", "No"]',
                "outcomePrices": json.dumps(["1", "0"] if outcome else ["0", "1"]),
                "clobTokenIds": json.dumps([yes_token, no_token]),
                "startDate": _iso(start), "endDate": _iso(close), "closedTime": _iso(close).replace("T", " ")[:-1] + "+00",
                "volumeNum": 250_000, "negRiskMarketID": f"event-{event}"})
            # price path drifts from the prior towards the outcome
            hours = np.arange(start, close, 3600)
            progress = (hours - start) / (close - start)
            path = np.clip(truth + (outcome - truth) * progress ** 2 + rng.normal(0, 0.03, len(hours)), 0.02, 0.98)
            prices[yes_token] = [{"timestamp": int(t), "price": round(float(p), 4)} for t, p in zip(hours, path)]
            records = []
            for _ in range(trades_per_market):
                index = int(rng.integers(len(wallets)))
                when = int(rng.integers(start, close - 3600))
                p_yes = float(path[(when - start) // 3600])
                knows = index < skilled and rng.random() < 2 * skill_strength
                wants_yes = (outcome == 1) if knows else bool(rng.random() < 0.5)
                token = yes_token if rng.random() < 0.5 else no_token
                buy = wants_yes == (token == yes_token)
                price = p_yes if token == yes_token else 1 - p_yes
                records.append({"token_id": token, "proxy_wallet": wallets[index], "side": "BUY" if buy else "SELL",
                                "price": round(price, 4), "size": float(rng.integers(100, 2000)),
                                "timestamp": when, "transaction_hash": f"0x{rng.integers(1 << 60):064x}",
                                "condition_id": condition})
            records.sort(key=lambda r: -r["timestamp"])            # API serves newest first
            trade_records[condition] = records
    return {"gamma": gamma, "trades": trade_records, "prices": prices, "wallets": wallets, "skilled": skilled}


def _iso(ts: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeApi:
    """Answers the same URLs the collector calls, from a synthetic world."""

    def __init__(self, world: dict, page_size: int = 250):
        self.world, self.page_size, self.calls = world, page_size, []

    def __call__(self, url: str, params: dict | None = None):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        self.calls.append((url, params))
        if url.endswith("/markets") and "slug" in params:
            wanted = set(params["slug"] if isinstance(params["slug"], list) else [params["slug"]])
            return [m for m in self.world["gamma"] if m.get("slug") in wanted]
        if url.endswith("/markets"):
            low, high = params["end_date_min"], params["end_date_max"]
            chosen = [m for m in self.world["gamma"] if low <= m["endDate"] < high]
            offset = int(params.get("offset", 0))
            return chosen[offset: offset + int(params["limit"])]
        if url.endswith("/v2/prices-history"):
            return {"data": self.world["prices"].get(params["token_id"], []), "pagination": {}}
        if url.endswith("/v2/trades"):
            records = self.world["trades"][params["condition"]]
            start = int(params.get("cursor") or 0)
            limit = min(int(params["limit"]), self.page_size)
            page = records[start: start + limit]
            following = start + limit
            return {"data": page, "pagination": {"next_cursor": str(following) if following < len(records) else None}}
        if url.endswith("/api/v3/klines"):
            return []
        if "/v8/finance/chart/" in url:
            start = min(m["startDate"] for m in self.world["gamma"])
            from datetime import datetime
            t0 = int(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp())
            step = 3600 if params.get("interval") == "60m" else 86_400
            stamps = list(range(t0, t0 + 400 * 86_400, step))[:5000]
            closes = [100 + (i % 7) * 0.1 for i in range(len(stamps))]
            return {"chart": {"result": [{"timestamp": stamps, "indicators": {"quote": [{"close": closes}]}}]}}
        raise AssertionError(f"unexpected URL {url}")


@pytest.fixture
def world():
    return synthetic_world()


@pytest.fixture
def settings(tmp_path):
    settings = load_settings(root=tmp_path)
    settings.collect.closed_from = "2025-01-01"
    settings.collect.closed_to = "2026-01-31"
    settings.collect.min_volume_usd = 0
    settings.collect.sample_size = 1000
    settings.research.persistence_min_markets = 3
    settings.research.bootstrap_draws = 300
    settings.research.permutations = 200
    return settings
