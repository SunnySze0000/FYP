"""Frozen-wallet daily panels with strict UTC intervals and explicit coverage.

Rows describe participant trading flow, not holdings, beliefs or market volume.
Historical panels use later-fitted memberships and are never forecast inputs.
"""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DIRECTIONS = ("buy_yes", "sell_yes", "buy_no", "sell_no")
PANEL_COLUMNS = [
    "snapshot_id", "asof_utc", "interval_start_utc", "event_id", "market_id",
    "rate_outcome", "condition_id", "cluster_id", "model_version",
    "model_fit_cutoff_utc", "decision_cutoff_utc", "cluster_member_count",
    "active_wallet_count", "participant_rows", "unique_transactions", "gross_shares",
    "gross_participant_notional_usd", "buy_yes_shares", "sell_yes_shares",
    "buy_no_shares", "sell_no_shares", "signed_yes_flow_shares",
    "aggregate_directional_imbalance", "equal_weight_directional_imbalance",
    "largest_wallet_notional_fraction", "no_activity", "coverage_complete",
    "complete_wallet_count", "forecast_input_allowed", "availability_basis",
]
ACTIVITY_COLUMNS = [
    "active_wallet_count", "participant_rows", "unique_transactions", "gross_shares",
    "gross_participant_notional_usd", "buy_yes_shares", "sell_yes_shares",
    "buy_no_shares", "sell_no_shares", "signed_yes_flow_shares",
    "aggregate_directional_imbalance", "equal_weight_directional_imbalance",
    "largest_wallet_notional_fraction", "no_activity",
]


def _instant(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("Daily inputs require timezone-aware timestamps")
    return stamp.tz_convert("UTC")


def _truth(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1"}


def aggregate_four_direction(rows: pd.DataFrame) -> dict[str, Any]:
    """Aggregate a complete wallet/market/day subset; preserve participant rows.

    The transaction count is a set union across wallets: a shared transaction is
    counted once, while all participant records and shares remain represented.
    """
    if rows.empty:
        result = {name: 0 for name in ACTIVITY_COLUMNS}
        result.update(aggregate_directional_imbalance=np.nan,
                      equal_weight_directional_imbalance=np.nan,
                      largest_wallet_notional_fraction=np.nan, no_activity=True)
        return result
    values = rows.copy()
    values["shares"] = pd.to_numeric(values["shares"], errors="raise")
    values["notional_usd"] = pd.to_numeric(values["notional_usd"], errors="raise")
    if not np.isfinite(values[["shares", "notional_usd"]].to_numpy()).all():
        raise ValueError("Non-finite trade amount")
    if (values["shares"] <= 0).any() or (values["notional_usd"] < 0).any():
        raise ValueError("Invalid trade amount")
    action = values["side"].str.lower() + "_" + values["token_outcome"].str.lower()
    if not action.isin(DIRECTIONS).all():
        raise ValueError("Unsupported side/token outcome")
    direction = action.map({"buy_yes": 1, "sell_yes": -1, "buy_no": -1, "sell_no": 1})
    values["_signed"] = values["shares"] * direction
    gross = float(values["shares"].sum())
    notional = float(values["notional_usd"].sum())
    signed = float(values["_signed"].sum())
    wallet = values.groupby("wallet_address", sort=True).agg(
        gross=("shares", "sum"), signed=("_signed", "sum"),
        notional=("notional_usd", "sum"))
    result = {
        "active_wallet_count": int(len(wallet)), "participant_rows": int(len(values)),
        "unique_transactions": int(values["transaction_hash"].nunique()),
        "gross_shares": gross, "gross_participant_notional_usd": notional,
        "signed_yes_flow_shares": signed,
        "aggregate_directional_imbalance": signed / gross,
        "equal_weight_directional_imbalance": float((wallet["signed"] / wallet["gross"]).mean()),
        "largest_wallet_notional_fraction": float(wallet["notional"].max() / notional) if notional else np.nan,
        "no_activity": False,
    }
    result.update({name + "_shares": float(values.loc[action.eq(name), "shares"].sum())
                   for name in DIRECTIONS})
    return result


def _memberships(memberships: pd.DataFrame, config: dict) -> pd.DataFrame:
    if memberships.empty:
        return pd.DataFrame(columns=["wallet_address", "cluster_id", "model_version"])
    required = {"wallet_address", "cluster_id"}
    if not required.issubset(memberships.columns):
        raise ValueError("Membership table missing wallet_address/cluster_id")
    result = memberships.copy()
    assigned = result["cluster_id"].notna() & result["cluster_id"].astype(str).ne("")
    result = result.loc[assigned].copy()
    result["wallet_address"] = result["wallet_address"].str.lower()
    if result["wallet_address"].duplicated().any():
        raise ValueError("Duplicate assigned wallet")
    # Keep numeric labels stable rather than turning integer labels into 0.0.
    result["cluster_id"] = result["cluster_id"].map(
        lambda x: str(int(x)) if isinstance(x, (int, float, np.integer, np.floating)) and float(x).is_integer() else str(x))
    if "model_version" not in result:
        result["model_version"] = config.get("model_version", config["snapshot_id"])
    if result["model_version"].isna().any() or result["model_version"].nunique() > 1:
        raise ValueError("Daily panel requires one frozen model version")
    return result[["wallet_address", "cluster_id", "model_version"]]


def _map_markets(market_map: list[dict]) -> dict[str, dict]:
    result = {}
    for source in market_map:
        row = dict(source)
        for name in ("event_id", "market_id", "condition_id"):
            if name in row:
                row[name] = str(row[name])
        mid = row["market_id"]
        if not row.get("decision_cutoff_utc"):
            raise ValueError(f"Missing pre-decision cutoff for market {mid}")
        _instant(row["decision_cutoff_utc"])
        if mid in result:
            for field in ("event_id", "condition_id", "decision_cutoff_utc", "rate_outcome"):
                if result[mid].get(field) != row.get(field):
                    raise ValueError(f"Inconsistent market mapping: {mid}/{field}")
        else:
            result[mid] = row
    return result


def _target_sources(root: Path, config: dict, cohort: list[dict], maps: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = root / "datasets" / "polymarket"
    event = str(config["target_event_id"])
    with (base / f"event_{event}" / "market_inventory.csv").open(newline="") as handle:
        inventory = list(csv.DictReader(handle))
    selected = {row["wallet_address"].lower() for row in cohort}
    records, coverage = [], []
    expected = {key for key, row in maps.items() if row["event_id"] == event}
    actual = {str(row["market_id"]) for row in inventory}
    if expected != actual:
        raise ValueError("Target map and source market inventory differ")
    for item in sorted(inventory, key=lambda row: row["market_id"]):
        mid = str(item["market_id"])
        source = (base / f"event_{event}" / item["market_directory"]).resolve()
        path = source / "wallet_trades.csv.gz"
        metadata = source / "manifest.json"
        complete, status, seen, selected_count = False, "missing_source", 0, 0
        if path.exists() and metadata.exists():
            manifest = json.loads(metadata.read_text())
            with gzip.open(path, "rt", newline="") as handle:
                for row in csv.DictReader(handle):
                    seen += 1
                    if row["wallet_address"].lower() in selected:
                        if str(row["market_id"]) != mid or str(row["event_id"]) != event:
                            raise ValueError("Target trade source market/event mismatch")
                        if row["condition_id"].lower() != maps[mid]["condition_id"].lower():
                            raise ValueError("Target trade condition differs from mapping")
                        selected_count += 1
                        records.append({**row,
                            "source_snapshot_id": f"existing_market_{mid}",
                            "source_query": f"existing_market_{mid}",
                            "source_file": str(path.relative_to(root)),
                            "decision_cutoff_utc": maps[mid]["decision_cutoff_utc"]})
            complete = (_truth(manifest.get("exhausted_api_cursor"))
                        and _truth(item.get("exhausted_api_cursor"))
                        and seen == int(manifest.get("clean_rows", -1)) == int(item["participant_rows"])
                        and int(manifest.get("rejected_rows", -1)) == 0
                        and int(item.get("rejected_rows", -1)) == 0)
            status = "complete_served_export" if complete else "incomplete_or_inconsistent_export"
        for wallet in sorted(selected):
            coverage.append({"wallet_address": wallet, "event_id": event, "market_id": mid,
                "complete": complete, "status": status, "source_file": str(path.relative_to(root)),
                "source_participant_rows": seen, "selected_participant_rows": selected_count,
                "availability_basis": "trade_timestamp_only_retrospective"})
    return pd.DataFrame(records), pd.DataFrame(coverage)


def _panel(trades: pd.DataFrame, membership: pd.DataFrame, maps: dict, event_ids: set[str],
           config: dict, forecast: bool, coverage: pd.DataFrame | None = None) -> pd.DataFrame:
    if membership.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    selection = _instant(config["selection_cutoff_utc"])
    observation = _instant(config["observation_start_utc"])
    values = trades.copy()
    if not values.empty:
        values["wallet_address"] = values["wallet_address"].str.lower()
        values["market_id"] = values["market_id"].astype(str)
        values["event_id"] = values["event_id"].astype(str)
        values["_timestamp"] = pd.to_datetime(values["timestamp_utc"], utc=True, errors="raise")
        values["_asof"] = values["_timestamp"].dt.floor("D") + pd.Timedelta(days=1)
        values = values.merge(membership, on="wallet_address", how="inner", validate="many_to_one")
    groups = {}
    if not values.empty:
        for key, frame in values.groupby(["market_id", "cluster_id", "_asof"], sort=False):
            groups[key] = frame
    empty = pd.DataFrame(columns=["wallet_address", "shares", "notional_usd", "side", "token_outcome", "transaction_hash"])
    result = []
    for mid, market in sorted(maps.items()):
        event = str(market["event_id"])
        if event not in event_ids:
            continue
        cutoff = _instant(market["decision_cutoff_utc"])
        start = selection.ceil("D") if forecast else observation.floor("D") + pd.Timedelta(days=1)
        end = cutoff.floor("D")
        if not forecast:
            end = min(end, selection.floor("D"))
        for cluster, members in membership.groupby("cluster_id", sort=True):
            addresses = set(members["wallet_address"])
            if coverage is None:
                # Assignment requires complete historical coverage in feature builder.
                complete_count = len(addresses)
            else:
                statuses = coverage.loc[coverage["market_id"].astype(str).eq(mid)
                                        & coverage["wallet_address"].isin(addresses)]
                complete_count = int(statuses.loc[statuses["complete"].map(_truth), "wallet_address"].nunique())
            complete = complete_count == len(addresses)
            for asof in pd.date_range(start, end, freq="D"):
                interval = asof - pd.Timedelta(days=1)
                frame = groups.get((mid, cluster, asof), empty)
                if not frame.empty:
                    frame = frame.loc[frame["_timestamp"].ge(interval)
                                      & frame["_timestamp"].lt(asof)
                                      & frame["_timestamp"].lt(cutoff)]
                    if not forecast:
                        frame = frame.loc[frame["_timestamp"].ge(observation)
                                          & frame["_timestamp"].lt(selection)]
                stats = aggregate_four_direction(frame) if complete else {name: np.nan for name in ACTIVITY_COLUMNS}
                result.append({"snapshot_id": config["snapshot_id"], "asof_utc": asof.isoformat(),
                    "interval_start_utc": interval.isoformat(), "event_id": event, "market_id": mid,
                    "rate_outcome": market.get("rate_outcome", ""), "condition_id": market.get("condition_id", ""),
                    "cluster_id": cluster, "model_version": str(members["model_version"].iloc[0]),
                    "model_fit_cutoff_utc": selection.isoformat(), "decision_cutoff_utc": cutoff.isoformat(),
                    "cluster_member_count": len(addresses), **stats,
                    "coverage_complete": complete, "complete_wallet_count": complete_count,
                    "forecast_input_allowed": bool(forecast and complete and asof >= selection and asof <= cutoff),
                    "availability_basis": "trade_timestamp_only_retrospective"})
    return pd.DataFrame(result, columns=PANEL_COLUMNS)


def build_daily(cohort: list[dict], memberships: pd.DataFrame, history_trades: list[dict],
                market_map: list[dict], root: Path, config: dict) -> dict:
    """Read the existing June exports and produce separate forecast/descriptive panels."""
    root = Path(root).resolve()
    members = _memberships(memberships, config)
    selected = {row["wallet_address"].lower() for row in cohort}
    if not set(members["wallet_address"]).issubset(selected):
        raise ValueError("Assigned membership contains a wallet outside frozen cohort")
    maps = _map_markets(market_map)
    target, coverage = _target_sources(root, config, cohort, maps)
    signals = _panel(target, members, maps, {str(config["target_event_id"])}, config, True, coverage)
    historical = _panel(pd.DataFrame(history_trades), members, maps,
                        {str(event) for event in config["history_event_ids"]}, config, False)
    if not signals.empty and signals.duplicated(["asof_utc", "event_id", "market_id", "cluster_id", "model_version"]).any():
        raise AssertionError("Duplicate daily signal key")
    report = {"selected_wallets": len(selected), "assigned_wallets": len(members),
        "unassigned_wallets_excluded_from_cluster_signals": len(selected) - len(members),
        "target_trade_rows": len(target), "forecast_signal_rows": len(signals),
        "historical_descriptive_rows": len(historical),
        "incomplete_target_wallet_market_queries": int((~coverage["complete"].map(_truth)).sum()) if not coverage.empty else 0,
        "forecast_start_utc": signals["asof_utc"].min() if not signals.empty else None,
        "forecast_end_utc": signals["asof_utc"].max() if not signals.empty else None,
        "daily_interval": "[asof_utc - 24h, asof_utc)",
        "historical_forecast_input_allowed": False,
        "availability_basis": "trade_timestamp_only_retrospective",
        "coverage_scope": "served API exports; not full-chain completeness",
    }
    return {"signals": signals, "historical": historical, "target_trades": target,
            "coverage": coverage, "report": report}
