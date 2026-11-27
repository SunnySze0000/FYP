"""Command line: ``python -m walletlens [--profile NAME] <command>``.

    run-all   [--no-collect]                     every collector in parallel, then every research suite
    collect   --topic polymarket|crypto|events [--stages a,b] [--max-markets N]
    research  --topic polymarket|crypto|events [--dataset NAME] [--only e1,e2]
    pilot     --source <folder of FYP Fed exports>   build + research the Fed pilot
    check     test the internet connections the collectors need
    live-check  D4: can the app fetch live data fast enough (docs/05)
    status    list datasets and research runs
    app       start EventLens, the event-risk monitor [--replay 2025-04-07T14:00]
    export    rebuild the monitor model from the research data

Profiles are JSON overrides in config/ (e.g. --profile quick for a small trial run).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from walletlens import io, logs
from walletlens.config import load_settings


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def cmd_collect(args) -> None:
    settings = load_settings(args.profile)
    logs.setup(settings.paths.logs, f"collect-{args.topic}-{_stamp()}")
    stages = tuple(s.strip() for s in args.stages.split(",")) if args.stages else None
    if args.topic == "polymarket":
        from walletlens.collect import pipeline as module
        module.run(settings, stages=stages or module.STAGES, max_markets=args.max_markets)
    elif args.topic == "crypto":
        from walletlens.topics.crypto import collect as module
        module.run(settings, stages=stages or module.STAGES, max_markets=args.max_markets)
    else:
        from walletlens.topics.events import collect as module
        module.run(settings, stages=stages or module.STAGES)


def cmd_research(args) -> None:
    from walletlens.research.runner import SUITES, run_suite

    settings = load_settings(args.profile)
    dataset = args.dataset or SUITES[args.topic].default_dataset
    run_id = f"{_stamp()}_{args.topic}_{dataset}"
    logs.setup(settings.paths.logs, f"research-{run_id}")
    only = tuple(args.only.split(",")) if args.only else None
    run_suite(settings, args.topic, dataset, run_id, only=only)


def cmd_run_all(args) -> None:
    from walletlens.orchestrate import run_all

    settings = load_settings(args.profile)
    logs.setup(settings.paths.logs, f"run-all-{_stamp()}")
    run_all(settings, args.profile, collect=not args.no_collect)


def cmd_pilot(args) -> None:
    from walletlens.data.build import build_pilot
    from walletlens.research.runner import run_suite

    settings = load_settings(args.profile or "pilot")
    logs.setup(settings.paths.logs, f"pilot-{_stamp()}")
    folders = []
    for source in args.source:
        root = Path(source)
        found = sorted(p for p in root.iterdir() if p.is_dir() and (p / "wallet_trades.csv.gz").exists())
        folders += found if found else [root]
    build_pilot(settings, folders, name="pilot_fed")
    run_suite(settings, "polymarket", "pilot_fed", f"{_stamp()}_polymarket_pilot_fed")


def cmd_check(args) -> None:
    from walletlens.orchestrate import connectivity

    for name, state in connectivity().items():
        print(f"{name:<22} {state}")


def cmd_status(args) -> None:
    settings = load_settings(args.profile)
    for path in sorted(settings.paths.processed.glob("*/manifest.json")):
        manifest = io.read_json(path)
        print(f"dataset {manifest.get('dataset', path.parent.name):<10} markets={manifest.get('markets')} "
              f"trades={manifest.get('trades', '-')}")
    for name in ("OVERVIEW.md", "INDEX.md"):
        path = settings.paths.results / name
        if path.exists():
            print(path.read_text(encoding="utf-8"))


def cmd_app(args) -> None:
    from walletlens.app.server import serve
    from walletlens.monitor.service import Service
    from walletlens.monitor.sources import LiveSource, ReplaySource

    settings = load_settings(args.profile)
    logs.setup(settings.paths.logs, f"app-{_stamp()}")
    root = settings.paths.root
    if not (root / "data" / "app" / "model.json").exists():
        from walletlens.monitor.export import export
        export(settings, _latest_run(settings, "daily:events"))
    if args.replay:
        at = datetime.fromisoformat(args.replay).replace(tzinfo=timezone.utc).timestamp()
        source = ReplaySource(root, at)
    else:
        source = LiveSource()
    service = Service(root, source, refresh_seconds=args.refresh, results_run=_latest_run(settings, "daily:events"))
    serve(service, settings.app.host, args.port or settings.app.port, open_browser=not args.no_browser)


def cmd_export(args) -> None:
    from walletlens.monitor.export import export

    settings = load_settings(args.profile)
    logs.setup(settings.paths.logs, f"export-{_stamp()}")
    export(settings, _latest_run(settings, "daily:events"))


def cmd_calibrate(args) -> None:
    from walletlens.monitor import calibration
    from walletlens.monitor.engine import Model
    from walletlens.monitor.sources import LiveSource

    settings = load_settings(args.profile)
    logs.setup(settings.paths.logs, f"calibrate-{_stamp()}")
    out = settings.paths.results / f"{_stamp()}_live_calibration" / "d7_live_calibration.json"
    result = calibration.run(LiveSource(), Model.load(settings.paths.root / "data" / "app"), out)
    print(f"D7 live calibration: {result['verdict'].upper()} flag rate {result['flag_rate']}  ->  {out}")


def _latest_run(settings, key: str):
    path = settings.paths.results / "latest.json"
    return io.read_json(path).get(key) if path.exists() else None


def cmd_live_check(args) -> None:
    from walletlens.topics.events import live_check

    settings = load_settings(args.profile)
    run_id = f"{_stamp()}_live_check"
    logs.setup(settings.paths.logs, f"live-check-{_stamp()}")
    result = live_check.run(settings, run_id)
    print(f"D4 live check: {result['verdict'].upper()}  ->  results/{run_id}/summary.md")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="walletlens", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", help="config/<profile>.json overrides")
    sub = parser.add_subparsers(dest="command", required=True)
    topics = ("polymarket", "crypto", "events", "wallets", "daily")

    p = sub.add_parser("run-all", help="collect everything in parallel, then run every research suite")
    p.add_argument("--no-collect", action="store_true")
    p.set_defaults(func=cmd_run_all)

    p = sub.add_parser("collect", help="download one topic's data (resumable)")
    p.add_argument("--topic", choices=topics, default="polymarket")
    p.add_argument("--stages")
    p.add_argument("--max-markets", type=int)
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("research", help="run one topic's pre-registered experiments")
    p.add_argument("--topic", choices=topics, default="polymarket")
    p.add_argument("--dataset")
    p.add_argument("--only")
    p.set_defaults(func=cmd_research)

    p = sub.add_parser("pilot", help="build and research the Fed pilot from existing FYP exports")
    p.add_argument("--source", action="append", required=True)
    p.set_defaults(func=cmd_pilot)

    sub.add_parser("check", help="test internet access to every data source").set_defaults(func=cmd_check)
    sub.add_parser("live-check", help="D4: test the live data the app needs").set_defaults(func=cmd_live_check)
    sub.add_parser("status", help="list datasets and research runs").set_defaults(func=cmd_status)

    p = sub.add_parser("app", help="start the web app")
    p.add_argument("--port", type=int)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--replay", help="UTC time, e.g. 2025-04-07T14:00: replay the research data at that moment")
    p.add_argument("--refresh", type=int, default=300, help="seconds between live scans")
    p.set_defaults(func=cmd_app)
    sub.add_parser("calibrate", help="D7: replay the last 24 h of live data through the early warning").set_defaults(func=cmd_calibrate)
    sub.add_parser("export", help="export the monitor model from the research data").set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
