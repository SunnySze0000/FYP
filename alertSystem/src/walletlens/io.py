"""Small, safe file helpers: atomic writes and one table format for the whole project."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pandas as pd


def write_json(path: Path, value, indent: int = 2) -> None:
    """Write JSON through a temporary file so an interrupted run never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=indent, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    """CSV (gzip when the name ends in .gz), written atomically, with a fixed float format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if path.suffix == ".gz":
        with gzip.GzipFile(tmp, "wb", mtime=0) as handle:          # mtime=0: byte-identical reruns
            handle.write(frame.to_csv(index=False, float_format="%.6g").encode("utf-8"))
    else:
        frame.to_csv(tmp, index=False, float_format="%.6g")
    os.replace(tmp, path)


def write_table(path: Path, frame: pd.DataFrame) -> None:
    """Large analysis tables: compressed pickle (pandas only, fast, no extra packages)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    frame.to_pickle(tmp, compression="gzip")
    os.replace(tmp, path)


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_pickle(path, compression="gzip")
