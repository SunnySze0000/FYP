# 03 · App plan — built as EventLens v1 (2026-11-27)

*v1 as built: see the bottom of this file. The original draft below was for topic F and is kept for the record.*

Blocked until a gate in `00_PLAN.md` passes. What the app shows depends on which gate passed.

- **Visual rule:** YES/up is teal, NO/down is rose, everywhere. One signature element: a probability rail (price vs fair value) and a tug-of-war bar for skilled-wallet flow.
- **Type:** Bricolage Grotesque for headings, IBM Plex Sans for body, with tabular figures.
- **Pages:** Overview (the research verdict in one sentence, then the gates), Live signal or risk view, Wallets (track records), Research (every experiment with its figure), Past examples.
- **Stack:** Python standard-library server and a JSON API reading `results/<run>/app/`; vanilla JS with hand-made SVG charts, so there is no build step.
- **Already drafted:** `src/walletlens/app/` (server, store, live service, styles). It is kept but not finished.


## EventLens v1 (as built)

- **Start:** double-click `eventlens.bat` (live, rescans every 5 min) or `eventlens-replay.bat` (research data on 13 Jun 2025).
- **Today:** headline sentence; per-holding 24-hour event strip (ticks = 10-point jumps in linked markets, amber dot = early warning); jumping now; unusual wallet activity (W3); large-wallet pressure (W5).
- **Market drawer:** 3-day probability, wallets per hour vs usual, who traded (team clusters, descriptive), linked assets with their measured reaction.
- **Track record:** every alert logged to `data/app/journal.jsonl` and scored against the asset's move.
- **How we know:** D1–D6 verdicts and the limits.
- **Code:** `src/walletlens/monitor/` (sources, engine, journal, service, export), `src/walletlens/app/` (server, static).
- **Design:** cool paper `#edf0f2`, ink `#16212b`, teal = YES/up `#0e8a84`, rose = NO/down `#c2416a`, amber = warning `#c98200`; Bricolage Grotesque + IBM Plex Sans.
