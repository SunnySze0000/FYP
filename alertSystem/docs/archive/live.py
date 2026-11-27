"""Live Polymarket data for the app, joined with research results.

Everything is cached for a short time so the UI stays fast and the public API is not hammered.
"""

from __future__ import annotations

import math
import threading
import time

from walletlens.data.markets import parse_time
from walletlens.data.schema import categorise
from walletlens.polymarket import api
from walletlens.polymarket.http import get_json


def fair_value(price: float | None, params: dict) -> float | None:
    if price is None:
        return None
    if not params or not params.get("fitted"):
        return price
    p = min(max(price, 0.005), 0.995)
    x = params["a"] + params["b"] * math.log(p / (1 - p))
    return 1 / (1 + math.exp(-x))


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TTLCache:
    def __init__(self, seconds: int):
        self.seconds, self._data, self._lock = seconds, {}, threading.Lock()

    def get(self, key, compute):
        now = time.time()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < self.seconds:
                return hit[1]
        value = compute()
        with self._lock:
            self._data[key] = (now, value)
        return value


def summarise_market(market: dict, fair_params: dict) -> dict | None:
    labels = [str(x).lower() for x in api.as_list(market.get("outcomes"))]
    tokens = api.as_list(market.get("clobTokenIds"))
    if labels not in (["yes", "no"], ["up", "down"]) or len(tokens) != 2:
        return None
    prices = api.as_list(market.get("outcomePrices"))
    price = _float(prices[0]) if prices else None
    if price is None:
        price = _float(market.get("lastTradePrice"))
    fair = fair_value(price, fair_params)
    events = market.get("events") if isinstance(market.get("events"), list) else []
    return {
        "id": str(market.get("id")), "question": market.get("question"), "slug": market.get("slug"),
        "event_slug": events[0].get("slug") if events else None,
        "category": categorise(str(market.get("question", ""))), "image": market.get("icon") or market.get("image"),
        "price": price, "fair": fair, "fair_gap": (fair - price) if fair is not None and price is not None else None,
        "best_bid": _float(market.get("bestBid")), "best_ask": _float(market.get("bestAsk")),
        "spread": _float(market.get("spread")), "volume_24h": _float(market.get("volume24hr")) or 0.0,
        "volume": _float(market.get("volumeNum")) or 0.0, "liquidity": _float(market.get("liquidityNum")) or 0.0,
        "end_ts": parse_time(market.get("endDate")), "one_day_change": _float(market.get("oneDayPriceChange")),
        "condition_id": market.get("conditionId"), "yes_token": str(tokens[0]), "no_token": str(tokens[1]),
    }


def summarise_trades(records: list[dict], market: dict, wallet_index: dict, now: float) -> dict:
    """YES-terms trades of one market with each wallet's research tier, and flows by tier."""
    trades = []
    for record in records:
        token = str(record.get("token_id") or record.get("asset") or "")
        if token not in (market["yes_token"], market["no_token"]):
            continue
        price, size = _float(record.get("price")), _float(record.get("size"))
        if price is None or size is None:
            continue
        is_yes = token == market["yes_token"]
        buy = str(record.get("side", "")).upper() == "BUY"
        wallet = str(record.get("proxy_wallet") or record.get("proxyWallet") or "").lower()
        score = wallet_index.get(wallet)
        trades.append({
            "ts": int(record.get("timestamp", 0)), "wallet": wallet,
            "yes_dir": 1 if is_yes == buy else -1, "yes_price": price if is_yes else 1 - price,
            "usd": price * size, "tier": score["tier"] if score else "unranked",
            "rank": score["rank"] if score else None, "skill": score["shrunk"] if score else None,
            "name": record.get("name") or record.get("pseudonym") or "",
        })
    flows = {}
    for window, seconds in (("24h", 86_400), ("7d", 7 * 86_400), ("all", 10 ** 12)):
        bucket = {"top": 0.0, "ranked": 0.0, "unranked": 0.0, "top_gross": 0.0}
        for trade in trades:
            if now - trade["ts"] <= seconds:
                bucket[trade["tier"]] += trade["yes_dir"] * trade["usd"]
                if trade["tier"] == "top":
                    bucket["top_gross"] += trade["usd"]
        bucket["top_lean"] = bucket["top"] / bucket["top_gross"] if bucket["top_gross"] else None
        flows[window] = bucket
    notable = sorted(trades, key=lambda t: (t["tier"] != "top", -t["usd"]))[:40]
    return {"count": len(trades), "flows": flows, "notable": notable,
            "oldest_ts": min((t["ts"] for t in trades), default=None)}


class LiveService:
    def __init__(self, fetch=get_json, ttl: int = 60):
        self.fetch, self.cache = fetch, TTLCache(ttl)

    def markets(self, fair_params: dict, limit: int = 200) -> list[dict]:
        def load():
            rows = []
            for offset in range(0, limit, 100):
                rows += api.gamma_active_markets(limit=100, offset=offset, fetch=self.fetch)
            return rows
        raw = self.cache.get(("markets", limit), load)
        out = [summarise_market(m, fair_params) for m in raw]
        return [m for m in out if m and m["price"] is not None]

    def market(self, market_id: str, fair_params: dict, wallet_index: dict) -> dict:
        raw = self.cache.get(("market", market_id), lambda: api.gamma_market(market_id, self.fetch))
        summary = summarise_market(raw, fair_params)
        if summary is None:
            raise ValueError("Only binary Yes/No markets are supported")
        history, source = self.cache.get(("history", market_id),
                                         lambda: api.price_history(summary["yes_token"], 3600, self.fetch))
        if len(history) > 600:
            step = len(history) / 600
            history = [history[int(i * step)] for i in range(600)] + [history[-1]]
        records = self.cache.get(("trades", market_id),
                                 lambda: api.recent_trades(summary["condition_id"], 1000, self.fetch))
        return {"market": summary, "description": raw.get("description", ""),
                "prices": [[p["t"], p["p"]] for p in history], "price_source": source,
                "trades": summarise_trades(records, summary, wallet_index, time.time())}

    def wallet_activity(self, wallet: str) -> list[dict]:
        records = self.cache.get(("wallet", wallet), lambda: api.wallet_trades(wallet, 100, self.fetch))
        out = []
        for r in records:
            out.append({"ts": int(r.get("timestamp", 0)), "title": r.get("title") or r.get("slug") or "",
                        "outcome": r.get("outcome"), "side": r.get("side"), "price": _float(r.get("price")),
                        "size": _float(r.get("size")), "usd": (_float(r.get("price")) or 0) * (_float(r.get("size")) or 0),
                        "slug": r.get("eventSlug") or r.get("slug")})
        return out
