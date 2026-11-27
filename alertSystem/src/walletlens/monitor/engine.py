"""The event-risk monitor: one scan turns live (or replayed) data into what the app shows.

Every number here maps to a research result (docs/05_daily_applicability.md):

* **alert**          watched market moved >= 10 points in the last hour            (V1, D1-D6)
* **typical move**   the linked asset's shock-hour vs normal-hour |return|        (V1, D3)
* **early warning**  W3 model on price + wallet activity, top 5% of scores        (W3, D1, D2)
* **pressure**       net YES dollars from $5k+ trades in the last hour            (W5, D1, D2)
* **who's trading**  the team's behaviour clusters, descriptive only              (W5 secondary)
* **watch the open** linked jumps while the US market was closed, shown before the open (S2, doc 13, V4 doc 14)
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
                       "series": [[t, c] for t, c in rows[-400:]], "info": info}
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
        history = self.source.price_history(market, now - 9 * 86_400)
        if len(history) < 3:
            return None
        first_ts = history[0][0]
        grid = hourly_grid(history, now, 192)          # 8 days: the holding drawer scrolls back a week
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


# ---------------------------------------------------------------------------- D4: watch the open
# Direct channels, fixed before V4 ran (docs/14_clean_links.md). Clean links carried the same-hour effect
# (+10.6%, overnight +15.9%); loose links showed none on their own.
CLEAN_LINKS = {"rates": {"TLT", "IEF", "SHY"}, "trade_china": {"FXI", "KWEB"}, "energy_mideast": {"USO", "XLE"},
               "war_europe": {"ITA", "EZU"}, "ai_tech": {"NVDA", "SMH"}}
OPEN_WINDOW_HOURS = 2          # after the open, keep showing what was flagged for this long (the effect is in the first hour)


def _nth_sunday(year: int, month: int, n: int) -> int:
    """Day of the month of the n-th Sunday."""
    import datetime as dt
    first = dt.date(year, month, 1)
    return 1 + (6 - first.weekday()) % 7 + 7 * (n - 1)


def us_offset(ts: float) -> int:
    """UTC offset of New York in seconds (US daylight saving: 2nd Sunday of March to 1st Sunday of November)."""
    import datetime as dt
    d = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    y = d.year
    start = dt.datetime(y, 3, _nth_sunday(y, 3, 2), 7, tzinfo=dt.timezone.utc)    # 02:00 EST
    end = dt.datetime(y, 11, _nth_sunday(y, 11, 1), 6, tzinfo=dt.timezone.utc)    # 02:00 EDT
    return -4 * HOUR if start <= d < end else -5 * HOUR


def us_session(now: float) -> dict:
    """Regular US session (09:30-16:00 New York, Mon-Fri; exchange holidays are not modelled).

    Returns the state ("closed", "opening" in the first hours after the open, "open"), the last close,
    and the next (or today's) open, all as Unix seconds."""
    import datetime as dt

    def at(day: dt.date, h: int, m: int) -> float:
        guess = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=dt.timezone.utc).timestamp()
        return guess - us_offset(guess - 5 * HOUR)

    local = dt.datetime.fromtimestamp(now + us_offset(now), dt.timezone.utc).date()
    days = [local + dt.timedelta(days=k) for k in range(-6, 8) if (local + dt.timedelta(days=k)).weekday() < 5]
    sessions = [(at(d, 9, 30), at(d, 16, 0)) for d in days]
    last_close = max(c for o, c in sessions if c <= now) if any(c <= now for _, c in sessions) else now - 24 * HOUR
    current = next(((o, c) for o, c in sessions if o <= now < c), None)
    if current:
        o, c = current
        prev_close = max(cc for _, cc in sessions if cc <= o)
        state = "opening" if now < o + OPEN_WINDOW_HOURS * HOUR else "open"
        return {"state": state, "open": o, "close": c, "since": prev_close, "until": o}
    nxt = min(o for o, _ in sessions if o > now)
    return {"state": "closed", "open": nxt, "since": last_close, "until": now}


def link_is_direct(symbol: str, how: dict) -> bool:
    """A direct channel: the bet names the holding, or the group is a clean link for it (V4)."""
    return bool(how.get("direct")) or any(symbol in CLEAN_LINKS.get(g, ()) for g in how.get("groups", []))


def watch_open(scan: dict, holdings: list[str], now: float | None = None) -> dict:
    """D4: per holding, the reliable linked jumps since the last US close (up to today's open when trading).

    Only the last 24 h of jumps are kept by the scan, so after a weekend the window is the last 24 h.
    As in the research (doc 13, doc 14), crypto bets and round-the-clock assets (e.g. BTC-USD) are left out:
    they have no open to watch."""
    now = now if now is not None else scan.get("updated_at") or time.time()
    s = us_session(now)
    lo, hi = max(s["since"], now - 24 * HOUR), s["until"]
    rows = []
    for symbol in holdings:
        if symbol.endswith("-USD"):
            continue
        jumps = []
        for m in scan.get("markets", []):
            how = (m.get("links") or {}).get(symbol)
            if not how or not how.get("reliable") or "crypto" in m.get("groups", []):
                continue
            for j in m.get("shocks_24h", []):
                if lo < j["ts"] <= hi:
                    jumps.append({"market": m["id"], "question": m["question"], "ts": j["ts"], "dp": j["dp"],
                                  "direct": link_is_direct(symbol, how)})
        if jumps:
            jumps.sort(key=lambda j: (not j["direct"], -j["ts"]))
            rows.append({"symbol": symbol, "jumps": jumps[:6], "n": len(jumps), "markets": len({j["market"] for j in jumps}),
                         "direct": any(j["direct"] for j in jumps)})
    rows.sort(key=lambda r: (not r["direct"], -r["n"]))
    return {**s, "window_from": lo, "window_to": hi, "holdings": rows,
            "evidence": {"overnight_all": 0.12, "overnight_direct": 0.16, "one_jump": 0.06, "two_plus": 0.09}}


# ---------------------------------------------------------------------------- holding drawer: live charts
def holding_live(scan: dict, symbol: str, profile: dict | None, shock_points: float = 0.10) -> dict:
    """Price series, hourly moves vs this holding's normal, and the linked signals over the same window.

    Moves are |log return| per bar divided by the holding's normal hourly |return| (its own 2-year history,
    from the profile), so 1.0 = a normal hour and ``big`` marks the top-20% size. A bar that follows a gap
    (the open after a closed market) is flagged: that is the hour D4 watches. Jumps come from each linked
    bet's hourly price grid (last 72 h), with the same 10-90% watch band as the alerts."""
    in_scan = symbol in (scan.get("assets") or {})
    a = (scan.get("assets") or {}).get(symbol) or {}
    series = a.get("series") or []
    profile = profile or {}
    info = a.get("info") or {}
    normal = profile.get("normal_abs_r") or info.get("normal_abs_r")
    big = profile.get("big_threshold") or info.get("big_threshold")
    moves = []
    for (t0, c0), (t1, c1) in zip(series[:-1], series[1:]):
        if c0 and c1:
            r = math.log(c1 / c0)
            moves.append({"ts": t1, "r": r, "x": abs(r) / normal if normal else None, "open": t1 - t0 > HOUR})
    lo = series[0][0] if series else 0
    jumps, seen = [], set()
    for m in scan.get("markets", []):
        how = (m.get("links") or {}).get(symbol)
        if not how:
            continue
        pts_ = [p for p in m.get("prices", []) if p[1] is not None]
        for (t0, p0), (t1, p1) in zip(pts_[:-1], pts_[1:]):
            if t1 - t0 > HOUR + 60 or t1 <= lo or not (0.10 <= p0 <= 0.90) or abs(p1 - p0) < shock_points:
                continue
            key = (m["id"], int(t1 // HOUR))
            if key in seen:
                continue
            seen.add(key)
            jumps.append({"ts": t1, "dp": p1 - p0, "market": m["id"], "question": m["question"],
                          "reliable": bool(how.get("reliable")), "direct": link_is_direct(symbol, how)})
    notes = [{"ts": h, "name": n["name"]} for n in (scan.get("notes") or {}).get(symbol, []) for h in n.get("hours", []) if h >= lo]
    return {"symbol": symbol, "in_scan": in_scan, "updated_at": scan.get("updated_at"), "series": series, "moves": moves,
            "normal_abs_r": normal, "big_x": (big / normal) if big and normal else None,
            "jumps": sorted(jumps, key=lambda j: j["ts"]), "notes": notes}
