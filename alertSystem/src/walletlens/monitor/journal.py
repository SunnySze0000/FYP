"""Forward track record: every alert the monitor raises is logged once, then scored against what the
linked asset actually did in that hour (did it make a top-20% move?). This is how the app keeps testing
itself on new data (docs/05, limitation 1)."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path

from walletlens.monitor import APP_VERSION

HOUR = 3600


class Journal:
    def __init__(self, path: Path):
        self.path, self._lock = path, threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def _write(self, rows: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, scan: dict) -> int:
        """Log new alerts once per market and hour: the jump happening now and, as backfill, every watched jump of
        the last 24 hours (so hours missed while the app was off are filled in). Returns how many were added."""
        if not scan.get("ok"):
            return 0
        with self._lock:
            rows = self.entries()
            seen = {}
            for r in rows:
                seen.setdefault(r["market"], []).append(r["hour"])
            added = 0
            for m in scan["markets"]:
                events = [(int(s["ts"]), s["dp"], False) for s in m.get("shocks_24h", [])]
                if m["alert"]:
                    events.append((int(scan["updated_at"] // HOUR * HOUR), m["dp_1h"], True))
                for hour, dp, live in events:
                    if any(abs(hour - h) <= HOUR for h in seen.get(m["id"], [])):
                        continue
                    rows.append({"market": m["id"], "question": m["question"], "hour": hour,
                                 "ts": scan["updated_at"] if live else hour, "dp": dp, "assets": m["assets"],
                                 "reliable": m["reliable"], "backfilled": not live, "warning_before": m["warning"].get("shadow_flag", m["warning"]["flag"]) if live else None,
                                 "pressure_usd": m["pressure_usd"] if live else None, "source": scan["source"],
                                 "version": APP_VERSION, "scores": {}})
                    seen.setdefault(m["id"], []).append(hour)
                    added += 1
            if added:
                self._write(rows)
            return added

    def score(self, bars: dict, model_assets: dict, now: float) -> int:
        """Score alerts older than 2 hours against the asset bar that ended in the alert hour."""
        with self._lock:
            rows, changed = self.entries(), 0
            for r in rows:
                if now - r["ts"] < 2 * HOUR:
                    continue
                for asset in r["assets"]:
                    if asset in r["scores"] or asset not in bars or not (model_assets.get(asset) or {}).get("big_threshold"):
                        continue
                    series = bars[asset]
                    # the asset bar whose end is nearest the alert (within 1 h) covers the hour that jumped
                    near = [i for i, (t, _) in enumerate(series) if abs(t - r["ts"]) <= HOUR and i > 0]
                    if not near:
                        if series and series[-1][0] > r["ts"] + 6 * HOUR:
                            r["scores"][asset] = {"status": "market closed"}
                            changed += 1
                        continue
                    i = min(near, key=lambda k: abs(series[k][0] - r["ts"]))
                    if series[i][0] - series[i - 1][0] > HOUR:
                        r["scores"][asset] = {"status": "market closed"}
                        changed += 1
                        continue
                    after, before = [series[i]], [series[i - 1]]
                    move = math.log(after[0][1] / before[-1][1])
                    r["scores"][asset] = {"status": "scored", "move": move,
                                          "big": abs(move) >= model_assets[asset]["big_threshold"]}
                    changed += 1
            if changed:
                self._write(rows)
            return changed

    def summary(self) -> dict:
        rows = self.entries()
        scored = [s for r in rows if r.get("reliable") for s in r["scores"].values() if s.get("status") == "scored"]
        big = sum(1 for s in scored if s["big"])
        return {"alerts": len(rows), "scored_pairs": len(scored), "big_moves": big,
                "big_rate": big / len(scored) if scored else None, "research_rate": 0.25, "unrelated_rate": 0.18,
                "recent": sorted(rows, key=lambda r: -r["ts"])[:50]}


class NotesLog(Journal):
    """D2/D3 wallet notes, one row per holding, signal and hour; scored against the holding's next-hour move."""

    def record_notes(self, scan: dict) -> int:
        if not scan.get("ok"):
            return 0
        with self._lock:
            rows = self.entries()
            seen = {(r["symbol"], r["signal"], r["hour"]) for r in rows}
            added = 0
            for symbol, notes in (scan.get("notes") or {}).items():
                for note in notes:
                    for hour in note["hours"]:
                        key = (symbol, note["signal"], int(hour))
                        if key in seen:
                            continue
                        rows.append({"symbol": symbol, "signal": note["signal"], "hour": int(hour), "version": APP_VERSION,
                                     "source": scan["source"], "shown_effect": note["shown_effect"], "score": None})
                        seen.add(key)
                        added += 1
            if added:
                self._write(rows)
            return added

    def score_notes(self, bars: dict, thresholds: dict, now: float) -> int:
        with self._lock:
            rows, changed = self.entries(), 0
            for r in rows:
                if r["score"] is not None or now - r["hour"] < 2 * HOUR or r["symbol"] not in bars:
                    continue
                series = bars[r["symbol"]]
                nxt = [i for i, (t, _) in enumerate(series) if r["hour"] < t <= r["hour"] + 2 * HOUR and i > 0]
                if not nxt:
                    if series and series[-1][0] > r["hour"] + 6 * HOUR:
                        r["score"] = {"status": "market closed"}
                        changed += 1
                    continue
                i = nxt[0]
                if series[i][0] - series[i - 1][0] > HOUR:
                    r["score"] = {"status": "market closed"}
                else:
                    move = math.log(series[i][1] / series[i - 1][1])
                    th = (thresholds.get(r["symbol"]) or {})
                    r["score"] = {"status": "scored", "move": move,
                                  "big": bool(th.get("big") and abs(move) >= th["big"]),
                                  "vs_normal": abs(move) / th["normal"] if th.get("normal") else None}
                changed += 1
            if changed:
                self._write(rows)
            return changed

    def summary(self) -> dict:
        rows = self.entries()
        scored = [r for r in rows if r.get("score") and r["score"].get("status") == "scored"]
        ratios = [r["score"]["vs_normal"] for r in scored if r["score"].get("vs_normal") is not None]
        return {"notes": len(rows), "scored": len(scored),
                "mean_vs_normal": sum(ratios) / len(ratios) if ratios else None,
                "recent": sorted(rows, key=lambda r: -r["hour"])[:50]}
