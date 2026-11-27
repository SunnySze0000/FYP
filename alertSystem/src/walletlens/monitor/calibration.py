"""D7 · Live calibration of the early warning: replay the last 24 hours of live data hour by hour.

For the watched live markets, fetch 3 days of prices and $250+ trades once, then compute the early-warning
flag at each of the last 24 whole hours exactly as the app does. Pre-registered expectation (docs/05, D7):
3-8% of watched market-hours flagged, as in the research data. Also reports how often a flagged hour was
followed by a 10-point jump (few jumps in one day, so this is descriptive only).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from walletlens import io, logs
from walletlens.monitor.engine import HOUR, Model, _price_at, early_warning, wallet_hours

log = logs.get("monitor.calibration")


def run(source, model: Model, out_path, hours: int = 24, max_markets: int = 60) -> dict:
    ew, watch = model.raw["early_warning"], model.raw["watch"]
    now = source.now()
    markets = [m for m in source.active_markets() if m["groups"] and m["price"] is not None and 0.03 <= m["price"] <= 0.97]
    markets = sorted(markets, key=lambda m: -m["volume_24h"])[:max_markets]

    def fetch(m):
        try:
            return m, source.price_history(m, now - 6 * 86_400), source.trades(m, now - (hours + 52) * HOUR, ew["min_trade_usd"])
        except Exception as error:                    # noqa: BLE001
            log.warning("skip %s: %s", m["question"][:50], error)
            return m, [], []
    with ThreadPoolExecutor(8) as pool:
        data = list(pool.map(fetch, markets))
    rows = []
    top = int(now // HOUR * HOUR)
    for m, history, trades in data:
        if len(history) < 3:
            continue
        first = history[0][0]
        for k in range(hours, 0, -1):
            t = top - k * HOUR
            p, prev, nxt = _price_at(history, t), _price_at(history, t - HOUR), _price_at(history, t + HOUR)
            if p is None or prev is None or not (watch["low"] <= prev <= watch["high"]) or t - HOUR - first < 24 * HOUR:
                continue
            grid = [_price_at(history, t - j * HOUR) for j in range(26, -1, -1)]
            diffs = [abs(b - a) for a, b in zip(grid[:-1], grid[1:]) if a is not None and b is not None]
            recent = sum(diffs[-25:-1]) / max(1, len(diffs[-25:-1]))
            w = early_warning(ew, abs(p - prev), recent, wallet_hours([x for x in trades if x["ts"] <= t], t, 49, ew["whale_trade_usd"]))
            rows.append({"market": m["id"], "hour": t, "flag": bool(w["flag"]), "activity": w["activity"],
                         **{f"x_{k}": v for k, v in w["features"].items()},
                         "jump_next": nxt is not None and abs(nxt - p) >= model.raw["shock_points"]})
    n, flagged = len(rows), sum(r["flag"] for r in rows)
    jumps_f = sum(r["jump_next"] for r in rows if r["flag"])
    jumps = sum(r["jump_next"] for r in rows)
    by_hour = {}
    for r in rows:
        h = by_hour.setdefault(r["hour"], [0, 0])
        h[0] += 1
        h[1] += r["flag"]
    result = {"market_hours": n, "flag_rate": flagged / n if n else None, "flagged": flagged,
              "jumps": jumps, "jumps_after_flag": jumps_f, "verdict": "pass" if n and 0.03 <= flagged / n <= 0.08 else "fail",
              "by_hour_utc": {str((h // HOUR) % 24): round(v[1] / v[0], 3) for h, v in sorted(by_hour.items())}}
    import statistics as st
    feats = [k for k in rows[0] if k.startswith("x_")] if rows else []
    result["features"] = {k[2:]: {"mean": st.fmean(r[k] for r in rows), "sd": st.pstdev([r[k] for r in rows])} for k in feats}
    result["research_features"] = dict(zip(ew["features"], zip(ew["mean"], ew["std"])))
    levels = {}
    for r in rows:
        lv = next((i for i, l in enumerate(ew.get("levels", [])) if r["activity"] <= l["upper"]), -1)
        a = levels.setdefault(str(lv), [0, 0])
        a[0] += 1
        a[1] += r["flag"]
    result["by_activity_level"] = {k: {"hours": v[0], "flag_rate": round(v[1] / v[0], 3)} for k, v in sorted(levels.items())}
    io.write_json(out_path, result)
    log.info("D7 live calibration: %s", json.dumps({k: v for k, v in result.items() if k != "by_hour_utc"}))
    return result
