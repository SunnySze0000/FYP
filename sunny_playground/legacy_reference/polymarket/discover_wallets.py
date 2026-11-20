#!/usr/bin/env python3
"""Combine event activity and select a retrospective, pre-cutoff candidate cohort."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from build_meeting_index import checksums
from collect_history import atomic_json
from collect_pilot import write_csv
from decode_receipt import EXCHANGES, OLD_EXCHANGES


def bucket():
    return {"first_trade_utc":None, "last_trade_utc":None, "participant_rows":0,
            "transactions":set(), "days":Counter(), "markets":set(), "duplicates":0,
            "chain_statuses":Counter(), "notional":Decimal(0),
            "shares":defaultdict(Decimal), "notionals":defaultdict(Decimal)}


def add(target, row):
    time = row["timestamp_utc"]
    target["first_trade_utc"] = min(target["first_trade_utc"] or time,time)
    target["last_trade_utc"] = max(target["last_trade_utc"] or time,time)
    target["participant_rows"] += 1
    target["transactions"].add(row["transaction_hash"])
    target["days"][time[:10]] += 1
    target["markets"].add(row["market_id"])
    target["duplicates"] += int(row["same_fingerprint_count"]) > 1
    target["chain_statuses"][row["chain_verification"]] += 1
    amount = Decimal(row["notional_usd"])
    target["notional"] += amount
    category = row["side"].lower()+"_"+row["token_outcome"].lower()
    target["shares"][category] += Decimal(row["shares"])
    target["notionals"][category] += amount


def common(target):
    return {"first_trade_utc":target["first_trade_utc"], "last_trade_utc":target["last_trade_utc"],
            "participant_rows":target["participant_rows"], "unique_transactions":len(target["transactions"]),
            "active_days":len(target["days"]), "gross_participant_notional_usd":str(target["notional"]),
            "duplicate_candidate_rows":target["duplicates"],
            "duplicate_candidate_fraction":str(Decimal(target["duplicates"])/target["participant_rows"]),
            "chain_matched_rows":target["chain_statuses"]["matched_unique"],
            "chain_not_checked_rows":target["chain_statuses"]["not_checked"],
            "chain_issue_rows":sum(v for k,v in target["chain_statuses"].items() if k not in ("matched_unique","not_checked")),
            "max_rows_in_one_day":max(target["days"].values())}


def market_row(target, wallet, mapping):
    output = {"event_id":mapping["event_id"], "meeting_month":mapping["meeting_month"],
              "market_id":mapping["market_id"], "rate_outcome":mapping["rate_outcome"],
              "condition_id":mapping["condition_id"], "wallet_address":wallet, **common(target)}
    for category in ("buy_yes","sell_yes","buy_no","sell_no"):
        output[category+"_shares"] = str(target["shares"][category])
        output[category+"_notional_usd"] = str(target["notionals"][category])
    output["yes_trade_flow_shares"] = str(target["shares"]["buy_yes"]-target["shares"]["sell_yes"])
    output["no_trade_flow_shares"] = str(target["shares"]["buy_no"]-target["shares"]["sell_no"])
    output["trades_both_directions_same_token"] = any(target["shares"]["buy_"+t] > 0 and target["shares"]["sell_"+t] > 0 for t in ("yes","no"))
    return output


def discover(root, event_id, cutoff, candidate_count):
    meeting = root / ("event_"+event_id)
    with (meeting / "market_inventory.csv").open() as handle:
        inventory = list(csv.DictReader(handle))
    mapping = {r["market_id"]:r for r in inventory}
    full, prior, wallets = defaultdict(bucket), defaultdict(bucket), defaultdict(bucket)
    inputs, total_rows, after_cutoff = [], 0, 0
    for market_id, meta in sorted(mapping.items()):
        path = root / ("market_"+market_id) / "wallet_trades.csv.gz"
        inputs.append({"market_id":market_id, "file":path.relative_to(root).as_posix(),
                       "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
        count = 0
        with gzip.open(path,"rt",newline="") as handle:
            for row in csv.DictReader(handle):
                if row["market_id"] != market_id or row["event_id"] != event_id:
                    raise ValueError("Source row market/event differs from inventory")
                count += 1
                key = (row["wallet_address"],market_id)
                add(full[key],row)
                # Exact UTC boundary; selection never sees records at/after it.
                if datetime.fromisoformat(row["timestamp_utc"]) < cutoff:
                    add(prior[key],row)
                    add(wallets[row["wallet_address"]],row)
                else:
                    after_cutoff += 1
        if count != int(meta["participant_rows"]):
            raise ValueError("Source CSV count differs from inventory")
        total_rows += count
    if not wallets:
        raise ValueError("No records before cutoff")
    full_rows = [market_row(v,wallet,mapping[market]) for (wallet,market),v in sorted(full.items())]
    prior_rows = [market_row(v,wallet,mapping[market]) for (wallet,market),v in sorted(prior.items())]
    prior_by_wallet = defaultdict(list)
    for row in prior_rows:
        prior_by_wallet[row["wallet_address"]].append(row)
    summaries, excluded = [], Counter()
    forbidden = EXCHANGES | OLD_EXCHANGES | {"0x"+"0"*40}
    for wallet,target in sorted(wallets.items()):
        reasons = []
        if wallet in forbidden:
            reasons.append("configured_exchange_or_zero_address")
        if len(target["days"]) < 5:
            reasons.append("fewer_than_5_active_days")
        if len(target["transactions"]) < 10:
            reasons.append("fewer_than_10_transactions")
        if target["duplicates"]*20 > target["participant_rows"]:
            reasons.append("more_than_5_percent_duplicate_candidate_rows")
        base = common(target)
        if base["chain_issue_rows"]:
            reasons.append("observed_chain_reconciliation_issue")
        excluded.update(reasons)
        ids = sorted(target["markets"])
        summaries.append({"wallet_address":wallet, "event_id":event_id,
                          "selection_cutoff_utc":cutoff.isoformat(), **base,
                          "markets_traded":len(ids), "market_ids":";".join(ids),
                          "rate_outcomes":";".join(mapping[m]["rate_outcome"] for m in ids),
                          "two_sided_markets":sum(r["trades_both_directions_same_token"] for r in prior_by_wallet[wallet]),
                          "eligible":not reasons, "eligibility_notes":";".join(reasons) or "passes_exploratory_activity_filters"})
    eligible = [r for r in summaries if r["eligible"]]
    broad = sorted([r for r in eligible if r["markets_traded"]>=3],key=lambda r:(-r["markets_traded"],-r["active_days"],-r["unique_transactions"],r["wallet_address"]))
    focused = sorted([r for r in eligible if r["markets_traded"]<=2],key=lambda r:(-r["active_days"],-r["unique_transactions"],r["wallet_address"]))
    candidates = []
    for group,pool,limit in [("broad_outcome_participation",broad,(candidate_count+1)//2),
                             ("focused_outcome_participation",focused,candidate_count//2)]:
        for rank,row in enumerate(pool[:limit],1):
            candidates.append({"candidate_number":len(candidates)+1, "selection_group":group,
                               "group_rank":rank, **row,
                               "selection_reason":"3+ markets; ranked by markets, active days, transactions" if group.startswith("broad") else "1-2 markets; ranked by active days, transactions",
                               "wallet_explorer_url":"https://polygonscan.com/address/"+row["wallet_address"]})
    if len(candidates)!=candidate_count:
        raise ValueError("Insufficient eligible wallets in one selection group; no cohort fabricated")
    selected = {r["wallet_address"] for r in candidates}
    selected_rows = [r for r in prior_rows if r["wallet_address"] in selected]
    out = meeting / "wallet_discovery"
    out.mkdir(exist_ok=True)
    for filename,rows in [("wallet_market_activity.csv",full_rows),("wallet_summary_pre_cutoff.csv",summaries),
                          ("candidate_wallets.csv",candidates),("candidate_outcome_activity.csv",selected_rows)]:
        write_csv(out/filename,list(rows[0]),rows)
    report = {"event_id":event_id, "selection_cutoff_utc":cutoff.isoformat(), "input_files":inputs,
              "full_history_participant_rows":total_rows, "full_history_wallet_market_pairs":len(full_rows),
              "full_history_distinct_wallets":len({key[0] for key in full}),
              "pre_cutoff_participant_rows":total_rows-after_cutoff, "excluded_at_or_after_cutoff_rows":after_cutoff,
              "pre_cutoff_distinct_wallets":len(summaries), "eligible_wallets":len(eligible),
              "exclusion_reason_counts_nonexclusive":dict(excluded), "eligible_broad_wallets":len(broad),
              "eligible_focused_wallets":len(focused), "candidate_wallets":len(candidates),
              "candidate_wallet_market_pairs":len(selected_rows),
              "selection_rules":{"minimum_active_utc_days":5,"minimum_unique_transactions":10,
                                 "maximum_duplicate_candidate_fraction":"0.05","exclude_configured_exchanges_and_zero_address":True,
                                 "exclude_observed_chain_reconciliation_issues":True,
                                 "broad_group":"3+ markets: markets descending, active days descending, transactions descending, address ascending",
                                 "focused_group":"1-2 markets: active days descending, transactions descending, address ascending"},
              "limitations":["Candidates represent observable activity, not proven skill, profit or a predictive ranking.",
                             "One meeting is one independent event even when a wallet trades multiple outcome markets.",
                             "Cutoff is based on historical trade timestamps in retrospectively collected API records, not a contemporaneously archived snapshot.",
                             "Duplicate candidates are retained; the fraction filter is exploratory and does not establish invalidity.",
                             "Chain-check coverage is sparse and retrospective; it is reported but not used to prefer wallets.",
                             "Trade flow is not full holdings; position operations, transfers and starting balances are not reconstructed."]}
    atomic_json(out/"report.json",report)
    preview = "\n".join(f"| {r['candidate_number']} | `{r['wallet_address'][:10]}…{r['wallet_address'][-4:]}` | {'Broad' if r['selection_group'].startswith('broad') else 'Focused'} | {r['markets_traded']} | {r['active_days']} | {r['unique_transactions']:,} | {r['two_sided_markets']} |" for r in candidates)
    (out/"README.md").write_text(f"""# Wallet activity and candidate discovery

Event `{event_id}`: five June Fed outcome markets. [Meeting overview](../README.md).

| File | Row meaning / scope |
|---|---|
| `wallet_market_activity.csv` | {len(full_rows):,} wallet/market pairs over the full collected history; shows which policy outcomes each address traded |
| `wallet_summary_pre_cutoff.csv` | {len(summaries):,} wallets with activity strictly before `{cutoff.isoformat()}`; selection features and eligibility for all of them |
| `candidate_wallets.csv` | {len(candidates)} candidates: {(candidate_count+1)//2} broad and {candidate_count//2} focused |
| `candidate_outcome_activity.csv` | {len(selected_rows)} candidate/market pairs using only pre-cutoff records |
| `report.json` | Input hashes, window counts, filters, ranking rules and limitations |
| `SHA256SUMS` | Integrity checks for these discovery files |

## How selection works

All selection features use trade timestamps **strictly before {cutoff.isoformat()}** (default:
before May 31 UTC, so the last included calendar day is May 30). Records at/after the cutoff
appear only in the full-history activity table. Full-history activity is descriptive and is not
an input to the shortlist. We use {total_rows-after_cutoff:,} pre-cutoff records and exclude {after_cutoff:,}
later records from selection. No final outcome, realized PnL, profitability or future trading is used.

Require at least 5 active UTC days, 10 distinct transactions, no more than 5% of records flagged
as duplicate candidates, no observed reconciliation issue in pre-cutoff records, and an address
other than the configured exchange contracts or zero address. {len(eligible):,} addresses qualify.
These are exploratory usability filters, not statistically validated measures of wallet quality.

The broad group has 3+ outcome markets and is ranked by market count, active days, then transaction
count. The focused group has 1-2 markets and is ranked by active days, then transaction count.
Address ascending breaks ties deterministically. Gross notional and sampled chain-check coverage
are reported but do not rank wallets. `candidate_number` is display order, not a skill score.

| Candidate | Address (shortened) | Group | Markets | Active days | Transactions | Two-sided markets |
|---|---|---|---:|---:|---:|---:|
{preview}

## CSV fields and units

The wallet/market tables contain `event_id`, `meeting_month`, `market_id`, `rate_outcome`,
`condition_id`, `wallet_address`; first/last observed UTC trades; `participant_rows`,
`unique_transactions`, `active_days`, `gross_participant_notional_usd`,
`duplicate_candidate_rows`, `duplicate_candidate_fraction`, `chain_matched_rows`,
`chain_not_checked_rows`, `chain_issue_rows`, and `max_rows_in_one_day`.
Transaction/day counts are set unions within the row's scope. Duplicate rows remain counted.

For each category (`buy_yes`, `sell_yes`, `buy_no`, `sell_no`), `_shares` and `_notional_usd`
columns sum gross shares and collateral notional separately. `yes_trade_flow_shares` and
`no_trade_flow_shares` are bought minus sold for that particular token/question, not holdings.
`trades_both_directions_same_token` means BUY and SELL were observed for YES or for NO;
it does not establish arbitrage, market making or manipulation. [Source units](../../SCHEMA.md).

Wallet summaries union transactions and UTC days across markets. `markets_traded`, `market_ids`
and `rate_outcomes` identify the observed policy questions; lists use semicolons. `two_sided_markets`
counts markets with both trade directions for at least one token. `selection_cutoff_utc`,
`eligible`, and `eligibility_notes` make the decision auditable. Exclusion counts in the report
are nonexclusive because a wallet may fail several filters. `chain_issue_rows` counts sampled
records whose status is neither `matched_unique` nor `not_checked`.

Candidates add `candidate_number`, `selection_group`, `group_rank`, `selection_reason` and a
public `wallet_explorer_url`. No real-world identities or wallet-performance scores are inferred.
Use full addresses from the CSV; display addresses above are abbreviated.

## Interpretation and reproduction

These addresses are **candidates for historical investigation**, not proven smart wallets.
Trading multiple questions within June still supplies only one independent meeting. Sustained
activity and two-sided trading can reflect several strategies; high activity is not evidence of skill.
Next, collect earlier resolved-meeting histories and assess sample size before designing scores.
Our October collection is retrospective: this cutoff removes future trade timestamps, but it
does not prove these exact API records were available at the historical cutoff.

From the repository root, no network or API key is needed:

```sh
python3 -B scripts/polymarket/discover_wallets.py
```

`--cutoff` requires an explicit timezone; `--candidate-count` allows 10 through 20.
Rerunning replaces the discovery files and refreshes their checksums and the parent meeting
checksums. Source per-market exports are read-only. All decimal totals use decimal arithmetic;
participant notional is not market volume, and trade flow excludes position lifecycle operations.
""")
    checksums(out)
    checksums(meeting)
    print(json.dumps({k:v for k,v in report.items() if k not in ("input_files","limitations","selection_rules")},indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root",type=Path,default=Path("datasets/polymarket"))
    parser.add_argument("--event-id",default="101772")
    parser.add_argument("--cutoff",default="2026-05-31T00:00:00+00:00")
    parser.add_argument("--candidate-count",type=int,default=20)
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff.replace("Z","+00:00"))
    if cutoff.tzinfo is None or not 10 <= args.candidate_count <= 20:
        parser.error("cutoff must include timezone; candidate-count must be 10..20")
    discover(args.dataset_root,args.event_id,cutoff.astimezone(timezone.utc),args.candidate_count)
