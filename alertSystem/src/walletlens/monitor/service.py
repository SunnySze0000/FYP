"""Glue for the app: portfolio and holding profiles, background scanning, logs, evidence."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pandas as pd

from walletlens import io, logs
from walletlens.monitor import APP_VERSION
from walletlens.monitor.engine import Model, Monitor, digest, holding_live, watch_open
from walletlens.monitor.holding_wallets import ResearchStore, check as wallet_check
from walletlens.monitor.holdings import build_profile, hourly_history
from walletlens.monitor.journal import Journal, NotesLog

log = logs.get("monitor.service")
DEFAULT_HOLDINGS = ["SPY", "QQQ", "TLT", "GLD", "USO", "BTC-USD"]
MAX_HOLDINGS = 15


class Service:
    def __init__(self, root: Path, source, refresh_seconds: int = 300, results_run: str | None = None):
        self.root, self.source, self.refresh = root, source, refresh_seconds
        self.app_dir = root / "data" / "app"
        self.profile_dir = self.app_dir / "holdings"
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.model = Model.load(self.app_dir)
        self.monitor = Monitor(source, self.model)
        suffix = "" if source.name == "live" else "_replay"
        self.journal = Journal(self.app_dir / f"journal{suffix}.jsonl")
        self.notes_log = NotesLog(self.app_dir / f"notes{suffix}.jsonl")
        self.shadow_path = self.app_dir / f"warnings_shadow{suffix}.jsonl"
        self.results_run = results_run
        self.scan, self._lock, self._busy = {"ok": False, "pending": True}, threading.Lock(), threading.Lock()
        self.early_warning_live = False                # D7 failed on live data: shadow mode (docs/05)
        self.store = ResearchStore(root)
        jumps = self.app_dir / "group_jumps.csv"
        self.jumps = pd.read_csv(jumps) if jumps.exists() else pd.DataFrame(columns=["ts", "group", "market_id"])
        self.checking: set[str] = set()

    # ------------------------------------------------------------------ holdings
    @property
    def portfolio_path(self) -> Path:
        return self.app_dir / "portfolio.json"

    def holdings(self) -> list[str]:
        if self.portfolio_path.exists():
            return json.loads(self.portfolio_path.read_text(encoding="utf-8")).get("holdings", DEFAULT_HOLDINGS)
        return list(DEFAULT_HOLDINGS)

    def profile(self, symbol: str) -> dict | None:
        path = self.profile_dir / f"{symbol.replace('^', '_')}.json"
        return io.read_json(path) if path.exists() else None

    def profiles(self) -> dict[str, dict]:
        return {s: p for s in self.holdings() if (p := self.profile(s))}

    def set_holdings(self, holdings: list[str]) -> list[str]:
        clean = [h for h in dict.fromkeys(str(h).strip().upper() for h in holdings) if h and len(h) <= 12][:MAX_HOLDINGS]
        if not clean:
            raise ValueError("Add at least one ticker")
        io.write_json(self.portfolio_path, {"holdings": clean})
        threading.Thread(target=self.ensure_profiles, daemon=True).start()
        return clean

    def ensure_profiles(self, force: bool = False) -> None:
        """Build the profile of every holding that has none (or an older version): layers 1-3, then D2/D3 checks."""
        for symbol in self.holdings():
            existing = self.profile(symbol)
            failed = str(((existing or {}).get("wallet_checks") or {}).get("note", "")).startswith("check failed")
            if existing and existing.get("version") == APP_VERSION and not force and not failed:
                continue
            if symbol in self.checking:
                continue
            self.checking.add(symbol)
            try:
                bars = None
                if self.source.name != "live":
                    bars = self.source.asset_history(symbol)
                else:
                    try:
                        bars = hourly_history(symbol)
                    except Exception as error:      # noqa: BLE001
                        log.warning("no history for %s: %s", symbol, error)
                        bars = []
                profile = build_profile(symbol, self.jumps, history=bars) if self.source.name == "live" else \
                    build_profile(symbol, self.jumps, fetch=self.source.fetch, history=bars)
                if profile.get("supported"):
                    try:
                        profile["wallet_checks"] = wallet_check(profile, bars or [], self.store)
                    except Exception as error:      # noqa: BLE001
                        log.error("wallet check %s failed: %s", symbol, error)
                        profile["wallet_checks"] = {"note": f"check failed: {error}", "signals": {}}
                io.write_json(self.profile_dir / f"{symbol.replace('^', '_')}.json", profile)
                log.info("profile %s: links %s, wallet signals %s", symbol, profile.get("links"),
                         {k: v["pass"] for k, v in (profile.get("wallet_checks") or {}).get("signals", {}).items()})
            finally:
                self.checking.discard(symbol)
        threading.Thread(target=self.run_scan, daemon=True).start()

    # ------------------------------------------------------------------ scanning
    def run_scan(self) -> dict:
        if not self._busy.acquire(blocking=False):
            return self.scan
        try:
            profiles = self.profiles()
            result = self.monitor.scan(profiles)
            if result.get("ok"):
                self._shadow(result)
                if not self.early_warning_live:
                    for m in result["markets"]:
                        m["warning"]["shadow_flag"], m["warning"]["flag"] = m["warning"]["flag"], False
                added = self.journal.record(result)
                self.notes_log.record_notes(result)
                bars = {s: [(t, c) for t, c in a.get("series", [])] for s, a in result["assets"].items()}
                thresholds = {s: {"big": p.get("big_threshold"), "normal": p.get("normal_abs_r")} for s, p in profiles.items()}
                self.journal.score(bars, {s: {"big_threshold": t["big"]} for s, t in thresholds.items()}, result["updated_at"])
                self.notes_log.score_notes(bars, thresholds, result["updated_at"])
                if added:
                    log.info("journal: %d new alerts (incl. backfill)", added)
            with self._lock:
                self.scan = result
            return result
        finally:
            self._busy.release()

    def _shadow(self, scan: dict) -> None:
        """Log one early-warning score per watched market and hour (incl. the last 24 h as backfill)."""
        seen = set()
        if self.shadow_path.exists():
            with self.shadow_path.open(encoding="utf-8") as handle:
                seen = {(r["market"], r["hour"]) for r in map(json.loads, handle) if r}
        rows = []
        for m in scan["markets"]:
            hours = list(m.get("warning_hours", []))
            if m["watched"]:
                hours.append({"hour": m["warning"]["hour"], "score": m["warning"]["score"],
                              "activity": m["warning"]["activity"], "flag": bool(m["warning"]["flag"])})
            for h in hours:
                if (m["id"], h["hour"]) in seen:
                    continue
                seen.add((m["id"], h["hour"]))
                rows.append({"market": m["id"], **h, "version": APP_VERSION})
        if rows:
            with self.shadow_path.open("a", encoding="utf-8") as handle:
                handle.writelines(json.dumps(r) + "\n" for r in rows)

    def start(self) -> None:
        def loop():
            self.ensure_profiles()
            while True:
                try:
                    self.run_scan()
                except Exception as error:          # noqa: BLE001 - keep scanning
                    log.error("scan failed: %s", error)
                if self.source.name != "live":
                    return
                time.sleep(self.refresh)
        threading.Thread(target=loop, daemon=True).start()

    # ------------------------------------------------------------------ views
    def state(self) -> dict:
        with self._lock:
            scan = self.scan
        holdings, profiles = self.holdings(), self.profiles()
        light = [{k: v for k, v in m.items() if k not in ("wallet_hours", "warning_hours")} for m in scan.get("markets", [])]
        board = digest(scan, holdings, self.model, profiles) if scan.get("ok") else []
        for row in board:
            if row["symbol"] in self.checking or row["symbol"] not in profiles:
                row["profile"]["status"] = "checking"
        names = {h: ((profiles.get(h) or {}).get("info") or {}).get("name") or h for h in holdings}
        return {"holdings": holdings, "names": names, "checking": sorted(self.checking), "version": APP_VERSION,
                "scan": {**scan, "markets": light}, "digest": board, "refresh_seconds": self.refresh,
                "watch_open": watch_open(scan, holdings) if scan.get("ok") else None,
                "early_warning_live": self.early_warning_live, "model": {
                    "shock_points": self.model.raw["shock_points"], "pressure": self.model.raw["pressure"],
                    "clusters": self.model.raw["clusters"],
                    "groups": {g: {"reliable": v["reliable"], "effect": v["effect"]} for g, v in self.model.raw["groups"].items()}}}

    def holding(self, symbol: str) -> dict:
        p = self.profile(symbol.upper())
        if not p:
            raise LookupError("No profile yet: the history check may still be running")
        with self._lock:
            scan = self.scan
        live = holding_live(scan, p["symbol"], p, self.model.raw["shock_points"]) if scan.get("ok") else None
        return {**p, "live": live}

    def market(self, market_id: str) -> dict:
        with self._lock:
            scan = self.scan
        for m in scan.get("markets", []):
            if m["id"] == market_id:
                profiles = self.profiles()
                info = {a: {**self.model.assets.get(a, {}), "history": (profiles.get(a) or {}).get("history"),
                            "links": (profiles.get(a) or {}).get("links")} for a in m["assets"]}
                return {**m, "asset_info": info,
                        "asset_moves": {a: scan["assets"].get(a) for a in m["assets"] if a in scan.get("assets", {})}}
        raise LookupError("Market not in the latest scan")

    def track(self) -> dict:
        return {**self.journal.summary(), "notes": self.notes_log.summary()}

    def evidence(self) -> dict:
        tests = []
        folder = self.root / "results" / self.results_run if self.results_run else None
        if folder and folder.exists():
            for item in ("d1", "d2", "d3", "d4", "d5", "d6"):
                path = folder / item / "summary.json"
                if path.exists():
                    data = io.read_json(path)
                    tests.append({"id": item, "title": data.get("title"), "verdict": data.get("verdict"),
                                  "headline": data.get("headline"), "question": data.get("question")})
        d7 = sorted((self.root / "results").glob("*_live_calibration/d7_live_calibration.json"))
        d7 = {k: v for k, v in io.read_json(d7[-1]).items() if k in ("verdict", "flag_rate", "market_hours", "jumps", "jumps_after_flag")} if d7 else None
        return {"run": self.results_run, "tests": tests, "d7": d7, "version": APP_VERSION,
                "early_warning_check": self.model.raw["early_warning"]["check"]}
