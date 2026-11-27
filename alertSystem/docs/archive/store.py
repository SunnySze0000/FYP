"""Read-only access to research outputs for the app (standard library only)."""

from __future__ import annotations

import csv
import json
import math
from functools import lru_cache
from pathlib import Path

NUMERIC = {"markets", "mean_edge", "edge_sd", "pnl", "notional", "wins", "longshot_share", "last_close",
           "shrunk", "roi", "rank", "close_ts", "edge", "trades", "outcome_yes", "volume_usd",
           "top_net_yes_usd", "pit_top_net_yes_usd", "last_price"}


def _num(key: str, value: str):
    if key not in NUMERIC or value in ("", None):
        return value if value != "" else None
    try:
        number = float(value)
    except ValueError:
        return value
    if math.isnan(number):
        return None
    return int(number) if number.is_integer() and key in {"markets", "wins", "rank", "close_ts", "trades",
                                                          "outcome_yes", "last_close"} else number


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: _num(k, v) for k, v in row.items()} for row in csv.DictReader(handle)]


class ResultsStore:
    """Finds the newest complete research run and serves its app/ folder."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir

    def runs(self) -> list[dict]:
        latest = self._latest()
        out = []
        for name, run_id in latest.items():
            if name.startswith("_"):
                continue
            manifest = self.results_dir / run_id / "manifest.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                out.append({"run_id": run_id, "dataset": name, "created_at": data.get("created_at"),
                            "decision": data.get("decision"), "verdicts": data.get("verdicts", {}),
                            "markets": data.get("dataset_manifest", {}).get("markets")})
        # the collected universe is the main study; the Fed pilot is a fallback
        return sorted(out, key=lambda r: (r["dataset"] != "universe", r["created_at"] or ""), reverse=False)

    def _latest(self) -> dict:
        path = self.results_dir / "latest.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def default_run(self) -> str | None:
        runs = self.runs()
        return runs[0]["run_id"] if runs else None

    def resolve(self, run_id: str | None) -> str | None:
        valid = {r["run_id"] for r in self.runs()}
        return run_id if run_id in valid else self.default_run()

    def app_dir(self, run_id: str) -> Path:
        return self.results_dir / run_id / "app"

    @lru_cache(maxsize=8)
    def findings(self, run_id: str) -> dict:
        path = self.app_dir(run_id) / "findings.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        manifest_path = self.results_dir / run_id / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["dataset_manifest"] = manifest.get("dataset_manifest", {})
            data["created_at"] = manifest.get("created_at")
        e5 = self.results_dir / run_id / "e5" / "summary.json"
        if e5.exists():
            data["export"] = json.loads(e5.read_text(encoding="utf-8")).get("metrics", {})
        return data

    @lru_cache(maxsize=8)
    def wallets(self, run_id: str) -> tuple:
        return tuple(read_rows(self.app_dir(run_id) / "wallet_scores.csv"))

    @lru_cache(maxsize=8)
    def wallet_index(self, run_id: str) -> dict:
        return {row["wallet"]: row for row in self.wallets(run_id)}

    @lru_cache(maxsize=8)
    def recent(self, run_id: str) -> dict:
        grouped: dict[str, list] = {}
        for row in read_rows(self.app_dir(run_id) / "wallet_recent_markets.csv"):
            grouped.setdefault(row["wallet"], []).append(row)
        return grouped

    @lru_cache(maxsize=8)
    def market_index(self, run_id: str) -> tuple:
        return tuple(read_rows(self.app_dir(run_id) / "market_index.csv"))

    def market(self, run_id: str, market_id: str) -> dict | None:
        if not market_id.isdigit():
            return None
        path = self.app_dir(run_id) / "markets" / f"{market_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def figure_path(self, run_id: str, experiment: str, name: str) -> Path | None:
        if not (experiment.isalnum() and name.replace("_", "").replace(".", "").isalnum() and name.endswith(".png")):
            return None
        path = self.results_dir / run_id / experiment / "figures" / name
        return path if path.exists() else None
