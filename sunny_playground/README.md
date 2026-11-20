# EventLens playground (`sunny_playground` branch)

A clean restart of the EventLens research code: Polymarket signals for trading
decisions, tested with point-in-time features, event-level statistics and
walk-forward backtests. **Start with [FINDINGS.md](FINDINGS.md).**

Nothing outside this folder is changed. The team's existing `models/`,
`datasets/` and `proposal/` folders are read but never modified.

## Layout

```text
sunny_playground/
├── FINDINGS.md               # What we learnt and the recommended direction
├── reports/                  # Generated: results.md + one CSV per table
├── scripts/run_research.py   # Runs every analysis
├── src/eventlens/
│   ├── config.py             # Paths (override with environment variables)
│   ├── data/                 # taxonomy.py, fomc.py, loaders.py
│   ├── validation/checks.py  # Data-quality checks that report, never repair
│   ├── features/             # events.py (per-meeting), returns.py (event windows)
│   ├── analysis/             # sanity, event_study, calibration, wallets, universe
│   ├── collectors/           # Gamma markets, CLOB prices, Yahoo prices (stdlib only)
│   ├── stats.py              # Bootstrap, permutation, clustered tests, power
│   ├── reporting.py          # CSV + Markdown output
│   └── pipeline.py           # One run_* function per research phase
├── tests/                    # pytest: maths, leakage guards, synthetic backtests
├── data/raw/                 # Local data (git-ignored), see below
└── legacy_reference/         # Collector scripts copied from PR #1, for reference
```

## Setup

Python 3.10+.

```sh
cd sunny_playground
python -m pip install -r requirements.txt
python -m pytest
```

### Wallet data (from PR #1)

The June 2026 wallet trades live on the branch
`codex/polymarket-fed-wallet-dataset`. Extract them into the ignored
`data/raw` folder once, from the repository root:

```sh
git fetch origin codex/polymarket-fed-wallet-dataset
mkdir -p sunny_playground/data/raw/fed_wallets
git archive origin/codex/polymarket-fed-wallet-dataset datasets/polymarket | tar -x -C sunny_playground/data/raw/fed_wallets --strip-components=2
```

On Windows, run this in Git Bash.

## Run the research

```sh
python scripts/run_research.py
```

This writes `reports/results.md` and the CSV tables in about 30 seconds.

## Collect more data (needs internet; run on your own PC)

The cross-market study needs data the sandbox cannot download. From
`sunny_playground`, with `src` on the path:

```sh
# Windows PowerShell: $env:PYTHONPATH="src"   |   macOS/Linux: export PYTHONPATH=src
python -m eventlens.collectors yahoo                                  # SPY, QQQ, IWM, TLT, DIA
python -m eventlens.collectors markets --since 2024-01-01 --min-volume 10000
python -m eventlens.collectors prices                                 # one request per market
python scripts/run_research.py                                        # section 6 now runs
```

Every request is cached under `data/raw/`, so an interrupted run can be
restarted with the same command. Use `--max-markets 500` for a quick trial.

## Conventions

- **Point in time:** every feature for a decision at time *t* uses only data
  stamped before *t*. Tests in `tests/test_features.py` and
  `tests/test_universe_and_collectors.py` enforce this.
- **Report, don't repair:** bad data is listed in `reports/data_check_*.csv`
  and excluded, never silently rescaled or forward-filled.
- **Honest statistics:** hypotheses are fixed in advance. Uncertainty
  resamples independent units (meetings, events, wallets), not daily rows.
  Trading rules must pass a break-even or walk-forward test after costs.
- **Paths:** set `EVENTLENS_TEAM_DATA`, `EVENTLENS_RAW_DATA` or
  `EVENTLENS_REPORTS` to use data stored elsewhere.
