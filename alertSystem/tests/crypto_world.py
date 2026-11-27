"""Synthetic BTC spot + Polymarket hourly up/down markets, with an optional planted lead.

With ``lead > 0`` the Polymarket price (and the trades of 'skilled' wallets) already reflect
part of the next 5 minutes of spot; with ``lead = 0`` Polymarket only follows spot.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from datetime import datetime, timezone

import numpy as np

DAY = 86_400
START = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _label(ts: int) -> str:
    moment = datetime.fromtimestamp(ts - 4 * 3600, timezone.utc)     # "ET" label, cosmetic only
    hour = moment.hour % 12 or 12
    return f"Bitcoin Up or Down - {moment:%B} {moment.day}, {hour}{'AM' if moment.hour < 12 else 'PM'} ET"


def crypto_world(days: int = 45, lead: float = 0.6, seed: int = 5, markets_per_day: int = 12, skilled: int = 25,
                 noise: int = 250):
    rng = np.random.default_rng(seed)
    minutes = days * 1440 + 2 * 1440
    sigma = 0.0008
    returns = rng.normal(0, sigma, minutes)
    price = 60_000 * np.exp(np.cumsum(returns))
    grid = START + np.arange(minutes) * 60
    wallets = [f"0x{i:040x}" for i in range(skilled + noise)]
    gamma, trades = [], {}
    market_id = 5000
    for day in range(days):
        for slot in range(markets_per_day):
            start = START + day * DAY + slot * 2 * 3600
            end = start + 3600
            i0 = (start - START) // 60
            s_open, s_close = price[i0], price[i0 + 60]
            outcome = int(s_close >= s_open)
            market_id += 1
            up, down = f"{market_id}1", f"{market_id}2"
            condition = f"0x{market_id:064x}"
            from walletlens.topics.crypto.collect import slug_for
            gamma.append({"id": str(market_id), "question": _label(start), "conditionId": condition,
                          "slug": slug_for("BTC", "1h", start),
                          "outcomes": '["Up", "Down"]', "outcomePrices": json.dumps(["1", "0"] if outcome else ["0", "1"]),
                          "clobTokenIds": json.dumps([up, down]), "startDate": _iso(start - 86_400),
                          "eventStartTime": _iso(start), "endDate": _iso(end),
                          "closedTime": _iso(end + 120).replace("T", " ")[:-1] + "+00", "volumeNum": 50_000})
            records = []
            for _ in range(240):
                t = int(rng.integers(start, end - 60))
                i = (t - START) // 60
                left = (end - t) / 60
                future = math.log(price[min(i + 5, len(price) - 1)] / price[i])
                expected = math.log(price[i] / s_open) + lead * future
                p_up = 0.5 * (1 + math.erf(expected / (sigma * math.sqrt(max(left, 1)) * math.sqrt(2))))
                p_up = float(np.clip(p_up + rng.normal(0, 0.01), 0.02, 0.98))
                index = int(rng.integers(len(wallets)))
                if index < skilled and lead > 0:
                    wants_up = future > 0
                else:
                    wants_up = bool(rng.random() < p_up)
                token = up if rng.random() < 0.5 else down
                buy = wants_up == (token == up)
                records.append({"token_id": token, "proxy_wallet": wallets[index], "side": "BUY" if buy else "SELL",
                                "price": round(p_up if token == up else 1 - p_up, 4), "size": float(rng.integers(20, 400)),
                                "timestamp": t, "transaction_hash": f"0x{rng.integers(1 << 60):064x}",
                                "condition_id": condition})
            records.sort(key=lambda r: -r["timestamp"])
            trades[condition] = records
    klines = np.column_stack([grid * 1000, price, price * 1.0005, price * 0.9995, price, np.ones(minutes)])
    return {"gamma": gamma, "trades": trades, "prices": {}, "klines": klines, "wallets": wallets}


def fake_binance(world):
    """fetch_bytes replacement: monthly zips cut from the synthetic klines."""
    def fetch_bytes(url: str):
        if "/monthly/" not in url:
            return None
        year, month = url.rsplit("-1m-", 1)[1][:7].split("-")
        rows = [k for k in world["klines"]
                if datetime.fromtimestamp(k[0] / 1000, timezone.utc).strftime("%Y-%m") == f"{year}-{month}"]
        if not rows:
            return None
        text = "\n".join(",".join([str(int(r[0]))] + [f"{v:.4f}" for v in r[1:]] + ["0", "0", "0", "0", "0", "0"])
                         for r in rows)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("klines.csv", text)
        return buffer.getvalue()
    return fetch_bytes
