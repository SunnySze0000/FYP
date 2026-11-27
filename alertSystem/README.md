# WalletLens (fyptest1)

A fresh start on the FYP brief: **Polymarket + wallets → a trading / financial helper**, done
research-first. No app is built until a pre-registered test passes.

Start with **[docs/00_PLAN.md](docs/00_PLAN.md)** (the plan, gates and decision log). AI agents and new teammates: read **[AGENTS.md](AGENTS.md)** first (structure and rules).

## Run it (Windows PowerShell)

```powershell
cd $HOME\Downloads\fyptest1
powershell -ExecutionPolicy Bypass -File run.ps1 all
```

`all` = install packages → tests → connection check → a quick trial of everything →
the full run (all collectors in parallel, then all research). Stop with Ctrl+C and rerun
any time; downloads resume from the cache. Other commands: `quick`, `full`, `research`,
`pilot`, `check`, `test`, `status` (see the top of `run.ps1`).

When it finishes, open **`results/OVERVIEW.md`**.

## The three topics (researched in parallel)

| Topic | Question | Advice for | Suite |
|---|---|---|---|
| **T1** crypto | Do Polymarket BTC/ETH up/down markets, and skilled wallets trading them, lead the spot price? | BTC/ETH spot | `crypto` (C0–C3) |
| **T2** events | Do event-probability shocks move the related assets (oil, Treasuries, China ETFs…), and do skilled wallets move first? | portfolio risk/hedging | `events` (V0–V4) |
| **F** fallback | Do skilled wallets inside Polymarket keep their edge, and can it be copied? | Polymarket itself | `polymarket` (E0–E5) |

## Layout

```text
config/            JSON overrides (quick, pilot)
docs/              00 plan · 01 topic · 02 research log · 03 app plan
src/walletlens/
  config.py        every parameter, fixed before the research runs
  polymarket/      API clients: Gamma, Data API, CLOB, Binance data, Yahoo (standard library)
  collect/         shared resumable download blocks + topic F collector
  data/            canonical schema, cleaning, dataset builders
  analytics/       calibration, wallet skill, markouts, walk-forward models, statistics
  research/        result format, runner (suites, decisions, index), topic F experiments
  topics/crypto/   T1 collector, minute panel, experiments C0-C3
  topics/events/   T2 collector, event-asset analysis, experiments V0-V4
  orchestrate.py   run-all: collectors in parallel, then research, then OVERVIEW.md
  app/             drafted web app (not finished on purpose)
data/raw/          untouched API responses (cache)
data/interim/      cleaned per-market files
data/processed/    analysis-ready datasets, one folder each
results/           one folder per research run + INDEX.md + OVERVIEW.md
logs/              one log per command
tests/             unit tests + synthetic worlds with planted effects (and null worlds)
```

Every research run writes `results/<run>/summary.md`, one folder per experiment with
`summary.json`, tables (CSV) and figures (PNG), and a `manifest.json` with all settings used.

## How we know the code finds real effects

Each suite is tested on synthetic data twice: once with a planted effect (skilled wallets,
a Polymarket lead, an event→asset link) that it must detect, and once without, where it
must not pass. See `tests/`.
