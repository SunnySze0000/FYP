"""Bounded, resumable collection for a frozen wallet-clustering cohort.

This module deliberately separates the wallet-selection cutoff from the queried
history window. Source participant records retain multiplicity; fingerprints are
diagnostics, not fill identifiers. No outcome labels are exported as features.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collect_history import atomic_json
from collect_pilot import array, clean_trades, utc_now


def instant(value):
    value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Timezone-aware UTC timestamps are required")
    return value.astimezone(timezone.utc)


def truth(value):
    return value is True or str(value).lower() in {"true", "1"}


def read_csv(path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def select_cohort(root: Path, config: dict) -> list[dict]:
    """Proportional breadth/activity strata, with hash ordering inside each cell."""
    path = Path(root) / "datasets/polymarket" / ("event_" + str(config["target_event_id"])) / "wallet_discovery/wallet_summary_pre_cutoff.csv"
    rows = [r for r in read_csv(path) if truth(r["eligible"])]
    cutoff = instant(config["selection_cutoff_utc"])
    if any(instant(r["selection_cutoff_utc"]) != cutoff for r in rows):
        raise ValueError("Discovery cutoff differs from frozen selection cutoff")
    if len({r["wallet_address"] for r in rows}) != len(rows):
        raise ValueError("Discovery population contains duplicate wallets")
    target = int(config["target_wallets"])
    if target <= 0 or target > len(rows):
        raise ValueError("Requested cohort exceeds eligible population or is empty")
    groups = defaultdict(list)
    for row in rows:
        groups["broad" if int(row["markets_traded"]) >= 3 else "focused"].append(row)
    strata = defaultdict(list)
    for breadth, members in sorted(groups.items()):
        # Rank-based thirds give deterministic boundaries even with tied counts.
        ordered = sorted(members, key=lambda r: (int(r["unique_transactions"]), r["wallet_address"]))
        for index, row in enumerate(ordered):
            third = min(2, index * 3 // len(ordered)) + 1
            strata[f"{breadth}_activity_{third}"].append(row)
    quotas = {key: target * len(value) / len(rows) for key, value in strata.items()}
    allocations = {key: math.floor(value) for key, value in quotas.items()}
    remainders = sorted(strata, key=lambda key: (-(quotas[key] - allocations[key]), key))
    for key in remainders[:target - sum(allocations.values())]:
        allocations[key] += 1
    selected = []
    for stratum, members in sorted(strata.items()):
        rank_key = lambda row: hashlib.sha256(f"{config['seed']}|{row['wallet_address']}".encode()).hexdigest()
        ranked = sorted(members, key=lambda row: (rank_key(row), row["wallet_address"]))
        for rank, row in enumerate(ranked[:allocations[stratum]], 1):
            selected.append({
                "snapshot_id": config["snapshot_id"], "wallet_address": row["wallet_address"],
                "selection_cutoff_utc": cutoff.isoformat(), "sampling_stratum": stratum,
                "stratum_population": len(members), "stratum_allocation": allocations[stratum],
                "stratum_rank": rank, "selection_hash": rank_key(row), "sampling_seed": config["seed"],
                "selection_reason": "proportional_breadth_activity_hash_sample",
                "discovery_unique_transactions": int(row["unique_transactions"]),
                "discovery_active_days": int(row["active_days"]),
                "discovery_markets_traded": int(row["markets_traded"]),
            })
    return sorted(selected, key=lambda row: row["wallet_address"])


def _fetch_json(url, deadline):
    """Retries and socket timeouts stay within the shared collection budget."""
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Collection budget exhausted")
        try:
            request = Request(url, headers={"Content-Type": "application/json", "User-Agent": "EventLens-wallet-cluster-pilot/1"})
            with urlopen(request, timeout=min(20, remaining)) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(f"HTTP {error.code}; query not complete") from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError("Network request failed; query not complete") from None
        time.sleep(max(0, min(2 ** attempt, deadline - time.monotonic())))
    raise RuntimeError("Query not completed")


def _validate_target_metadata(metadata, market_id, tokens):
    """Validate cached metadata as strictly as a freshly fetched response."""
    if not isinstance(metadata, dict) or str(metadata.get("id")) != market_id:
        raise ValueError("Target Gamma market mismatch")
    conditions = {row["condition_id"].lower() for row in tokens}
    if conditions != {str(metadata.get("conditionId", "")).lower()}:
        raise ValueError("Target Gamma condition differs from local mapping")
    labels, token_ids = array(metadata.get("outcomes")), array(metadata.get("clobTokenIds"))
    if not isinstance(labels, list) or not isinstance(token_ids, list) or len(labels) != 2 or len(token_ids) != 2:
        raise ValueError("Target Gamma token mapping is incomplete")
    remote = {str(token): str(label).upper() for token, label in zip(token_ids, labels)}
    local = {row["token_id"]: row["token_outcome"] for row in tokens}
    if remote != local or set(remote.values()) != {"YES", "NO"}:
        raise ValueError("Target Gamma token mapping differs from local mapping")
    instant(metadata["endDate"])


def load_market_map(root: Path, config: dict, cache: Path, deadline=None) -> list[dict]:
    """Reuse source mappings; final outcomes remain outside this export."""
    root, cache = Path(root), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    deadline = deadline if deadline is not None else time.monotonic() + 90
    wanted = set(map(str, config["history_event_ids"]))
    prior = root / "datasets/polymarket/event_101772/prior_history/prior_market_tokens.csv"
    keep = ("event_id", "meeting_month", "market_id", "rate_outcome", "condition_id", "token_id", "token_outcome", "market_end_date_utc", "decision_cutoff_utc", "metadata_collected_at_utc")
    rows = [{key: row.get(key, "") for key in keep} | {
        "metadata_source": str(prior.relative_to(root)), "cutoff_method": "gamma_endDate_minus_24h_approximate",
        "original_resolution_time_verified": False,
    } for row in read_csv(prior) if row["event_id"] in wanted]
    if {row["event_id"] for row in rows} != wanted:
        raise ValueError("Historical market mapping is incomplete")
    target_path = root / "datasets/polymarket" / ("event_" + str(config["target_event_id"])) / "market_tokens.csv"
    target = read_csv(target_path)
    by_market = defaultdict(list)
    for row in target:
        by_market[row["market_id"]].append(row)
    for market_id, tokens in sorted(by_market.items()):
        path = cache / "metadata" / (market_id + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata, error = {}, ""
        if path.exists():
            envelope = json.loads(path.read_text())
            metadata = envelope["response"]
        elif config.get("offline", False):
            envelope, error = {}, "metadata_unavailable_offline"
        else:
            try:
                metadata = _fetch_json("https://gamma-api.polymarket.com/markets/" + market_id, deadline)
                _validate_target_metadata(metadata, market_id, tokens)
                envelope = {"collected_at_utc": utc_now(), "response": metadata}
                atomic_json(path, envelope)
            except (RuntimeError, TimeoutError) as exc:
                metadata, envelope, error = {}, {}, str(exc)
        if metadata:
            _validate_target_metadata(metadata, market_id, tokens)
        decision = config.get("target_decision_cutoff_utc", "")
        if metadata.get("endDate"):
            decision = (instant(metadata["endDate"]) - timedelta(days=1)).isoformat()
        for token in tokens:
            rows.append({key: token.get(key, "") for key in keep} | {
                "market_end_date_utc": metadata.get("endDate", ""),
                "decision_cutoff_utc": decision,
                "metadata_collected_at_utc": envelope.get("collected_at_utc", ""),
                "metadata_source": str(target_path.relative_to(root)),
                "metadata_status": error or "available",
                "cutoff_method": "gamma_endDate_minus_24h_approximate" if decision else "unavailable",
                "original_resolution_time_verified": False,
            })
    target_cutoffs = {row["decision_cutoff_utc"] for row in rows if row["event_id"] == str(config["target_event_id"]) and row.get("decision_cutoff_utc")}
    if len(target_cutoffs) > 1:
        raise ValueError("Target markets disagree on the approximate event cutoff")
    return rows


def _query_wallet(wallet, markets, config, cache, deadline):
    start, end = instant(config["observation_start_utc"]), instant(config["selection_cutoff_utc"])
    if start >= end:
        raise ValueError("Observation start must precede selection cutoff")
    query = {"user": wallet, "condition": ",".join(sorted(markets)), "taker_only": "false",
             "filter_type": "TOKENS", "filter_amount": "0.01", "limit": 1000,
             "start": int(start.timestamp()), "end": int(end.timestamp()) - 1}
    digest = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()
    query_root = Path(cache) / "wallets" / wallet / digest[:20]
    query_root.mkdir(parents=True, exist_ok=True)
    atomic_json(query_root / "config.json", query)
    cursor, seen, raw, pages, status, reason = None, set(), [], 0, "incomplete", ""
    try:
        for page in range(1, int(config.get("max_pages", 1000)) + 1):
            path = query_root / f"page_{page:05d}.json"
            if path.exists():
                envelope = json.loads(path.read_text())
                if envelope.get("request_cursor") != cursor:
                    raise ValueError("Cached cursor chain differs")
            else:
                if config.get("offline", False):
                    raise RuntimeError("Query page unavailable in offline cache")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Collection budget exhausted")
                params = dict(query)
                if cursor:
                    params["cursor"] = cursor
                response = _fetch_json("https://data-api.polymarket.com/v2/trades?" + urlencode(params), deadline)
                envelope = {"collected_at_utc": utc_now(), "request_cursor": cursor, "response": response}
                atomic_json(path, envelope)
            response = envelope["response"]
            if not isinstance(response, dict) or not isinstance(response.get("data"), list) or "next_cursor" not in response.get("pagination", {}):
                raise ValueError("Unexpected v2 trade envelope")
            for index, row in enumerate(response["data"], 1):
                if (row.get("proxy_wallet", "").lower() != wallet or row.get("condition_id", "").lower() not in markets
                        or not int(start.timestamp()) <= int(row.get("timestamp", 0)) < int(end.timestamp())):
                    raise ValueError("API ignored wallet, condition or time filter")
                raw.append((page, index, row))
            pages = page
            cursor = response["pagination"]["next_cursor"]
            atomic_json(query_root / "checkpoint.json", {"pages": pages, "raw_rows": len(raw), "next_cursor": cursor, "complete": not cursor})
            if not cursor:
                status = "complete"
                break
            if cursor in seen:
                raise ValueError("Repeated API cursor")
            seen.add(cursor)
        if cursor:
            reason = "Page cap reached; resumable query is incomplete"
    except (ValueError, TypeError, KeyError, RuntimeError, TimeoutError, OSError) as exc:
        reason = str(exc)
    by_condition = defaultdict(list)
    for item in raw:
        by_condition[item[2]["condition_id"].lower()].append(item)
    trades, rejected = [], []
    for condition, records in by_condition.items():
        meta = markets[condition]
        market = {"id": meta["market_id"], "conditionId": condition,
                  "local_event_id": meta["event_id"], "local_meeting_month": meta["meeting_month"],
                  "local_rate_outcome": meta["rate_outcome"]}
        accepted, bad = clean_trades(records, market, meta["tokens"])
        rejected.extend(bad)
        for row in accepted:
            row.update(source_snapshot_id=f"{config['snapshot_id']}:{digest}", source_query=digest,
                       decision_cutoff_utc=meta["decision_cutoff_utc"],
                       market_end_date_utc=meta["market_end_date_utc"])
        trades.extend(accepted)
    if rejected:
        status, reason = "incomplete", "Invalid source rows quarantined"
    atomic_json(query_root / "rejected_records.json", rejected)
    event_counts = Counter(row["event_id"] for row in trades)
    coverage = [{"wallet_address": wallet, "event_id": event,
                 "complete": status == "complete", "status": status, "reason": reason,
                 "participant_rows": event_counts[event], "query_start_utc": start.isoformat(),
                 "query_end_utc": end.isoformat(), "pages": pages, "source_query": digest,
                 "source_snapshot_id": f"{config['snapshot_id']}:{digest}",
                 "availability_basis": "retrospective_trade_timestamp_only"}
                for event in sorted({m["event_id"] for m in markets.values()})]
    return trades, coverage, rejected


def collect_history(root: Path, config: dict, cohort: list[dict], out: Path, cache: Path):
    """Collect all requested wallet histories, preserving incomplete-query status."""
    out, cache = Path(out), Path(cache)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + float(config.get("collection_budget_seconds", 3600))
    metadata = load_market_map(root, config, cache, deadline)
    wanted = set(map(str, config["history_event_ids"]))
    markets = {}
    for row in metadata:
        if row["event_id"] not in wanted:
            continue
        entry = markets.setdefault(row["condition_id"], dict(row, tokens={}))
        entry["tokens"][row["token_id"]] = row["token_outcome"].title()
    if len(markets) > 20:
        raise ValueError("Pilot supports at most twenty historical conditions per wallet query")
    if any(set(m["tokens"].values()) != {"Yes", "No"} for m in markets.values()):
        raise ValueError("Incomplete historical YES/NO mapping")
    results = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, int(config.get("workers", 4))))) as executor:
        futures = [executor.submit(_query_wallet, wallet["wallet_address"], markets, config, cache, deadline) for wallet in cohort]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 10 == 0 or len(results) == len(cohort):
                complete = sum(bool(records) and all(row["complete"] for row in records) for _, records, _ in results)
                print(f"Wallet collection: {len(results)}/{len(cohort)} finished; {complete} complete histories", flush=True)
    trades = sorted([row for accepted, _, _ in results for row in accepted], key=lambda r: (r["wallet_address"], r["timestamp_utc"], r["market_id"], r["source_page"], r["source_row"]))
    coverage = sorted([row for _, records, _ in results for row in records], key=lambda r: (r["wallet_address"], r["event_id"]))
    rejected = [row for _, _, records in results for row in records]
    atomic_json(out / "collection_report.json", {
        "snapshot_id": config["snapshot_id"], "exported_at_utc": utc_now(), "wallets_requested": len(cohort),
        "wallets_complete": len({r["wallet_address"] for r in coverage if r["complete"]}),
        "participant_rows": len(trades), "rejected_rows": len(rejected),
        "coverage_status_counts": dict(Counter(r["status"] for r in coverage)),
        "history_event_ids": sorted(wanted), "size_filter_shares": "0.01",
        "selection_cutoff_utc": instant(config["selection_cutoff_utc"]).isoformat(),
        "query_start_utc": instant(config["observation_start_utc"]).isoformat(),
        "query_end_utc_exclusive": instant(config["selection_cutoff_utc"]).isoformat(),
        "availability_basis": "retrospective_trade_timestamp_only",
        "population_scope": "June_event_pre_cutoff_eligible_wallets; not a historical all-wallet universe",
        "historical_activity_before_selection_is_descriptive_only": True,
        "api_completion_is_not_chain_completeness": True,
    })
    atomic_json(out / "rejected_records.json", rejected)
    return trades, coverage, metadata
