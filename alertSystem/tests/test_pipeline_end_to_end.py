"""Collector -> dataset -> research, on a synthetic world with known answers."""

from __future__ import annotations

import pandas as pd

from walletlens import io
from walletlens.collect import pipeline
from walletlens.research.runner import run_all
from conftest import FakeApi, synthetic_world


def test_collector_builds_complete_dataset(settings, world):
    api = FakeApi(world)
    pipeline.run(settings, fetch=api)
    folder = settings.paths.dataset("universe")
    manifest = io.read_json(folder / "manifest.json")
    assert manifest["markets"] == len(world["gamma"])
    expected = sum(len(v) for v in world["trades"].values())
    assert manifest["trades"] == expected
    assert manifest["validation_problems"] == []
    # every market's trades were paged to the end
    status = pd.read_csv(settings.paths.interim / "download_status.csv")
    assert status["exhausted"].all() and not status["truncated"].any()


def test_collector_resumes_without_refetching(settings, world):
    api = FakeApi(world)
    pipeline.run(settings, stages=("universe", "screen", "sample"), fetch=api)
    pipeline.stage_download(settings, max_markets=5, fetch=api)
    calls_before = len(api.calls)
    pipeline.stage_download(settings, max_markets=5, fetch=api)
    assert len(api.calls) == calls_before                       # nothing fetched twice
    pipeline.stage_download(settings, fetch=api)
    assert len(list((settings.paths.interim / "trades").glob("*.csv.gz"))) == len(world["gamma"])


def test_research_finds_planted_skill(settings, world):
    pipeline.run(settings, fetch=FakeApi(world))
    manifest = run_all(settings, "universe", "planted")
    assert manifest["verdicts"]["e2"] == "pass"                  # skill persists
    e3 = io.read_json(settings.paths.results / "planted" / "e3" / "summary.json")
    assert e3["metrics"]["main"]["diff"] > 0                     # skilled trades carry information
    scores = pd.read_csv(settings.paths.results / "planted" / "app" / "wallet_scores.csv")
    top = set(scores.loc[scores["tier"] == "top", "wallet"])
    skilled = set(world["wallets"][: world["skilled"]])
    assert len(top & skilled) / len(top) > 0.5                   # the top tier is mostly the planted wallets


def test_research_finds_nothing_without_skill(settings):
    world = synthetic_world(seed=3, skill_strength=0.0)
    pipeline.run(settings, fetch=FakeApi(world))
    manifest = run_all(settings, "universe", "null")
    assert manifest["verdicts"]["e2"] != "pass"
