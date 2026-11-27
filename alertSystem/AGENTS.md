# AGENTS.md — guide for AI agents (and teammates) working on EventLens

Read this before you change anything in `FYP/alertSystem`. It explains what the project is, where everything
lives, and the rules every change must follow. Last updated 2026-11-27 (app v1.2).

## 1. What this is

**EventLens** is an event-risk monitor. A user enters US stocks / ETFs; EventLens links each holding to live
Polymarket bets, watches those bets, and flags when a linked bet's odds **jump** (≥ 10 points in 1 hour).
Research shows a linked jump comes with a modestly higher chance of a **big move** in the holding (any direction),
strongest at the **next US open** after an overnight jump. Wallet-level Polymarket data adds context (who is moving
the odds).

What it must never claim: **direction** (up/down), buy/sell advice, or certainty. Every direction test was ~50%.
About 3 in 4 alerts still end calm. Wording in the app and docs must stay honest about this.

Background: the team's FYP (HKUST). The repository root `FYP/` also holds the proposal (LaTeX), `models/`,
`datasets/` and `sunny_playground/`; this guide covers `alertSystem/` only. Git branch: **`alert-system`**.

## 2. Read these first, in order

1. `docs/00_PLAN.md` — **the source of truth**: value proposition, "what an alert means", evidence map
   (A = can, B = cannot, C = test register), work breakdown (the TODO table, with blockers), status, decision log.
2. `docs/08_system_workflow.md` — **how the product works now**: actors, state machines, how bets are linked,
   one scan, Today screen, Watch the open, holding drawer, logs, parameters, change log.
3. The numbered doc for whatever test or feature you are touching (section 4 below).

## 3. Folder map

```text
alertSystem/
  AGENTS.md            this file
  README.md            how to run (Windows)
  docs/                plan, workflow, one numbered doc per test or feature (see section 4)
  src/walletlens/
    config.py          every research parameter, fixed before research runs (ASSET_GROUPS, keywords, thresholds)
    polymarket/        API clients: Gamma, Data API, CLOB, Yahoo, Binance (standard library HTTP)
    collect/ data/     resumable downloads, schema, dataset builders
    analytics/         calibration, wallet skill, markouts, walk-forward, statistics
    topics/events/     T2 research: daily.py (shared context), experiments/ (V*, W*, D*, M*, S* tests)
    wallet_pipeline/   the team's wallet clustering (C0 market makers, C1 patient, C2 burst traders)
    monitor/           THE APP BACKEND
      __init__.py      APP_VERSION (stamped on every live log row)
      engine.py        Model, Monitor.scan, digest, watch_open (D4), holding_live (drawer charts)
      holdings.py      portfolio import: resolve ticker, link layers 1-3, history check
      holding_wallets.py  per-holding wallet checks (D2, D3)
      service.py       glue: portfolio, profiles, background scans, logs, state for the API
      sources.py       LiveSource (Polymarket + Yahoo) and ReplaySource (research data at a past moment)
      journal.py       journal / notes logs; export.py builds data/app/model.json from a results run
    app/               server.py (local HTTP API) + static/ (index.html, app.js, styles.css; no framework)
  scripts/             one-off analysis scripts (vN_*.py), each tied to a doc
  tests/               pytest suite (planted-signal and null worlds, monitor tests)
  config/              JSON overrides (quick, pilot)
  data/
    raw/ interim/ processed/   research data (git-ignored, large). The live app NEEDS
                       processed/events/ (markets.csv, trades.pkl.gz) for per-holding wallet checks:
                       a fresh clone must get it from a teammate or rebuild it (`run.ps1 full`).
    app/               live app state: model.json, portfolio.json, holdings/<T>.json,
                       journal.jsonl, notes.jsonl, warnings_shadow.jsonl  (the V1 live track record)
  results/<YYYYMMDD-HHMM>_<name>/   every research output; INDEX.md / OVERVIEW.md list them
  logs/                run logs
  *.bat                double-click entry points (Windows)
```

Entry points (Windows, double-click): `restart.bat` (stop and start the live app with the newest code — use this
after any app change), `eventlens.bat` (start), `eventlens-replay.bat` (app on research data, 13 Jun 2025),
`calibrate.bat`, `livecheck.bat`, `v3download.bat`, `research.bat`, `full.bat`. CLI:
`python -m walletlens app [--replay 2025-06-13T02:30] [--port N]` with `PYTHONPATH=src`. The app runs at
`http://127.0.0.1:8765`.

## 4. Naming and IDs

**TODO / test IDs** (used everywhere: plan, docs, code comments, commit messages):

| Prefix | Meaning | Examples |
|---|---|---|
| **D** | Dashboard / product implementation | D1 portfolio import, D4 Watch the open |
| **W** | Wallet research test | W7 cluster surge, W8 early-warning fix |
| **M** | Model (machine learning) | M1 learned links, M2 move size, M4 volatility model |
| **V** | Validation (data, controls, live run) | V1 live run, V3 sector gauges, V4 clean links |
| **H** | Housekeeping | H1 clean up |
| S, C, E, D-fix | earlier sequence / crypto / fallback tests and bug fixes | S2, D-fix-3 |

New IDs continue the sequence (next W is W11, next M is M5, next V is V7, next D is D5). Never reuse an ID.

**Docs:** `docs/NN_short_name.md`, next free number (now 16). One doc per test or feature.
**Results:** `results/YYYYMMDD-HHMM_short_name/` (local HKT time), holding the JSON/CSV/PNG outputs.
**Scripts:** `scripts/vN_short_name.py`, taking `<data root> <output folder> [inputs]` as arguments.

## 5. Rules for every change

### Research (any new test)
1. **Pre-register first.** Write the doc (question, design, data, **pass rules**, what each outcome changes in the
   product) and save it *before* running. Put "Pre-registered <date time>, before running" at the top.
2. Run it; save outputs under `results/<stamp>_<name>/`.
3. Append the result to the same doc: a results table with 95% CIs, which rules passed/failed, implication.
   **Do not change pass rules after seeing results.** Post-hoc ideas go in as new, labelled follow-ups.
4. Statistics conventions: day-cluster bootstrap CIs (1,000 draws), same-hour fixed effects where holdings are
   compared, placebo / unrelated assets as controls, crypto bets excluded from stock tests, outcome =
   |return| ÷ the holding's mean for that hour of day. A "top-20% move" = the holding's own top fifth of hourly moves.
5. Update `docs/00_PLAN.md`: test register row (C), evidence map (A/B) if a claim changes, TODO table status,
   status checklist, decision log if a decision was made. Update `docs/02_research_log.md` for major rounds.

### Product (any change under `src/walletlens/monitor/` or `src/walletlens/app/`)
1. Every number the app shows must trace to a logged result (doc + results folder). No result, no claim.
2. **Bump `APP_VERSION`** in `src/walletlens/monitor/__init__.py` for any change in behaviour or display
   (minor: 1.2 → 1.3). Live log rows carry it, so V1 can split the track record by version.
3. **Update `docs/08_system_workflow.md`**: the affected section (state machine, rules table, parameters) and a
   change-log row `| date | version | what changed |`. This is a standing rule.
4. Update the TODO row in `docs/00_PLAN.md` (status → Done (vX.Y)).
5. Test: `pytest tests/` and a replay check (`python -m walletlens app --replay 2025-06-13T02:30 --port 8799`):
   open the page, no console errors, look at the screen you changed.
6. The frontend may meet an older server (or the reverse) during a restart: read new fields defensively.
7. Tell the user to run `restart.bat` to load the new code.

### Never
- Never delete or rewrite `data/app/*.jsonl` (the live track record) or `results/` folders. Append only.
- Never show or imply a price direction, a trade, or "safe" / "dangerous" verdicts.
- Never add a link, signal or model to the app because it "looks right": it needs a passing test.
- Never put API keys or personal data in the repo. Never commit large data (`data/raw|interim|processed`).
- Do not commit or push unless the user asks; commits go on branch `alert-system`.

## 6. Current state (keep in sync with 00_PLAN)

- App **v1.2** live (V1 running from this folder). Features: portfolio import with checked links, Today screen
  (Watch the open, Jumping now, wallet patterns, large-wallet pressure), holding drawer with live price and
  move charts, Track record, How we know. Early warning (W3) runs in **shadow mode** (failed live calibration D7).
- Key evidence: linked holding vs others in the same hour **+7%**, **+12%** at the open; direct links **+10.6%**
  (+16% overnight); alert → top-20% move 25% vs 18%; direction ~50%.
- Open work (see the TODO table): V1 live run, V3 sector gauges (needs `v3download.bat`), V5 full Polymarket
  universe, V6 5-minute data, W8 early-warning fix (after V1), M1 learned links, M2 move size, **M4 volatility
  model on the jump stream** (priority, after V5 + V1).

## 7. How to report back

Short and concrete: what you ran, the result with its CI, pass/fail against the pre-registered rule, what changed
in the product and which docs you updated. If a test fails, say so plainly and record why and what would be tried
next as a remark on the TODO row.
