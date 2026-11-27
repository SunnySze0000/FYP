"""D4 · Live feasibility: can the event-risk monitor get what it needs, live and fast enough?

Pre-registered in docs/05_daily_applicability.md. Pass rule: all four sources reachable; median age of the
latest trade across the 50 most-traded watched markets <= 60 min; BTC-USD latest bar <= 90 min old; one
full refresh (market list + 50 markets' prices and trades + 6 assets) <= 120 s.

Run on a machine with internet: ``python -m walletlens live-check`` (or double-click livecheck.bat).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from statistics import median

from walletlens import io, logs
from walletlens.config import Settings
from walletlens.polymarket import api, yahoo
from walletlens.polymarket.http import get_json
from walletlens.topics.events.collect import groups_for

log = logs.get("events.live_check")
PORTFOLIO = ("SPY", "QQQ", "TLT", "GLD", "USO", "BTC-USD")
WATCH_LOW, WATCH_HIGH = 0.10, 0.90


def _yes_price(market: dict) -> float | None:
    prices = api.as_list(market.get("outcomePrices"))
    try:
        return float(prices[0])
    except (IndexError, TypeError, ValueError):
        return None


def watched_markets(n: int = 50, pages: int = 5) -> tuple[list[dict], int]:
    seen = []
    for page in range(pages):
        seen += api.gamma_active_markets(limit=100, offset=page * 100) or []
    watched = []
    for market in seen:
        price = _yes_price(market)
        groups = groups_for(market.get("question") or "")
        if groups and price is not None and WATCH_LOW <= price <= WATCH_HIGH and market.get("conditionId"):
            watched.append({**market, "_groups": groups, "_price": price})
    watched.sort(key=lambda m: float(m.get("volume24hr") or 0), reverse=True)
    return watched[:n], len(seen)


def _market_probe(market: dict, now: float) -> dict:
    out = {"id": market.get("id"), "question": market.get("question"), "groups": market["_groups"]}
    try:
        trades = api.recent_trades(market["conditionId"], limit=100)
        stamps = [int(t.get("timestamp") or 0) for t in trades if t.get("timestamp")]
        out["latest_trade_age_min"] = (now - max(stamps)) / 60 if stamps else None
        out["trades_last_hour"] = sum(1 for s in stamps if now - s <= 3600)
    except Exception as error:                     # noqa: BLE001 - report, do not crash the probe
        out["trade_error"] = str(error)[:200]
    try:
        token = api.as_list(market.get("clobTokenIds"))[0]
        mid = get_json(f"{api.CLOB}/midpoint", {"token_id": token})
        out["midpoint"] = float(mid.get("mid")) if isinstance(mid, dict) and mid.get("mid") else None
    except Exception as error:                     # noqa: BLE001
        out["price_error"] = str(error)[:200]
    return out


def _asset_probe(symbol: str, now: float) -> dict:
    try:
        rows = yahoo.bars(yahoo.chart(symbol, "1m", "1d"), 60)
        return {"symbol": symbol, "latest_bar_age_min": (now - rows[-1][1]) / 60 if rows else None, "bars": len(rows)}
    except Exception as error:                     # noqa: BLE001
        return {"symbol": symbol, "error": str(error)[:200]}


def run(settings: Settings, run_id: str) -> dict:
    started = time.time()
    reachable = {}
    try:
        markets, scanned = watched_markets()
        reachable["gamma"] = True
    except Exception as error:                     # noqa: BLE001
        log.error("gamma failed: %s", error)
        markets, scanned, reachable["gamma"] = [], 0, False
    now = time.time()
    with ThreadPoolExecutor(8) as pool:
        probes = list(pool.map(lambda m: _market_probe(m, now), markets))
        assets = list(pool.map(lambda s: _asset_probe(s, now), PORTFOLIO))
    elapsed = time.time() - started
    ages = [p["latest_trade_age_min"] for p in probes if p.get("latest_trade_age_min") is not None]
    reachable["data_api"] = bool(ages)
    reachable["clob"] = any(p.get("midpoint") is not None for p in probes)
    reachable["yahoo"] = any(a.get("latest_bar_age_min") is not None for a in assets)
    btc = next((a.get("latest_bar_age_min") for a in assets if a["symbol"] == "BTC-USD"), None)
    checks = {
        "all_sources_reachable": all(reachable.values()),
        "median_trade_age_ok": bool(ages) and median(ages) <= 60,
        "btc_bar_fresh": btc is not None and btc <= 90,
        "refresh_fast": elapsed <= 120,
    }
    verdict = "pass" if all(checks.values()) else "fail"
    result = {
        "id": "d4", "verdict": verdict, "run_at": datetime.now(timezone.utc).isoformat(),
        "reachable": reachable, "checks": checks, "refresh_seconds": round(elapsed, 1),
        "markets_scanned": scanned, "watched_markets": len(markets),
        "median_trade_age_min": median(ages) if ages else None,
        "markets_with_trade_last_hour": sum(1 for p in probes if p.get("trades_last_hour")),
        "btc_bar_age_min": btc, "assets": assets, "markets": probes,
    }
    folder = settings.paths.results / run_id
    io.write_json(folder / "d4_live_check.json", result)
    lines = [f"# D4 · Live feasibility — {verdict.upper()}", "",
             f"Run {result['run_at']}. Refresh took {elapsed:.1f} s for {len(markets)} watched markets "
             f"(of {scanned} active markets scanned) and {len(PORTFOLIO)} assets.", "",
             "| check | result |", "|---|---|"] + [f"| {k} | {'pass' if v else 'FAIL'} |" for k, v in checks.items()] + [
             "", f"- Sources reachable: {reachable}",
             f"- Median age of the latest trade: {result['median_trade_age_min']} min",
             f"- Markets with a trade in the last hour: {result['markets_with_trade_last_hour']} of {len(probes)}",
             f"- Asset bar ages (min): " + ", ".join(f"{a['symbol']} {a.get('latest_bar_age_min', 'err') if a.get('latest_bar_age_min') is None else round(a['latest_bar_age_min'], 1)}" for a in assets),
             "", "Stock bars are stale outside US trading hours; only BTC-USD freshness is part of the pass rule."]
    io.write_text(folder / "summary.md", "\n".join(lines))
    log.info("D4 live check: %s | %s | refresh %.1fs, median trade age %s min", verdict, checks, elapsed,
             result["median_trade_age_min"])
    return result
