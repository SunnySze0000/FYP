"""Meeting registry and trade-file discovery for multi-meeting runs.

Decision cutoff per meeting (the last instant whose trading may be used):

1. Gamma ``endDate`` minus 24 hours, when the collector's saved
   ``raw/market.json`` is available (latest across the meeting's markets);
2. otherwise the EARLIEST of the meeting's per-market last
   ``forward_probabilities.csv`` dates, minus one day. This reproduces all 21
   cutoffs recorded in the frozen pilot. (Using the latest market's last date
   was wrong: in Oct 2025 one market kept quoting two days after the decision,
   which put the cutoff after the announcement.)

The clustering cutoff is ``decision_cutoff - signal_days``: behaviour is
measured strictly before it, and cluster signals run from it to the decision
cutoff (June: 2026-05-31 -> 2026-06-16, i.e. 16 days).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

TRADE_LOCATIONS = (
    "datasets/polymarket/market_{m}/wallet_trades.csv.gz",
    "tmp/polymarket/history_market_{m}/wallet_trades.csv.gz",
    "tmp/polymarket/history_market_{m}/wallet_trades.csv",
)


def trade_file(root: Path, market_id) -> Path | None:
    for pattern in TRADE_LOCATIONS:
        path = root / pattern.format(m=market_id)
        if path.exists():
            return path
    return None


def collection_complete(root: Path, market_id) -> bool | None:
    """True/False from the collector manifest; None if no manifest is present."""
    for base in (f"datasets/polymarket/market_{market_id}", f"tmp/polymarket/history_market_{market_id}"):
        path = root / base / "manifest.json"
        if path.exists():
            return bool(json.loads(path.read_text()).get("exhausted_api_cursor"))
    return None


def _gamma_cutoff(root: Path, market_id):
    path = root / f"tmp/polymarket/history_market_{market_id}/raw/market.json"
    if not path.exists():
        return None
    end = json.loads(path.read_text()).get("endDate")
    return pd.Timestamp(end).tz_convert("UTC") - pd.Timedelta(hours=24) if end else None


def registry(root: Path, probability: pd.DataFrame, signal_days: float = 16.0) -> pd.DataFrame:
    """One row per meeting: markets, cutoffs, data availability."""
    data = probability.copy()
    data["date"] = pd.to_datetime(data["date"], utc=True)
    rows = []
    for event_id, part in data.groupby("event_id"):
        markets = sorted(str(m) for m in part["market_id"].unique())
        gamma = [c for c in (_gamma_cutoff(root, m) for m in markets) if c is not None]
        last_by_market = part.groupby("market_id")["date"].max()
        decision = max(gamma) if gamma else last_by_market.min() - pd.Timedelta(days=1)
        files = {m: trade_file(root, m) for m in markets}
        complete = [collection_complete(root, m) for m in markets]
        rows.append(dict(
            event_id=str(event_id), meeting_month=part["meeting_month"].iloc[0], markets=markets,
            decision_cutoff_utc=decision, cluster_cutoff_utc=decision - pd.Timedelta(days=signal_days),
            cutoff_source="gamma_end_date" if gamma else "last_probability_date",
            markets_with_trades=sum(f is not None for f in files.values()),
            trades_available=all(f is not None for f in files.values()),
            collection_complete=all(c is True for c in complete),
            trade_files={m: str(f.relative_to(root)) if f else None for m, f in files.items()}))
    return pd.DataFrame(rows).sort_values("decision_cutoff_utc").reset_index(drop=True)
