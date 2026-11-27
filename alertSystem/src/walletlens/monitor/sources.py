"""Where the monitor gets its data: live public APIs, or a replay of the research dataset at a past moment.

Both expose the same five calls, so the engine and the tests do not care which one is used.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from walletlens import io
from walletlens.data.schema import add_yes_terms
from walletlens.polymarket import api, yahoo
from walletlens.polymarket.http import get_json
from walletlens.topics.events.collect import DTYPES, groups_for


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LiveSource:
    name = "live"

    def __init__(self, fetch=get_json, scan_pages: int = 5):
        self.fetch, self.scan_pages = fetch, scan_pages

    def now(self) -> float:
        return time.time()

    def active_markets(self) -> list[dict]:
        rows = []
        for page in range(self.scan_pages):
            rows += api.gamma_active_markets(limit=100, offset=page * 100, fetch=self.fetch) or []
        out, seen = [], set()
        for m in rows:
            if str(m.get("id")) in seen:          # pages can overlap when the volume order shifts
                continue
            seen.add(str(m.get("id")))
            labels = [str(x).lower() for x in api.as_list(m.get("outcomes"))]
            tokens = api.as_list(m.get("clobTokenIds"))
            prices = api.as_list(m.get("outcomePrices"))
            if labels != ["yes", "no"] or len(tokens) != 2 or not prices or not m.get("conditionId"):
                continue
            events = m.get("events") if isinstance(m.get("events"), list) else []
            out.append({"id": str(m.get("id")), "question": m.get("question") or "", "condition_id": m["conditionId"],
                        "yes_token": str(tokens[0]), "price": _float(prices[0]),
                        "volume_24h": _float(m.get("volume24hr")) or 0.0, "end": m.get("endDate"),
                        "slug": (events[0].get("slug") if events else None) or m.get("slug"),
                        "groups": groups_for(m.get("question") or "")})
        return out

    def price_history(self, market: dict, since: float) -> list[tuple[int, float]]:
        # hourly points (fidelity 60), the same resolution the research data used (D-fix-3)
        payload = self.fetch(f"{api.CLOB}/prices-history", {"market": market["yes_token"], "startTs": int(since),
                                                            "endTs": int(self.now()), "fidelity": 60})
        points = payload.get("history", []) if isinstance(payload, dict) else []
        return [(int(p["t"]), float(p["p"])) for p in points]

    def trades(self, market: dict, since: float, min_usd: float) -> list[dict]:
        out = []
        for _, page in api.trade_pages(market["condition_id"], "CASH", min_usd, 500, 6, fetch=self.fetch):
            rows = page.get("data", [])
            for r in rows:
                token = str(r.get("asset") or r.get("token_id") or "")
                price, size = _float(r.get("price")), _float(r.get("size"))
                if price is None or size is None:
                    continue
                is_yes = token == market["yes_token"]
                buy = str(r.get("side", "")).upper() == "BUY"
                out.append({"ts": int(r.get("timestamp", 0)), "usd": price * size, "yes_dir": 1 if is_yes == buy else -1,
                            "wallet": str(r.get("proxyWallet") or r.get("proxy_wallet") or "").lower()})
            if not rows or min(int(r.get("timestamp", 0)) for r in rows) < since:
                break
        return [t for t in out if t["ts"] >= since]

    def asset_bars(self, symbols: list[str]) -> dict[str, list[tuple[int, float]]]:
        def one(symbol):
            try:
                return symbol, [(end, close) for _, end, close in yahoo.bars(yahoo.chart(symbol, "60m", "1mo", self.fetch), 3600)]
            except Exception:                         # noqa: BLE001 - one missing asset must not stop the scan
                return symbol, []
        with ThreadPoolExecutor(6) as pool:
            return dict(pool.map(one, symbols))


class ReplaySource:
    """The research dataset (``data/processed/events``) as if it were live at ``at`` (unix seconds)."""

    name = "replay"

    def __init__(self, root, at: float, dataset: str = "events"):
        folder = root / "data" / "processed" / dataset
        self.at = float(at)
        self.markets = pd.read_csv(folder / "markets.csv", dtype=DTYPES)
        prices = io.read_table(folder / "prices.pkl.gz")
        self.prices = {m: g.sort_values("ts") for m, g in prices.groupby("market_id")}
        trades = io.read_table(folder / "trades.pkl.gz")
        trades = add_yes_terms(trades)
        trades["market_id"] = trades["market_id"].astype(str)
        self.trades_by = {m: g.sort_values("ts") for m, g in trades.groupby("market_id")}
        hourly = io.read_table(folder / "assets_hourly.pkl.gz")
        self.assets = {s: g.sort_values("end_ts") for s, g in hourly.groupby("symbol")}

    def now(self) -> float:
        return self.at

    @staticmethod
    def fetch(*_args, **_kwargs):
        raise RuntimeError("replay mode has no internet: tickers resolve from the built-in ETF table only")

    def asset_history(self, symbol: str) -> list[tuple[int, float]]:
        g = self.assets.get(symbol)
        if g is None:
            return []
        g = g[g["end_ts"] <= self.at]
        return list(zip(g["end_ts"].astype(int), g["close"].astype(float)))

    def active_markets(self) -> list[dict]:
        out = []
        for m in self.markets.itertuples(index=False):
            series = self.prices.get(m.market_id)
            if series is None or not (series["ts"].iloc[0] <= self.at < m.close_ts):
                continue
            before = series[series["ts"] <= self.at]
            if before.empty:
                continue
            day = self.trades_by.get(m.market_id)
            volume = float(day[(day["ts"] > self.at - 86_400) & (day["ts"] <= self.at)]["notional"].sum()) if day is not None else 0.0
            out.append({"id": m.market_id, "question": m.question, "condition_id": m.condition_id, "yes_token": m.yes_token,
                        "price": float(before["yes_price"].iloc[-1]), "volume_24h": volume, "end": None, "slug": None,
                        "groups": groups_for(m.question)})
        return out

    def price_history(self, market: dict, since: float) -> list[tuple[int, float]]:
        s = self.prices[market["id"]]
        s = s[(s["ts"] >= since) & (s["ts"] <= self.at)]
        return list(zip(s["ts"].astype(int), s["yes_price"].astype(float)))

    def trades(self, market: dict, since: float, min_usd: float) -> list[dict]:
        t = self.trades_by.get(market["id"])
        if t is None:
            return []
        t = t[(t["ts"] >= since) & (t["ts"] <= self.at) & (t["notional"] >= min_usd)]
        return [{"ts": int(a), "usd": float(b), "yes_dir": int(c), "wallet": str(d)}
                for a, b, c, d in zip(t["ts"], t["notional"], t["yes_dir"], t["wallet"])]

    def asset_bars(self, symbols: list[str]) -> dict[str, list[tuple[int, float]]]:
        out = {}
        for s in symbols:
            g = self.assets.get(s)
            if g is None:
                out[s] = []
                continue
            g = g[(g["end_ts"] <= self.at) & (g["end_ts"] > self.at - 10 * 86_400)]
            out[s] = list(zip(g["end_ts"].astype(int), g["close"].astype(float)))
        return out
