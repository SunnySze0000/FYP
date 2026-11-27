"""Run every collector in parallel, then every research suite, then write one overview.

    python -m walletlens run-all [--quick] [--no-collect]

* Collectors run as separate processes (one per topic), each with its own log in ``logs/``.
  If one fails the others carry on; rerunning resumes from the cache.
* Topic T2 waits for topic F's market screen, so it starts its downloads a little later.
* Research suites run one after another once collection is over, on whatever data exists.
* ``results/OVERVIEW.md`` lists every topic, its gate verdicts and the decision.
* Creating a file named ``STOP`` in the project folder stops every collector within 5 seconds.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from walletlens import io, logs
from walletlens.config import Settings
from walletlens.polymarket.http import ApiError, get_json

log = logs.get("run-all")

COLLECTORS = {
    "polymarket": ["collect", "--topic", "polymarket"],
    "crypto": ["collect", "--topic", "crypto"],
    "events": ["collect", "--topic", "events"],
}
RESEARCH = [("polymarket", "universe"), ("crypto", "crypto"), ("events", "events"), ("wallets", "events"), ("daily", "events")]
CHECKS = {
    "Polymarket Gamma": ("https://gamma-api.polymarket.com/markets", {"limit": 1}),
    "Polymarket Data API": ("https://data-api.polymarket.com/v2/trades",
                            {"condition": "0x3d675f1c88099a57c12abca632cf926be1bf430125168321de06234e9930fe1a",
                             "limit": 1, "taker_only": "false"}),
    "Polymarket CLOB": ("https://clob.polymarket.com/time", None),
    "Yahoo Finance": ("https://query1.finance.yahoo.com/v8/finance/chart/SPY", {"interval": "1d", "range": "5d"}),
}


def connectivity(fetch=get_json) -> dict:
    from walletlens.polymarket.binance import fetch_bytes
    status = {}
    for name, (url, params) in CHECKS.items():
        try:
            fetch(url, params, retries=2)
            status[name] = "ok"
        except (ApiError, Exception) as error:  # noqa: BLE001 - report every failure the same way
            status[name] = f"FAILED: {error}"
    try:
        content = fetch_bytes("https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2026-01.zip")
        status["Binance data"] = "ok" if content else "FAILED: file not found"
    except Exception as error:  # noqa: BLE001
        status["Binance data"] = f"FAILED: {error}"
    return status


def _tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return lines[-1][-150:] if lines else ""
    except OSError:
        return ""


def collect_parallel(settings: Settings, profile: str | None, topics: list[str], poll_s: int = 60,
                     max_attempts: int = 4) -> dict:
    """Start one process per topic; restart a failed one (it resumes from its cache) up to max_attempts."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    state = {}

    def start(topic: str, attempt: int):
        log_path = settings.paths.logs / f"collect-{topic}-{stamp}-try{attempt}.out"
        command = [sys.executable, "-m", "walletlens"] + (["--profile", profile] if profile else []) + COLLECTORS[topic]
        handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, cwd=settings.paths.root)
        state[topic] = {"process": process, "log": log_path, "handle": handle, "attempt": attempt}
        log.info("started %s collector, attempt %d (log: %s)", topic, attempt, log_path.name)

    for topic in topics:
        start(topic, 1)
    started = time.time()
    results = {}
    stop_file = settings.paths.root / "STOP"
    while len(results) < len(topics):
        for _ in range(poll_s // 5):
            time.sleep(5)
            if stop_file.exists():
                break
        if stop_file.exists():                        # a STOP file in the project folder ends the run cleanly
            for item in state.values():
                if item["process"].poll() is None:
                    item["process"].terminate()
            stop_file.unlink()
            log.warning("STOP file found: collectors stopped; rerun to resume from the cache")
            raise SystemExit(3)
        minutes = (time.time() - started) / 60
        for topic, item in list(state.items()):
            if topic in results:
                continue
            code = item["process"].poll()
            if code is None:
                log.info("[%5.0f min] %-10s running  %s", minutes, topic, _tail(item["log"]))
                continue
            item["handle"].close()
            if code == 0:
                results[topic] = "done"
                log.info("[%5.0f min] %-10s DONE", minutes, topic)
            elif item["attempt"] < max_attempts:
                log.warning("%s collector stopped (exit %s): %s; restarting in 30 s", topic, code, _tail(item["log"]))
                time.sleep(30)
                start(topic, item["attempt"] + 1)
            else:
                results[topic] = f"failed after {max_attempts} attempts, see logs/{item['log'].name}"
                log.error("%s collector %s", topic, results[topic])
    return results


def research_all(settings: Settings, stamp: str) -> list[dict]:
    from walletlens.research.runner import run_suite
    manifests = []
    for suite, dataset in RESEARCH:
        if not (settings.paths.dataset(dataset) / "manifest.json").exists():
            log.warning("skip %s research: dataset %s not built", suite, dataset)
            manifests.append({"suite": suite, "dataset": dataset, "decision": "not run: no data", "verdicts": {}})
            continue
        try:
            manifests.append(run_suite(settings, suite, dataset, f"{stamp}_{suite}"))
        except Exception as error:  # noqa: BLE001 - one suite failing must not stop the others
            log.exception("%s research failed", suite)
            manifests.append({"suite": suite, "dataset": dataset, "decision": f"failed: {error}", "verdicts": {}})
    return manifests


def write_overview(settings: Settings, manifests: list[dict], collection: dict, checks: dict) -> Path:
    lines = ["# Overview of all topics", "", f"Generated {datetime.now():%Y-%m-%d %H:%M}.", "",
             "Order of preference (docs/00_PLAN.md): **T1 crypto → T2 events → F Polymarket-internal**.", "",
             "## Connectivity", ""]
    lines += [f"- {name}: {state}" for name, state in checks.items()]
    lines += ["", "## Collection", ""] + [f"- {topic}: {state}" for topic, state in collection.items()]
    lines += ["", "## Research", "", "| topic | run | gate verdicts | decision |", "|---|---|---|---|"]
    for manifest in manifests:
        run = manifest.get("run_id")
        link = f"[{run}]({run}/summary.md)" if run else "-"
        verdicts = ", ".join(f"{k}: {v}" for k, v in manifest.get("verdicts", {}).items()) or "-"
        lines.append(f"| {manifest['suite']} | {link} | {verdicts} | {manifest.get('decision')} |")
    path = settings.paths.results / "OVERVIEW.md"
    io.write_text(path, "\n".join(lines) + "\n")
    return path


def run_all(settings: Settings, profile: str | None, collect: bool = True) -> None:
    checks = connectivity()
    for name, state in checks.items():
        log.info("connectivity %-20s %s", name, state)
    collection = {}
    if collect:
        collection = collect_parallel(settings, profile, list(COLLECTORS))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifests = research_all(settings, stamp)
    path = write_overview(settings, manifests, collection, checks)
    log.info("overview written to %s", path)
    for manifest in manifests:
        log.info("%-10s %s", manifest["suite"], manifest.get("decision"))
