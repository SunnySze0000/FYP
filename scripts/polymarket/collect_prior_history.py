#!/usr/bin/env python3
"""Collect shortlisted wallets' trades in earlier team Fed markets; no skill scoring."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from build_meeting_index import checksums
from collect_history import atomic_json
from collect_pilot import array, clean_trades, fetch, utc_now, write_csv


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def prepare(args, cutoff):
    with args.candidates.open() as handle:
        candidates = list(csv.DictReader(handle))
    if not candidates or len({r["wallet_address"] for r in candidates})!=len(candidates):
        raise ValueError("Missing or duplicate candidates")
    if any(instant(r["selection_cutoff_utc"])!=cutoff for r in candidates):
        raise ValueError("Candidate selection cutoff differs from history cutoff")
    with args.input.open() as handle:
        local = defaultdict(list)
        for row in csv.DictReader(handle):
            if row["meeting_month"] < cutoff.strftime("%Y-%m"):
                local[row["market_id"]].append(row)
    raw_dir = args.raw / "metadata"
    raw_dir.mkdir(parents=True,exist_ok=True)
    markets,metadata = {},[]
    for market_id,rows in sorted(local.items()):
        for field in ("event_id","meeting_month","outcome","final_outcome"):
            if len({r[field] for r in rows})!=1:
                raise ValueError("Inconsistent local market labels")
        path = raw_dir / (market_id+".json")
        if not path.exists():
            atomic_json(path,{"collected_at_utc":utc_now(),"response":fetch("https://gamma-api.polymarket.com/markets/"+market_id)})
        envelope = json.loads(path.read_text())
        market = envelope["response"]
        if str(market["id"])!=market_id:
            raise ValueError("Gamma market mismatch")
        closed_at = instant(market["closedTime"]) if market.get("closedTime") else None
        if not market.get("closed") or not closed_at or closed_at>=cutoff or market.get("umaResolutionStatus")!="resolved":
            raise ValueError("An earlier market lacks pre-cutoff closure/current resolution evidence")
        tokens,labels = array(market["clobTokenIds"]),array(market["outcomes"])
        prices = [Decimal(str(p)) for p in array(market["outcomePrices"])]
        if len(tokens)!=2 or set(labels)!={"Yes","No"} or sorted(prices)!=[Decimal(0),Decimal(1)]:
            raise ValueError("Unsupported token mapping or nonfinal current prices")
        yes_result = int(prices[labels.index("Yes")])
        if yes_result!=int(rows[0]["final_outcome"]):
            raise ValueError("Team outcome label disagrees with current Gamma outcome")
        end = instant(market["endDate"])
        decision_cutoff = end-timedelta(days=1)
        market.update(local_event_id=rows[0]["event_id"],local_meeting_month=rows[0]["meeting_month"],local_rate_outcome=rows[0]["outcome"])
        record = {"event_id":rows[0]["event_id"],"meeting_month":rows[0]["meeting_month"],
                  "market_id":market_id,"rate_outcome":rows[0]["outcome"],"condition_id":market["conditionId"].lower(),
                  "market_end_date_utc":end.isoformat(),"market_closed_at_utc":closed_at.isoformat(),
                  "decision_cutoff_utc":decision_cutoff.isoformat(),"closed_before_selection_cutoff":True,
                  "current_resolution_status":market["umaResolutionStatus"],"current_final_yes_outcome":yes_result,
                  "team_final_yes_outcome":rows[0]["final_outcome"],"original_resolution_time_verified":False,
                  "metadata_collected_at_utc":envelope["collected_at_utc"]}
        if record["condition_id"] in markets:
            raise ValueError("Condition shared unexpectedly across team markets")
        markets[record["condition_id"]] = (market,dict(zip(map(str,tokens),labels)),record)
        metadata.extend({**record,"token_id":str(token),"token_outcome":label.upper()} for token,label in zip(tokens,labels))
    for event in {r["event_id"] for r in metadata}:
        event_rows = [r for r in metadata if r["event_id"]==event]
        if len({r["decision_cutoff_utc"] for r in event_rows})!=1 or sum(r["current_final_yes_outcome"] for r in event_rows if r["token_outcome"]=="YES")!=1:
            raise ValueError("Inconsistent event cutoffs or winning outcome count")
    print(f"Metadata verified: {len(markets)} markets, {len({r['event_id'] for r in metadata})} earlier meetings",flush=True)
    return candidates,markets,metadata


def collect_wallet(candidate,markets,args,cutoff):
    wallet = candidate["wallet_address"]
    conditions = sorted(markets)
    queries,accepted,rejected = [],[],[]
    for group_index,offset in enumerate(range(0,len(conditions),20),1):
        group = conditions[offset:offset+20]
        root = args.raw / "wallets" / wallet / f"conditions_{group_index}"
        root.mkdir(parents=True,exist_ok=True)
        params = {"user":wallet,"condition":",".join(group),"taker_only":"false","filter_type":"TOKENS",
                  "filter_amount":"0.01","limit":1000,"start":1,"end":int(cutoff.timestamp())-1}
        config_path = root / "config.json"
        if config_path.exists() and json.loads(config_path.read_text())!=params:
            raise ValueError("Saved wallet query configuration differs")
        atomic_json(config_path,params)
        cursor,seen,pages,count = None,set(),[],0
        by_condition = defaultdict(list)
        for page in range(1,args.max_pages+1):
            path = root / f"page_{page:05d}.json"
            if path.exists():
                envelope = json.loads(path.read_text())
                if envelope["request_cursor"]!=cursor:
                    raise ValueError("Saved wallet cursor chain differs")
            else:
                request = dict(params)
                if cursor:
                    request["cursor"] = cursor
                response = fetch("https://data-api.polymarket.com/v2/trades?"+urlencode(request))
                if not isinstance(response.get("data"),list) or "next_cursor" not in response.get("pagination",{}):
                    raise ValueError("Unexpected trade page")
                envelope = {"collected_at_utc":utc_now(),"request_cursor":cursor,"response":response}
                atomic_json(path,envelope)
            response = envelope["response"]
            for index,row in enumerate(response["data"],1):
                if row["proxy_wallet"].lower()!=wallet or row["condition_id"].lower() not in group or not 1<=int(row["timestamp"])<int(cutoff.timestamp()):
                    raise ValueError("API ignored wallet/condition/time filter; row not accepted")
                by_condition[row["condition_id"].lower()].append((page,index,row))
            count += len(response["data"])
            pages.append({"page":page,"rows":len(response["data"]),"collected_at_utc":envelope["collected_at_utc"]})
            cursor = response["pagination"]["next_cursor"]
            atomic_json(root/"checkpoint.json",{"pages":len(pages),"raw_rows":count,"next_cursor":cursor,"exhausted_api_cursor":not cursor})
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("Repeated wallet cursor")
            seen.add(cursor)
        if cursor:
            raise ValueError("Wallet page cap reached; increase --max-pages to resume")
        for condition,raw in by_condition.items():
            market,mapping,meta = markets[condition]
            clean,bad = clean_trades(raw,market,mapping)
            for row in clean:
                accepted.append({"source_query":f"conditions_{group_index}",**row,
                                 "market_end_date_utc":meta["market_end_date_utc"],
                                 "market_closed_at_utc":meta["market_closed_at_utc"],
                                 "decision_cutoff_utc":meta["decision_cutoff_utc"],
                                 "before_decision_cutoff":instant(row["timestamp_utc"])<instant(meta["decision_cutoff_utc"]),
                                 "before_market_close":instant(row["timestamp_utc"])<instant(meta["market_closed_at_utc"])})
            rejected.extend({"wallet_address":wallet,"source_query":f"conditions_{group_index}",**r} for r in bad)
        queries.append({"wallet_address":wallet,"source_query":f"conditions_{group_index}","conditions":group,
                        "pages":pages,"raw_rows":count,"exhausted_api_cursor":True})
    print(f"Wallet {candidate['candidate_number']}: {len(accepted)} accepted earlier-market rows, {len(rejected)} rejected",flush=True)
    return accepted,rejected,queries


def build(args):
    cutoff = instant(args.cutoff)
    candidates,markets,metadata = prepare(args,cutoff)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(lambda r:collect_wallet(r,markets,args,cutoff),candidates))
    trades = sorted([r for clean,_,_ in results for r in clean],key=lambda r:(r["wallet_address"],r["timestamp_utc"],r["market_id"],r["source_query"],r["source_page"],r["source_row"]))
    rejected = [r for _,bad,_ in results for r in bad]
    queries = [r for _,_,queries in results for r in queries]
    event_meta = {r["event_id"]:r for r in metadata}
    groups = defaultdict(list)
    for row in trades:
        groups[(row["wallet_address"],row["event_id"])].append(row)
    participation,summaries = [],[]
    for candidate in candidates:
        wallet = candidate["wallet_address"]
        wallet_rows = []
        for event,meta in sorted(event_meta.items(),key=lambda x:x[1]["meeting_month"]):
            rows = groups[(wallet,event)]
            early = [r for r in rows if r["before_decision_cutoff"]]
            duplicates = sum(int(r["same_fingerprint_count"])>1 for r in early)
            participant = {"candidate_number":candidate["candidate_number"],"wallet_address":wallet,
                           "selection_group":candidate["selection_group"],"event_id":event,"meeting_month":meta["meeting_month"],
                           "decision_cutoff_utc":meta["decision_cutoff_utc"],"served_trade_rows":len(rows),
                           "pre_decision_trade_rows":len(early),"pre_decision_unique_transactions":len({r["transaction_hash"] for r in early}),
                           "pre_decision_active_days":len({r["timestamp_utc"][:10] for r in early}),
                           "pre_decision_markets_traded":len({r["market_id"] for r in early}),
                           "pre_decision_gross_participant_notional_usd":str(sum((Decimal(r["notional_usd"]) for r in early),Decimal(0))),
                           "pre_decision_duplicate_candidate_rows":duplicates,
                           "first_observed_trade_utc":min((r["timestamp_utc"] for r in rows),default=""),
                           "last_observed_trade_utc":max((r["timestamp_utc"] for r in rows),default=""),
                           "has_pre_decision_activity":bool(early),"current_resolution_status":"resolved",
                           "closed_before_selection_cutoff":True,"original_resolution_time_verified":False,
                           "exhausted_wallet_api_cursors":True}
            participation.append(participant)
            wallet_rows.append(participant)
        prior_events = [r for r in wallet_rows if r["has_pre_decision_activity"]]
        count = len(prior_events)
        summaries.append({"candidate_number":candidate["candidate_number"],"wallet_address":wallet,
                          "selection_group":candidate["selection_group"],"selection_cutoff_utc":cutoff.isoformat(),
                          "queried_prior_meetings":len(event_meta),"meetings_with_any_served_trade":sum(r["served_trade_rows"]>0 for r in wallet_rows),
                          "meetings_with_pre_decision_activity":count,
                          "pre_decision_meeting_months":";".join(r["meeting_month"] for r in prior_events),
                          "served_prior_trade_rows":sum(r["served_trade_rows"] for r in wallet_rows),
                          "pre_decision_trade_rows":sum(r["pre_decision_trade_rows"] for r in wallet_rows),
                          "history_review_band":"3plus_prior_meetings" if count>=3 else "1to2_prior_meetings" if count else "no_observed_pre_decision_history",
                          "verified_original_resolution_timestamps":0,"skill_score_available":False})
    out = args.output
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"prior_market_tokens.csv",list(metadata[0]),metadata)
    write_csv(out/"candidate_meeting_activity.csv",list(participation[0]),participation)
    write_csv(out/"candidate_history_summary.csv",list(summaries[0]),summaries)
    months = sorted({r["meeting_month"] for r in participation})
    cells = {(r["wallet_address"],r["meeting_month"]):r["pre_decision_trade_rows"] for r in participation}
    matrix = [{"candidate_number":r["candidate_number"],"wallet_address":r["wallet_address"],
               "selection_group":r["selection_group"],"pre_decision_meetings":r["meetings_with_pre_decision_activity"],
               **{"rows_"+month.replace("-","_"):cells[(r["wallet_address"],month)] for month in months}}
              for r in summaries]
    write_csv(out/"candidate_meeting_matrix.csv",list(matrix[0]),matrix)
    temporary = args.raw/"prior_wallet_trades.csv"
    fields = list(trades[0]) if trades else ["wallet_address","market_id","timestamp_utc"]
    write_csv(temporary,fields,trades)
    with temporary.open("rb") as source,(out/"prior_wallet_trades.csv.gz").open("wb") as target:
        with gzip.GzipFile(filename="",fileobj=target,mode="wb",mtime=0) as compressed:
            import shutil
            shutil.copyfileobj(source,compressed)
    atomic_json(args.raw/"rejected_records.json",rejected)
    atomic_json(out/"coverage.json",{"queries":queries,"raw_rows":sum(r["raw_rows"] for r in queries),"clean_rows":len(trades),"rejected_rows":len(rejected),"all_wallet_api_cursors_exhausted":True})
    report = {"exported_at_utc":utc_now(),"selection_cutoff_utc":cutoff.isoformat(),"candidate_count":len(candidates),
              "prior_meetings":len(event_meta),"prior_markets":len(markets),"accepted_prior_trade_rows":len(trades),
              "rejected_rows":len(rejected),"pre_decision_trade_rows":sum(r["before_decision_cutoff"] for r in trades),
              "candidate_meeting_pairs_including_zero_rows":len(participation),
              "prior_meeting_count_distribution":dict(sorted(Counter(r["meetings_with_pre_decision_activity"] for r in summaries).items())),
              "candidates_with_3plus_prior_meetings":sum(r["meetings_with_pre_decision_activity"]>=3 for r in summaries),
              "candidate_source_sha256":hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
              "query_settings":{"taker_only":False,"filter_type":"TOKENS","filter_amount":"0.01","user_start":1,"user_end_inclusive":int(cutoff.timestamp())-1,"maximum_conditions_per_query":20},
              "limitations":["Current Gamma resolution status and pre-cutoff closedTime are verified, but original resolution timestamps are not. Closure is not the same as resolution.",
                             "Historical API records and labels were collected retrospectively; contemporaneous availability is not established.",
                             "Decision cutoff is one day before Gamma endDate, not the exact FOMC announcement time. Later trades do not count as pre-decision participation.",
                             "Only seven prior meetings in the team's existing universe are queried; a zero row does not establish a wallet's lifetime inactivity.",
                             "Trade presence establishes data feasibility, not forecasting skill, profit or holdings. No skill score is produced.",
                             "API size floor applies; duplicate candidates remain preserved. These new records are not independently chain-verified."]}
    atomic_json(out/"report.json",report)
    table="\n".join(f"| {r['candidate_number']} | `{r['wallet_address'][:10]}…{r['wallet_address'][-4:]}` | {r['meetings_with_pre_decision_activity']} | {r['pre_decision_trade_rows']:,} | {r['history_review_band']} |" for r in summaries)
    matrix_header = "| Candidate | " + " | ".join(months) + " |"
    matrix_separator = "|---|" + "---|"*len(months)
    matrix_body = "\n".join("| "+str(r["candidate_number"])+" | "+" | ".join("✓" if cells[(r["wallet_address"],month)] else "—" for month in months)+" |" for r in summaries)
    (out/"README.md").write_text(f"""# Candidate wallets: earlier Fed meeting history

This checks the existing 20-wallet shortlist against seven earlier team meetings: July,
September, October and December 2025; January, March and April 2026. [Candidate guide](../wallet_discovery/README.md).
Source: Gamma metadata and Polymarket Data API v2, with wallet+condition filters and UTC
trade timestamps strictly before `{cutoff.isoformat()}`. All wallet query cursors are exhausted.

Collected **{len(trades):,} accepted records** across 28 earlier markets. Of these,
**{report['pre_decision_trade_rows']:,}** precede the per-meeting analysis cutoff.
**{report['candidates_with_3plus_prior_meetings']} candidates** have observed pre-decision activity
in at least three earlier meetings. This is a history-review grouping, not a validated skill threshold.

| Candidate | Address (shortened) | Earlier meetings before decision cutoff | Pre-decision records | History review band |
|---|---|---:|---:|---|
{table}

## Which earlier meetings have records?

✓ means at least one served trade before the declared decision cutoff; — means none observed.
This marks participation only. Exact trade counts are in `candidate_meeting_matrix.csv`.

{matrix_header}
{matrix_separator}
{matrix_body}

## Files and row meanings

- `candidate_history_summary.csv`: one row per candidate. `queried_prior_meetings` is the search
  universe size; `meetings_with_any_served_trade` includes late trades, while
  `meetings_with_pre_decision_activity` counts independent meetings with at least one earlier
  trade. `pre_decision_meeting_months` is a semicolon list. Trade-row totals include retained
  duplicate candidates. `history_review_band` groups 0, 1-2, or 3+ observed meetings; it is not a
  skill score. `verified_original_resolution_timestamps=0`, `skill_score_available=False`.
- `candidate_meeting_activity.csv`: 20 × 7 = 140 candidate/meeting rows, including explicit zeros.
  Counts distinct transactions, days and markets within the pre-decision window, gross participant
  notional and duplicate-candidate rows; also records first/last served trade times, closure and
  current-resolution evidence flags. Counts across multiple outcome markets are one meeting.
- `candidate_meeting_matrix.csv`: 20 rows, with candidate/address/group and `pre_decision_meetings`;
  each `rows_YYYY_MM` column is the number of pre-decision participant records for that meeting.
- `prior_wallet_trades.csv.gz`: cleaned candidate participant records using the [trade schema](../../SCHEMA.md).
  Adds `source_query`, Gamma `market_end_date_utc`, `market_closed_at_utc`, `decision_cutoff_utc`,
  `before_decision_cutoff`, and `before_market_close`. Snapshot keys are wallet + source_query +
  source_page + source_row. All `chain_verification` values are `not_checked`.
- `prior_market_tokens.csv`: 56 token rows linking 28 markets to seven events, YES/NO labels,
  end/closure/decision times, current final YES outcomes and team labels. Final labels agree;
  they are audit metadata, not candidate-selection features. Metadata acquisition times are retained.
- `coverage.json`: original query condition lists, per-page timestamps/counts, raw/accepted/rejected
  totals and cursor exhaustion for all 40 wallet/condition-group queries.
- `report.json`: counts, source shortlist hash, filters, meeting-count distribution and limitations.
- `SHA256SUMS`: integrity checks for these outputs.

## Evidence boundaries

Gamma currently reports each market resolved with final prices of 0/1. Its `closedTime` precedes
the May 31 selection cutoff, but it does not supply an independently verified original resolution
timestamp here. We therefore call these **earlier closed meetings with current resolved labels**,
not proof that every resolution was finalized or every API record available at that historical time.

Participation before a decision cutoff is a more useful starting point than simply trading a
winning token afterward. We set that cutoff to **Gamma endDate minus 24 hours** for each event,
validate it is consistent across its markets, and exclude trades at/after it from the history counts.
This is a declared conservative convention, not an exact announcement-time reconstruction.
Presence in several prior meetings makes case-study investigation feasible; it does not prove
correct decisions, independence of addresses, profit or skill. Trade-flow records do not reconstruct
holdings or account for transfers, splits, merges and redemptions.

Zero means no served records for these queried markets under these filters. It does not mean the
wallet never traded other markets or had no on-chain activity. The 0.01-share floor and API coverage
still apply. New prior records have not been Polygon-verified. Raw metadata, responses, rejected rows
and resume checkpoints remain in ignored `tmp/polymarket/prior_candidate_history/`.

## Reproduce

From the repository root, no Polymarket API key is required:

```sh
python3 -B scripts/polymarket/collect_prior_history.py
```

Use `--workers` to control concurrent wallets; `--max-pages` caps pages per condition group.
Saved metadata/query pages are reused and validated on reruns. Use another `--raw` directory
for a fresh acquisition; exports are replaced and checksums refreshed. The script does not
change the shortlist or the original five June datasets, and produces no performance score.
""")
    checksums(out)
    checksums(out.parent)
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=Path("datasets/forward_probabilities.csv"))
    parser.add_argument("--candidates",type=Path,default=Path("datasets/polymarket/event_101772/wallet_discovery/candidate_wallets.csv"))
    parser.add_argument("--raw",type=Path,default=Path("tmp/polymarket/prior_candidate_history"))
    parser.add_argument("--output",type=Path,default=Path("datasets/polymarket/event_101772/prior_history"))
    parser.add_argument("--cutoff",default="2026-05-31T00:00:00+00:00")
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--max-pages",type=int,default=1000)
    args=parser.parse_args()
    if datetime.fromisoformat(args.cutoff.replace("Z","+00:00")).tzinfo is None or not 1<=args.workers<=8 or args.max_pages<1:
        parser.error("Timezone-aware cutoff, workers 1..8, and positive max-pages required")
    build(args)
