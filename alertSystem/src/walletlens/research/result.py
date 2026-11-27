"""The structured output every experiment returns, and how it is written to disk.

results/<run_id>/
    manifest.json            settings, dataset manifest, software versions, timings
    summary.md               one section per experiment, verdicts first
    <experiment_id>/
        summary.json         machine-readable headline numbers and verdict
        summary.md           the same for people
        tables/<name>.csv
        figures/<name>.png
    app/                     artefacts the web app loads (wallet scores, fair value, findings)
results/INDEX.md            one line per run
results/latest.json         pointer to the newest run per dataset
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from walletlens import io

VERDICTS = ("pass", "fail", "inconclusive", "descriptive")


@dataclass
class ExperimentResult:
    id: str
    title: str
    question: str
    verdict: str
    headline: str
    metrics: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)          # name -> DataFrame
    figures: dict = field(default_factory=dict)         # name -> matplotlib Figure
    artifacts: dict = field(default_factory=dict)       # relative path -> JSON-serialisable object
    notes: list = field(default_factory=list)
    seconds: float = 0.0

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}")

    def write(self, run_dir: Path) -> Path:
        folder = run_dir / self.id
        for name, table in self.tables.items():
            io.write_csv(folder / "tables" / f"{name}.csv", table)
        for name, figure in self.figures.items():
            path = folder / "figures" / f"{name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path, dpi=150, bbox_inches="tight")
        for name, value in self.artifacts.items():
            io.write_json(folder / "artifacts" / name, _clean(value), indent=None)
        io.write_json(folder / "summary.json", self.summary())
        io.write_text(folder / "summary.md", self.markdown(link_prefix=""))
        return folder

    def summary(self) -> dict:
        return {"id": self.id, "title": self.title, "question": self.question, "verdict": self.verdict,
                "headline": self.headline, "metrics": _clean(self.metrics), "notes": self.notes,
                "tables": sorted(self.tables), "figures": sorted(self.figures), "seconds": round(self.seconds, 1)}

    def markdown(self, link_prefix: str) -> str:
        lines = [f"## {self.id.upper()} · {self.title}", "",
                 f"**Question.** {self.question}", "",
                 f"**Verdict: {self.verdict.upper()}.** {self.headline}", ""]
        if self.metrics:
            lines += ["| metric | value |", "|---|---|"]
            lines += [f"| {k} | {_fmt(v)} |" for k, v in _flatten(self.metrics).items()]
            lines.append("")
        for name in sorted(self.figures):
            lines += [f"![{name}]({link_prefix}figures/{name}.png)", ""]
        if self.tables:
            lines.append("Tables: " + ", ".join(f"[{n}]({link_prefix}tables/{n}.csv)" for n in sorted(self.tables)))
            lines.append("")
        if self.notes:
            lines += [f"- {note}" for note in self.notes] + [""]
        return "\n".join(lines)


def _flatten(metrics: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in metrics.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, name + "."))
        else:
            out[name] = value
    return out


def _fmt(value) -> str:
    if isinstance(value, float):
        if math.isnan(value):
            return "n/a"
        return f"{value:.4g}"
    return str(value)


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def frame_or_empty(rows) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()
