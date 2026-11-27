"""The event-risk monitor: one scan turns live (or replayed) data into what the app shows.

Every number here maps to a research result (docs/05_daily_applicability.md):

* **alert**          watched market moved >= 10 points in the last hour            (V1, D1-D6)
* **typical move**   the linked asset's shock-hour vs normal-hour |return|        (V1, D3)
* **early warning**  W3 model on price + wallet activity, top 5% of scores        (W3, D1, D2)
* **pressure**       net YES dollars from $5k+ trades in the last hour            (W5, D1, D2)
* **who's trading**  the team's behaviour clusters, descriptive only              (W5 secondary)
"""

from __future__ import annotations

import csv
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from walletlens import io, logs

log = logs.get("monitor")
HOUR = 3600


@dataclass
class Model:
    raw: dict
    clusters: dict = field(default_factory=dict)

    @classmethod
    def load(cls, folder: Path) -> "Model":
        raw = io.read_json(folder / "model.json")
        clusters = {}
        path = folder / "wallet_clusters.csv"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                clusters = {row["wallet"].lower(): row["cluster_id"] for row in csv.DictReader(handle)}
        return cls(raw, clusters)

    @property
    def assets(self) -> dict:
        return {a["asset"]: a for a in self.raw["assets"]}

    def assets_for(self, groups: list[str]) -> list[str]:
        out = []
        for g in groups:
            out += [a for a in self.raw["groups"].get(g, {}).get("assets", []) if a not in out]
        return out

    def reliable(self, groups: list[str]) -> bool:
        return any(self.raw["groups"].get(g, {}).get("reliable", True) for g in groups)


def _price_at(series: list[tuple[int, float]], at: float) -> float | None:
    value = None
    for ts, p in series:
        if ts > at:
            break
        value = p
    return value


def hourly_grid(series: list[tuple[int, float]], end: float, hours: int) -> list[tuple[int, float | None]]:
    """Probability at each whole hour for the last ``hours`` hours (and at ``end`` itself, last)."""
    top = int(end // HOUR * HOUR)
    grid = [(t, _price_at(series, t)) for t in range(top - hours * HOUR, top + 1, HOUR)]
    if end > top:
        grid.append((int(end), _price_at(series, end)))
    return grid


def wallet_hours(trades: list[dict], end: float, hours: int, whale_usd: float) -> list[dict]:
    """Per one-hour window ending at end, end-1h, ...: gross, whale gross, distinct wallets, net, whale net."""
    out = []
    for k in range(hours, -1, -1):
        hi, lo = end - k * HOUR, end - (k + 1) * HOUR
        part = [t for t in trades if lo < t["ts"] <= hi]
        whales = [t for t in part if t["usd"] >= whale_usd]
        out.append({"end": int(hi), "gross": sum(t["usd"] for t in part),
                    "whale_gross": sum(t["usd"] for t in whales),
                    "wallets": len({t["wallet"] for t in part}),
                    "net": sum(t["usd"] * t["yes_dir"] for t in part),
                    "whale_net": sum(t["usd"] * t["yes_dir"] for t in whales), "trades": len(part)})
    return out


def early_warning(model: dict, abs_dp: float, recent_vol: float, hours: list[dict]) -> dict:
    """W3 score for the hour that just ended; ``hours`` is oldest-first and ends with that hour."""
    trailing, current = hours[:-1][-model["trailing_hours"]:], hours[-1]

    def rel(key):
        past = [math.log1p(abs(h[key])) for h in trailing]
        return math.log1p(abs(current[key])) - (sum(past) / len(past) if past else 0.0)

    features = {"abs_dp": abs_dp, "recent_vol": recent_vol, "gross_z": rel("gross"), "whale_z": rel("whale_gross"),
                "wallets_z": rel("wallets"),
                "imbalance": abs(current["net"]) / current["gross"] if current["gross"] else 0.0}
    x = [(features[f] - m) / s for f, m, s in zip(model["features"], model["mean"], model["std"])]
    score = model["beta"][0] + sum(b * v for b, v in zip(model["beta"][1:], x))
    chance = 1 / (1 + math.exp(-score))
    activity = sum(1 for h in trailing if h["trades"] > 0) / len(trailing) if trailing else 0.0
    level = next((lv for lv in model.get("levels", []) if activity <= lv["upper"]), None)
    threshold = level["threshold"] if level else model["threshold"]
    base = level["jump_rate"] if level else model["jump_rate_all"]
    return {"score": score, "flag": score >= threshold, "chance": chance, "activity": activity,
            "times_normal": (level["jump_rate_flagged"] if level else chance) / base if base else None,
            "jump_chance": level["jump_rate_flagged"] if level else chance, "usual_chance": base,
            "features": features,
            "driver": max(("wallets_z", "gross_z", "whale_z"),
                          key=lambda f: model["beta"][1 + model["features"].index(f)] * x[model["features"].index(f)])}


def clusters_mix(trades: list[dict], lookup: dict, names: dict) -> list[dict]:
    totals: dict[str, float] = {}
    for t in trades:
        key = lookup.get(t["wallet"], "unknown")
        totals[key] = totals.get(key, 0.0) + t["usd"]
    gross = sum(totals.values()) or 1.0
    order = sorted(totals, key=lambda k: -totals[k])
    return [{"cluster": k, "name": names.get(k, {}).get("name", "New or unclassified wallets"),
             "share": totals[k] / gross, "usd": totals[k]} for k in order]


def asset_moves(bars: dict, model: Model) -> dict:
    out = {}
    for symbol, rows in bars.items():
        info = model.assets.get(symbol, {})
        if len(rows) < 2:
            out[symbol] = {"symbol": symbol, "last": None, "info": info}
            continue
        (t0, c0), (t1, c1) = rows[-2], rows[-1]
        r = math.log(c1 / c0) if c0 else 0.0
        normal = info.get("normal_abs_r")
        out[symbol] = {"symbol": symbol, "last": c1, "last_ts": t1, "r_last_hour": r if t1 - t0 <= HOUR else None,
                       "times_normal": abs(r) / normal if normal and t1 - t0 <= HOUR else None,
                       "series": [[t, c] for t, c in rows[-72:]], "info": info}
    return out


class Monitor:
    def __init__(self, source, model: Model, max_markets: int = 80, workers: int = 8):
        self.source, self.model, self.max_markets, self.workers = source, model, max_markets, workers
        self.profiles: dict[str, dict] = {}

    def link(self, market: dict) -> tuple[list[str], bool, dict]:
        """Holdings this market is linked to (layer 1 or checked layer 2), whether any link is reliable, and how."""
        from walletlens.monitor.holdings import active_groups, mentions
        linked, reliable, how = [], False, {}
        for symbol, profile in self.profiles.items():
            if not profile.get("supported"):
                continue
            groups = active_groups(profile)
            hit = [g for g in market["groups"] if g in groups]
            direct = bool(profile.get("terms")) and mentions(market["question"], profile["terms"])
            if hit or direct:
                linked.append(symbol)
                ok = direct or any(groups[g] for g in hit)
                reliable = reliable or ok
                how[symbol] = {"direct": direct, "groups": hit, "reliable": ok}
        return linked, reliable, how

    def _analyse(self, market: dict, now: float) -> dict | None:
        cfg = self.model.raw
        ew_model = cfg["early_warning"]
        history = self.source.price_history(market, now - 8 * 86_400)
        if len(history) < 3:
            return None
        first_ts = history[0][0]
        grid = hourly_grid(history, now, 72)
        trades = self.source.trades(market, now - 74 * HOUR, ew_model["min_trade_usd"])
        for t in trades:
            t["market"] = market["id"]
        top = int(now // HOUR * HOUR)
        # live alert: current price (market list) against the price an hour ago
        p_now = market["price"] if market.get("price") is not None else _price_at(history, now)
        p_hour_ago = _price_at(history, now - HOUR)
        if p_now is None or p_hour_ago is None:
            return None
        watch = cfg["watch"]
        watched = watch["low"] <= p_hour_ago <= watch["high"] and now - HOUR - first_ts >= watch["min_age_hours"] * HOUR
        dp = p_now - p_hour_ago
        # early warning: computed on whole hours from hourly prices, exactly as in the research (D-fix-3)
        p_top, p_prev = _price_at(history, top), _price_at(history, top - HOUR)
        hourly = [_price_at(history, top - j * HOUR) for j in range(26, -1, -1)]
        diffs = [abs(b - a) for a, b in zip(hourly[:-1], hourly[1:]) if a is not None and b is not None]
        recent_vol = sum(diffs[-25:-1]) / max(1, len(diffs[-25:-1]))
        hours = wallet_hours(trades, top, 49, ew_model["whale_trade_usd"])
        warn_watched = p_prev is not None and watch["low"] <= p_prev <= watch["high"] and top - HOUR - first_ts >= watch["min_age_hours"] * HOUR
        warning = early_warning(ew_model, abs((p_top or 0) - (p_prev or 0)), recent_vol, hours)
        warning["flag"] = bool(warning["flag"] and warn_watched)
        warning["hour"] = top
        warning_hours = []                      # backfill: the warning at each of the last 24 whole hours
        for k in range(24, 0, -1):
            t0 = top - k * HOUR
            a, b = _price_at(history, t0), _price_at(history, t0 - HOUR)
            if a is None or b is None or not (watch["low"] <= b <= watch["high"]) or t0 - HOUR - first_ts < watch["min_age_hours"] * HOUR:
                continue
            hh = [_price_at(history, t0 - j * HOUR) for j in range(26, -1, -1)]
            dd = [abs(y - x) for x, y in zip(hh[:-1], hh[1:]) if x is not None and y is not None]
            rv = sum(dd[-25:-1]) / max(1, len(dd[-25:-1]))
            w = early_warning(ew_model, abs(a - b), rv, wallet_hours([x for x in trades if x["ts"] <= t0], t0, 49, ew_model["whale_trade_usd"]))
            warning_hours.append({"hour": t0, "score": w["score"], "activity": w["activity"], "flag": bool(w["flag"])})
        live_hours = wallet_hours(trades, now, 49, ew_model["whale_trade_usd"])
        last = live_hours[-1]
        pressure = last["whale_net"] if watched and abs(last["whale_net"]) >= cfg["pressure"]["min_flow_usd"] else 0.0
        day = [t for t in trades if t["ts"] > now - 86_400]
        past_shocks = []
        for (t0, a), (t1, b) in zip(grid[:-1], grid[1:]):
            if a is not None and b is not None and watch["low"] <= a <= watch["high"] and abs(b - a) >= cfg["shock_points"] \
                    and t1 > now - 86_400 and t0 - first_ts >= watch["min_age_hours"] * HOUR:
                past_shocks.append({"ts": t1, "dp": b - a})
        assets, reliable, how = self.link(market)
        return {
            "id": market["id"], "question": market["question"], "slug": market.get("slug"), "groups": market["groups"],
            "assets": assets, "reliable": reliable, "links": how, "price": p_now, "dp_1h": dp,
            "warning_hours": warning_hours, "_trades": trades,
            "watched": watched, "alert": watched and abs(dp) >= cfg["shock_points"],
            "shocks_24h": past_shocks, "warning": warning, "pressure_usd": pressure,
            "whale_net_24h": sum(t["usd"] * t["yes_dir"] for t in day if t["usd"] >= ew_model["whale_trade_usd"]),
            "volume_24h": market.get("volume_24h", 0.0), "trades_24h": len(day),
            "wallets_24h": len({t["wallet"] for t in day}),
            "mix": clusters_mix(day, self.model.clusters, cfg["clusters"]),
            "prices": [[t, p] for t, p in grid if p is not None] + [[int(now), p_now]], "wallet_hours": live_hours[-48:],
        }

    def scan(self, profiles: dict[str, dict]) -> dict:
        started = time.time()
        now = self.source.now()
        errors = []
        self.profiles = profiles
        holdings = list(profiles)
        try:
            markets = [m for m in self.source.active_markets() if m["price"] is not None and 0.03 <= m["price"] <= 0.97]
        except Exception as error:                      # noqa: BLE001
            log.error("market list failed: %s", error)
            return {"ok": False, "error": f"Could not load the market list: {error}", "updated_at": now}
        ranked = []
        for m in markets:
            linked, _, _ = self.link(m)
            if m["groups"] or linked:
                ranked.append((0 if linked else 1, -m["volume_24h"], m))
        ranked.sort(key=lambda x: (x[0], x[1]))
        markets = [m for _, _, m in ranked[: self.max_markets]]

        def safe(m):
            try:
                return self._analyse(m, now)
            except Exception as error:                  # noqa: BLE001
                errors.append(f"{m['question'][:60]}: {error}")
                return None
        with ThreadPoolExecutor(self.workers) as pool:
            rows = [r for r in pool.map(safe, markets) if r]
        symbols = sorted(holdings)
        bars = self.source.asset_bars(symbols) if symbols else {}
        assets = asset_moves(bars, self.model)
        notes = self._notes(rows, profiles, now)
        for r in rows:
            r.pop("_trades", None)
        log.info("scan: %d markets analysed, %d alerts, %d warnings, %.1fs", len(rows),
                 sum(r["alert"] for r in rows), sum(r["warning"]["flag"] for r in rows), time.time() - started)
        return {"ok": True, "source": self.source.name, "updated_at": now, "seconds": round(time.time() - started, 1),
                "markets": rows, "assets": assets, "notes": notes, "errors": errors[:10]}

    def _notes(self, rows: list[dict], profiles: dict, now: float) -> dict:
        """D2/D3: per holding, which passing wallet signals fired now and in the last 24 hours."""
        from walletlens.monitor.holding_wallets import live_flags
        out = {}
        for symbol, profile in profiles.items():
            checks = ((profile.get("wallet_checks") or {}).get("signals") or {})
            passing = {k: v for k, v in checks.items() if v.get("pass")}
            if not passing:
                continue
            trades = [t for r in rows if symbol in r["assets"] and r["links"][symbol]["reliable"] for t in r["_trades"]]
            fired = live_flags(trades, self.model.clusters, now)
            out[symbol] = [{"signal": k, "name": v["name"], "shown_effect": v["shown_effect"], "hours": fired.get(k, []),
                            "active": bool(fired.get(k)) and fired[k][-1] >= now - 3600} for k, v in passing.items()]
        return out


def digest(scan: dict, holdings: list[str], model: Model, profiles: dict | None = None) -> list[dict]:
    """Per holding: what happened in its linked event markets over the last 24 hours (D5 daily digest)."""
    out = []
    for symbol in holdings:
        linked = [m for m in scan.get("markets", []) if symbol in m["assets"]]
        shocks = sorted(({"market": m["id"], "question": m["question"], "ts": s["ts"], "dp": s["dp"],
                          "reliable": m["links"][symbol]["reliable"]} for m in linked for s in m["shocks_24h"]), key=lambda s: -s["ts"])
        reliable_shocks = [s for s in shocks if s["reliable"]]
        warnings = [m["id"] for m in linked if m["warning"]["flag"] and m["links"][symbol]["reliable"]]   # empty in shadow mode
        alerts_now = [m["id"] for m in linked if m["alert"] and m["links"][symbol]["reliable"]]
        from walletlens.monitor.holdings import jump_ratio
        profile = (profiles or {}).get(symbol, {})
        info = dict(model.assets.get(symbol, {}))
        ratio = jump_ratio(profile)
        if ratio:
            info["jump_ratio"] = ratio
        elif info.get("normal_abs_r"):
            info["jump_ratio"] = info["shock_abs_r"] / info["normal_abs_r"]
        notes = scan.get("notes", {}).get(symbol, [])
        level = "high" if alerts_now else "elevated" if (reliable_shocks or warnings) else "calm"
        out.append({"symbol": symbol, "level": level, "linked_markets": len(linked), "shocks": shocks[:12],
                    "alerts_now": alerts_now, "warnings": warnings, "info": info, "notes": notes,
                    "profile": {k: profile.get(k) for k in ("supported", "reason", "links", "candidate_reason", "status", "info")},
                    "move": scan.get("assets", {}).get(symbol)})
    return out
