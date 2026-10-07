#!/usr/bin/env python3
"""Offline, retrospective flow diagnostics; never infer holdings or wallet forecasts."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, getcontext
from pathlib import Path

from build_meeting_index import checksums
from collect_pilot import write_csv
from collect_prior_history import instant

getcontext().prec = 40
ZERO = Decimal(0)
WINDOWS = (1, 7, 30)
CANDIDATES = (3, 6, 7, 12)


def read_csv(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def main(args):
    prior = args.event_root / 'prior_history'
    selected = [r for r in read_csv(prior / 'candidate_history_summary.csv')
                if int(r['candidate_number']) in CANDIDATES]
    if len(selected) != 4 or any(int(r['meetings_with_pre_decision_activity']) != 7 for r in selected):
        raise ValueError('Expected the frozen four wallets with seven prior meetings')
    wallets = {r['wallet_address']: r for r in selected}
    markets = {r['market_id']: r for r in read_csv(prior / 'prior_market_tokens.csv')
               if r['token_outcome'] == 'YES'}
    events = defaultdict(list)
    for r in markets.values():
        events[r['event_id']].append(r)
    if len(events) != 7 or any(len(rs) != 4 for rs in events.values()):
        raise ValueError('Expected seven independent four-outcome meetings')
    baseline_rows = defaultdict(list)
    for row in read_csv(args.probabilities):
        if row['market_id'] in markets:
            baseline_rows[row['market_id']].append(row)
    baselines = {}
    for market_id, market in markets.items():
        cutoff = instant(market['decision_cutoff_utc'])
        available = [r for r in baseline_rows[market_id] if instant(r['date']) <= cutoff]
        if not available:
            raise ValueError('Missing pre-cutoff market baseline')
        row = max(available, key=lambda r: instant(r['date']))
        age = (cutoff - instant(row['date'])).total_seconds() / 3600
        p = Decimal(row['market_probability'])
        if not 0 <= p <= 1 or age > 24:
            raise ValueError('Invalid or stale market baseline')
        if int(row['final_outcome']) != int(market['current_final_yes_outcome']):
            raise ValueError('Outcome label mismatch')
        baselines[market_id] = (row['date'], p, age)

    def empty():
        return {'rows': 0, 'duplicate_rows': 0, 'transactions': set(), 'days': set(),
                'first': '', 'last': '', **{k: ZERO for k in
                ('BUY_YES', 'SELL_YES', 'BUY_NO', 'SELL_NO')}}
    groups = defaultdict(empty)
    source_rows = 0
    with gzip.open(prior / 'prior_wallet_trades.csv.gz', 'rt') as handle:
        for r in csv.DictReader(handle):
            if r['wallet_address'] not in wallets:
                continue
            source_rows += 1
            market = markets[r['market_id']]
            cutoff, timestamp = instant(market['decision_cutoff_utc']), instant(r['timestamp_utc'])
            if r['event_id'] != market['event_id'] or r['wallet_address'] not in wallets:
                raise ValueError('Unexpected market/wallet mapping')
            action = r['side'] + '_' + r['token_outcome']
            if action not in ('BUY_YES', 'SELL_YES', 'BUY_NO', 'SELL_NO'):
                raise ValueError('Unsupported action')
            shares = Decimal(r['shares'])
            sign = 1 if action in ('BUY_YES', 'SELL_NO') else -1
            if shares <= 0 or Decimal(r['signed_yes_shares']) != sign * shares:
                raise ValueError('Invalid shares or directional sign')
            for window in WINDOWS:
                if not cutoff - timedelta(days=window) <= timestamp < cutoff:
                    continue
                g = groups[(r['wallet_address'], r['market_id'], window)]
                g['rows'] += 1
                g['duplicate_rows'] += int(r['same_fingerprint_count']) > 1
                g['transactions'].add(r['transaction_hash'])
                g['days'].add(timestamp.date().isoformat())
                g[action] += shares
                g['first'] = min(g['first'], r['timestamp_utc']) if g['first'] else r['timestamp_utc']
                g['last'] = max(g['last'], r['timestamp_utc'])

    details, decisions = [], []
    for wallet, candidate in sorted(wallets.items(), key=lambda x: int(x[1]['candidate_number'])):
        for event_id, em in sorted(events.items(), key=lambda x: x[1][0]['meeting_month']):
            for window in WINDOWS:
                rows, txs, days = [], set(), set()
                for m in sorted(em, key=lambda r: r['market_id']):
                    g = groups[(wallet, m['market_id'], window)]
                    txs.update(g['transactions']); days.update(g['days'])
                    gross = sum((g[k] for k in ('BUY_YES','SELL_YES','BUY_NO','SELL_NO')), ZERO)
                    direction = g['BUY_YES'] - g['SELL_YES'] + g['SELL_NO'] - g['BUY_NO']
                    quote_time, p, age = baselines[m['market_id']]
                    row = {'candidate_number': candidate['candidate_number'], 'wallet_address': wallet,
                           'event_id': event_id, 'meeting_month': m['meeting_month'],
                           'decision_cutoff_utc': m['decision_cutoff_utc'], 'window_days': window,
                           'market_id': m['market_id'], 'rate_outcome': m['rate_outcome'],
                           'participant_rows': g['rows'], 'unique_transactions': len(g['transactions']),
                           'active_days': len(g['days']), 'first_trade_utc': g['first'], 'last_trade_utc': g['last'],
                           'duplicate_candidate_rows': g['duplicate_rows'],
                           **{k.lower() + '_shares': g[k] for k in ('BUY_YES','SELL_YES','BUY_NO','SELL_NO')},
                           'gross_token_shares': gross, 'net_yes_directional_flow_shares': direction,
                           'both_directions_observed': g['BUY_YES'] + g['SELL_NO'] > 0 and g['SELL_YES'] + g['BUY_NO'] > 0,
                           'baseline_timestamp_utc': instant(quote_time).isoformat(), 'baseline_age_hours': age,
                           'baseline_yes_probability': p, 'final_yes_outcome': m['current_final_yes_outcome'],
                           'diagnostic_numerator': direction * (Decimal(m['current_final_yes_outcome']) - p),
                           'chain_verification': 'not_checked'}
                    details.append(row); rows.append(row)
                norm = sum((abs(r['net_yes_directional_flow_shares']) for r in rows), ZERO)
                gross = sum((r['gross_token_shares'] for r in rows), ZERO)
                count = sum(r['participant_rows'] for r in rows)
                dup = sum(r['duplicate_candidate_rows'] for r in rows)
                status = ('no_window_activity' if not count else 'zero_net_flow' if not norm
                          else 'duplicate_fraction_over_5pct' if Decimal(dup) / count > Decimal('.05') else 'scored')
                positive = [r for r in rows if r['net_yes_directional_flow_shares'] > 0]
                negative = [r for r in rows if r['net_yes_directional_flow_shares'] < 0]
                def strongest(rs):
                    if not rs: return ''
                    strength = max(abs(r['net_yes_directional_flow_shares']) for r in rs)
                    return ';'.join(r['rate_outcome'] for r in rs if abs(r['net_yes_directional_flow_shares']) == strength)
                decisions.append({'candidate_number': candidate['candidate_number'], 'wallet_address': wallet,
                    'event_id': event_id, 'meeting_month': em[0]['meeting_month'],
                    'decision_cutoff_utc': em[0]['decision_cutoff_utc'], 'window_days': window,
                    'participant_rows': count, 'unique_transactions': len(txs), 'active_days': len(days),
                    'markets_with_activity': sum(r['participant_rows'] > 0 for r in rows),
                    'markets_with_both_directions': sum(r['both_directions_observed'] for r in rows),
                    'duplicate_candidate_rows': dup, 'gross_token_shares': gross, 'absolute_net_flow_shares': norm,
                    'netting_ratio': norm / gross if gross else '',
                    'strongest_positive_flow_outcome': strongest(positive),
                    'strongest_negative_flow_outcome': strongest(negative),
                    'actual_rate_outcome': next(r['rate_outcome'] for r in rows if r['final_yes_outcome'] == '1'),
                    'baseline_probability_sum': sum((r['baseline_yes_probability'] for r in rows), ZERO),
                    'flow_alignment_score': sum((r['diagnostic_numerator'] for r in rows), ZERO) / gross if status == 'scored' else '',
                    'status': status, 'wallet_forecast_available': False, 'wallet_pnl_available': False})
    summaries = []
    for candidate in sorted(selected, key=lambda r: int(r['candidate_number'])):
        for window in WINDOWS:
            rs = [r for r in decisions if r['wallet_address'] == candidate['wallet_address'] and r['window_days'] == window]
            scores = [r['flow_alignment_score'] for r in rs if r['status'] == 'scored']
            summaries.append({'candidate_number': candidate['candidate_number'], 'wallet_address': candidate['wallet_address'],
                'window_days': window, 'total_meetings': len(rs), 'scored_meetings': len(scores),
                'abstained_meetings': len(rs) - len(scores), 'positive_score_meetings': sum(s > 0 for s in scores),
                'mean_flow_alignment_score': sum(scores, ZERO) / len(scores) if scores else '',
                'minimum_flow_alignment_score': min(scores) if scores else '',
                'maximum_flow_alignment_score': max(scores) if scores else '',
                'validated_smart_wallet': False, 'production_weight_available': False})
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows in [('outcome_flows.csv', details), ('meeting_decisions.csv', decisions), ('wallet_diagnostics.csv', summaries)]:
        write_csv(args.output / name, list(rows[0]), rows)
    inputs = [prior / 'candidate_history_summary.csv', prior / 'prior_market_tokens.csv',
              prior / 'prior_wallet_trades.csv.gz', args.probabilities]
    report = {'method_version': 'flow-alignment-v1', 'candidate_numbers': CANDIDATES,
              'main_window_days': 7, 'sensitivity_window_days': [1, 30], 'meeting_count': len(events),
              'selected_wallet_source_rows': source_rows, 'outcome_flow_rows': len(details),
              'meeting_decision_rows': len(decisions), 'wallet_diagnostic_rows': len(summaries),
              'input_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
              'score_denominator': 'gross token shares; prevents near-cancelled net flow amplification',
              'quote_maximum_age_hours': 24, 'duplicate_fraction_maximum': '0.05',
              'claim': 'Retrospective signed trade-flow association, not proper forecast score, PnL, or validated skill',
              'selection_bias': 'Four wallets selected using later June activity and all-seven prior meeting coverage',
              'original_resolution_timestamps_verified': False, 'prior_polygon_verification': False}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    checksums(args.output)
    checksums(args.event_root)
    print(json.dumps(summaries, default=str, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event-root', type=Path, default=Path('datasets/polymarket/event_101772'))
    parser.add_argument('--probabilities', type=Path, default=Path('datasets/forward_probabilities.csv'))
    parser.add_argument('--output', type=Path, default=Path('datasets/polymarket/event_101772/decision_review'))
    main(parser.parse_args())
