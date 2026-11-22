"""Optional past-only wallet skill scores (flow-alignment-v1, vectorized).

Behaviour clustering groups wallets by *how* they trade; this module scores
*whether* their flow has tended to point toward the realized outcome. It is
independent of clustering and plugs into ``cluster_implied_probability`` in two
ways:

* filter: keep members whose score clears a threshold (``filter_by_skill``);
* weight: pass ``skill_weights`` as the membership ``weight`` column.

Score for wallet/entity ``w`` and meeting ``e`` (same definition as
``review_wallet_decisions.py``):

    alignment(w, e) = sum_m D_m * (y_m - p_m) / G

``D_m`` is YES-equivalent signed shares in the window before the market's
decision cutoff, ``G`` gross shares over all markets of the meeting, ``p_m`` the
latest market probability at or before the cutoff, ``y_m`` the realized outcome.
Across meetings the score is shrunk toward zero:

    skill(w) = sum_e alignment(w, e) / (meetings_scored + prior_meetings)

**Leakage rule:** pass ``as_of``; only meetings whose decision cutoff is
strictly before ``as_of`` are scored, because ``y_m`` must already be known.
This measures flow association with outcomes, not trading profit.
"""
from __future__ import annotations

import pandas as pd

from cluster_implied_probability import signed_trades


def meeting_alignment(trades: pd.DataFrame, outcomes: pd.DataFrame,
                      window: pd.Timedelta = pd.Timedelta(days=7),
                      entity_map: pd.Series | None = None) -> pd.DataFrame:
    """One row per (entity, event_id) with ``alignment`` and ``gross_shares``.

    ``outcomes`` columns: ``event_id``, ``market_id``, ``decision_cutoff_utc``,
    ``cutoff_probability`` (p_m) and ``final_outcome`` (y_m).
    """
    data = signed_trades(trades)
    info = outcomes.copy()
    info["market_id"] = info["market_id"].astype(str)
    info["event_id"] = info["event_id"].astype(str)
    info["decision_cutoff_utc"] = pd.to_datetime(info["decision_cutoff_utc"], utc=True)
    overlap = [c for c in info.columns if c != "market_id" and c in data.columns]
    data = data.drop(columns=overlap).merge(info, on="market_id", how="inner")
    data = data.loc[data["timestamp_utc"].lt(data["decision_cutoff_utc"])
                    & data["timestamp_utc"].ge(data["decision_cutoff_utc"] - window)]
    data["entity_id"] = data["wallet_address"].map(entity_map) if entity_map is not None else data["wallet_address"]
    data["entity_id"] = data["entity_id"].fillna(data["wallet_address"])
    data["_num"] = data["signed_shares"] * (data["final_outcome"].astype(float) - data["cutoff_probability"].astype(float))
    out = data.groupby(["entity_id", "event_id"], as_index=False).agg(
        numerator=("_num", "sum"), gross_shares=("shares", "sum"),
        decision_cutoff_utc=("decision_cutoff_utc", "max"))
    out["alignment"] = out["numerator"] / out["gross_shares"]
    return out.drop(columns="numerator")


def skill_scores(alignment: pd.DataFrame, as_of, prior_meetings: float = 2.0) -> pd.DataFrame:
    """Shrunk mean alignment per entity using only meetings resolved before ``as_of``."""
    as_of = pd.Timestamp(as_of)
    as_of = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of.tz_convert("UTC")
    past = alignment.loc[alignment["decision_cutoff_utc"].lt(as_of)]
    out = past.groupby("entity_id", as_index=False).agg(
        meetings_scored=("alignment", "size"), alignment_sum=("alignment", "sum"),
        mean_alignment=("alignment", "mean"))
    out["skill"] = out["alignment_sum"] / (out["meetings_scored"] + prior_meetings)
    out["as_of_utc"] = as_of
    return out.drop(columns="alignment_sum")


def filter_by_skill(memberships: pd.DataFrame, scores: pd.DataFrame,
                    min_skill: float = 0.0, min_meetings: int = 2,
                    key: str = "wallet_address") -> pd.DataFrame:
    """Keep members with enough scored meetings and skill above the threshold."""
    good = scores.loc[scores["meetings_scored"].ge(min_meetings) & scores["skill"].gt(min_skill), "entity_id"]
    return memberships.loc[memberships[key].isin(set(good))].copy()


def skill_weights(memberships: pd.DataFrame, scores: pd.DataFrame,
                  key: str = "wallet_address", floor: float = 0.0) -> pd.Series:
    """Non-negative weights: positive part of skill; unscored members get ``floor``."""
    mapped = memberships[key].map(scores.set_index("entity_id")["skill"])
    return mapped.clip(lower=0).fillna(floor)
