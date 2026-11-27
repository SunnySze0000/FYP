"""Run a topic's experiment suite, write every result, and record the decision it implies.

A suite is: a name, a context factory (loads the data once), an ordered list of experiment
modules (each exposes ``run(ctx) -> ExperimentResult``) and a pre-registered decision rule.

Suites:  polymarket (topic F) · crypto (topic T1) · events (topic T2)
"""

from __future__ import annotations

import platform
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from typing import Callable

import numpy as np
import pandas as pd

from walletlens import __version__, io, logs
from walletlens.config import Settings
from walletlens.research import plots

log = logs.get("research")


@dataclass
class Suite:
    name: str
    title: str
    package: str
    experiments: tuple
    context: Callable
    decide: Callable
    default_dataset: str
    export_id: str | None = None


# --------------------------------------------------------------------------- topic F decision
F_DECISIONS = [
    (("pass", "pass", "pass"), "Smart-money signal: alerts when skilled wallets trade, with expected edge."),
    (("pass", "pass", None), "Smart-money radar as evidence: who is on each side and their record, plus fair value; no copy button."),
    (("pass", None, None), "Wallet track-record explorer plus fair value."),
    ((None, None, None), "Pivot: fair-value / mispricing helper; refine the topic."),
]


def decide_polymarket(verdicts: dict) -> str:
    h1, h2, h3 = verdicts.get("e2"), verdicts.get("e3"), verdicts.get("e4")
    if None in (h1, h2, h3):
        return "Partial run: E2-E4 were not all run, so no decision."
    if "inconclusive" in (h1, h2, h3) and h1 != "fail":
        return ("Inconclusive: not enough independent events for at least one test. "
                "Collect the wider universe before deciding.")
    for (r1, r2, r3), product in F_DECISIONS:
        if (r1 is None or h1 == r1) and (r2 is None or h2 == r2) and (r3 is None or h3 == r3):
            return product
    return F_DECISIONS[-1][1]


def decide(verdicts: dict) -> str:          # kept for backwards compatibility
    return decide_polymarket(verdicts)


def _polymarket_context(settings, dataset):
    from walletlens.research.context import ResearchContext
    return ResearchContext(settings, dataset)


def _crypto_context(settings, dataset):
    from walletlens.topics.crypto.context import CryptoContext
    return CryptoContext(settings, dataset)


def _events_context(settings, dataset):
    from walletlens.topics.events.context import EventsContext
    return EventsContext(settings, dataset)


def _wallets_context(settings, dataset):
    from walletlens.topics.events.wallet_context import WalletContext
    return WalletContext(settings, dataset)


def _decide_wallets(verdicts):
    from walletlens.topics.events.wallet_context import decide
    return decide(verdicts)


def _decide_crypto(verdicts):
    from walletlens.topics.crypto.context import decide
    return decide(verdicts)


def _decide_events(verdicts):
    from walletlens.topics.events.context import decide
    return decide(verdicts)


def _daily_context(settings, dataset):
    from walletlens.topics.events.daily import DailyContext
    return DailyContext(settings, dataset)


def _decide_daily(verdicts):
    from walletlens.topics.events.daily import decide
    return decide(verdicts)


SUITES = {
    "polymarket": Suite("polymarket", "F · Smart money inside Polymarket", "walletlens.research.experiments",
                        ("e0_data", "e1_calibration", "e2_persistence", "e3_information", "e4_tradability", "e5_export"),
                        _polymarket_context, decide_polymarket, "universe", export_id="e5"),
    "crypto": Suite("crypto", "T1 · Polymarket crypto markets as a lead signal for BTC/ETH",
                    "walletlens.topics.crypto.experiments",
                    ("c0_data", "c1_market_lead", "c2_wallet_lead", "c3_trading"),
                    _crypto_context, _decide_crypto, "crypto"),
    "events": Suite("events", "T2 · Event-probability shocks and the assets they move",
                    "walletlens.topics.events.experiments",
                    ("v0_data", "v1_sensitivity", "v2_lead", "v3_wallet_lead", "v4_stability", "v5_robustness"),
                    _events_context, _decide_events, "events"),
    "wallets": Suite("wallets", "T2-W · Can wallets help the event-risk monitor?", "walletlens.topics.events.experiments",
                     ("w0_data", "w1_confirmation", "w2_persistence", "w3_early_warning", "w4_direction", "w5_wallet_types", "w6_robustness", "w7_cluster_holding"),
                     _wallets_context, _decide_wallets, "events"),
    "daily": Suite("daily", "T2-D · Daily-use applicability (docs/05)", "walletlens.topics.events.experiments",
                   ("d1_point_in_time", "d2_stability", "d3_alerts", "d4_live", "d5_daily", "d6_generality"),
                   _daily_context, _decide_daily, "events"),
}


def _ensure(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_suite(settings: Settings, suite_name: str, dataset: str | None, run_id: str, only: tuple | None = None) -> dict:
    suite = SUITES[suite_name]
    dataset = dataset or suite.default_dataset
    run_dir = settings.paths.results / run_id
    started = time.time()
    ctx = suite.context(settings, dataset)
    results = []
    for name in suite.experiments:
        experiment_id = name.split("_")[0]
        if only and experiment_id not in only:
            continue
        log.info("--- %s / %s ---", suite_name, name)
        t0 = time.time()
        result = import_module(f"{suite.package}.{name}").run(ctx)
        result.seconds = time.time() - t0
        result.write(run_dir)
        plots.close_all()
        log.info("%s: %s | %s", experiment_id, result.verdict.upper(), result.headline)
        results.append(result)

    verdicts = {r.id: r.verdict for r in results}
    decision = suite.decide(verdicts) if not only else "Partial run: no decision."
    app_dir = run_dir / "app"
    export = next((r for r in results if r.id == suite.export_id), None)
    if export:
        for name, table in export.tables.items():
            io.write_csv(app_dir / f"{name}.csv", table)
        for name in export.artifacts:
            shutil.copyfile(run_dir / export.id / "artifacts" / name, _ensure(app_dir / name))
    io.write_json(app_dir / "findings.json", {
        "run_id": run_id, "suite": suite_name, "title": suite.title, "dataset": dataset, "decision": decision,
        "fair_value": getattr(getattr(ctx, "fair", None), "to_dict", lambda: {})(),
        "experiments": [r.summary() for r in results if r.id != suite.export_id]})

    manifest = {"run_id": run_id, "suite": suite_name, "title": suite.title, "dataset": dataset,
                "created_at": datetime.now(timezone.utc).isoformat(), "seconds": round(time.time() - started, 1),
                "walletlens": __version__, "python": platform.python_version(), "pandas": pd.__version__,
                "numpy": np.__version__, "settings": settings.to_dict(),
                "dataset_manifest": getattr(ctx, "manifest", {}), "context": getattr(ctx, "describe", lambda: {})(),
                "verdicts": verdicts, "decision": decision}
    io.write_json(run_dir / "manifest.json", manifest)
    _write_summary(run_dir, run_id, suite, dataset, results, decision)
    _update_index(settings, run_id, suite, dataset, verdicts, decision, complete=only is None)
    log.info("decision: %s", decision)
    log.info("results in %s (%.0f s)", run_dir, time.time() - started)
    return manifest


def run_all(settings: Settings, dataset: str, run_id: str, only: tuple | None = None) -> dict:
    """Topic F suite (the original entry point)."""
    return run_suite(settings, "polymarket", dataset, run_id, only)


def _write_summary(run_dir, run_id, suite, dataset, results, decision) -> None:
    lines = [f"# {suite.title}", "", f"Run `{run_id}` on dataset **{dataset}**.", "",
             "| Experiment | Verdict | Headline |", "|---|---|---|"]
    lines += [f"| [{r.id.upper()} {r.title}]({r.id}/summary.md) | **{r.verdict}** | {r.headline} |" for r in results]
    lines += ["", f"**Decision (pre-registered rule):** {decision}", ""]
    lines += [r.markdown(link_prefix=f"{r.id}/") for r in results]
    io.write_text(run_dir / "summary.md", "\n".join(lines))


def _update_index(settings: Settings, run_id, suite, dataset, verdicts, decision, complete: bool) -> None:
    index = settings.paths.results / "INDEX.md"
    divider = "|---|---|---|---|---|\n"
    header = "# Research runs\n\nNewest first.\n\n| run | topic | dataset | verdicts | decision |\n" + divider
    body = index.read_text(encoding="utf-8").split(divider, 1)[-1] if index.exists() else ""
    tests = ", ".join(f"{k}: {v}" for k, v in verdicts.items() if v != "descriptive") or "-"
    line = f"| [{run_id}]({run_id}/summary.md) | {suite.name} | {dataset} | {tests} | {decision} |\n"
    io.write_text(index, header + line + body)
    if not complete:
        return                                   # the app only ever points at complete runs
    latest_path = settings.paths.results / "latest.json"
    latest = io.read_json(latest_path) if latest_path.exists() else {}
    latest[f"{suite.name}:{dataset}"] = run_id
    latest["_newest"] = run_id
    io.write_json(latest_path, latest)
