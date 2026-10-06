# Datasets

| Dataset | Start here |
|---|---|
| Existing Fed probability CSVs | Structure and examples below |
| Polymarket Fed wallet trades and sampled Polygon fills | [Dataset overview](polymarket/README.md) · [CSV dictionary](polymarket/market_906973/README.md) |

The wallet snapshot currently covers one June 2026 outcome market. It can be joined to the
probability data using `market_id`; it does not cover the whole decision distribution yet.

## Forward rate-probability datasets

Market-implied probabilities of central-bank policy outcomes, by meeting horizon.
Two files, same underlying observations, two layouts.

- `forward_probabilities.csv` — **long / tidy**
- `forward_probabilities_wide.csv` — **wide** (pivot of the long file)

Coverage: **546 dates**, `2025-03-20` → `2026-09-16`; **6 outcomes**; horizons **0–6** months;
**10 events**, **43 markets**; 5,834 long rows / 2,533 wide rows.

---

## `forward_probabilities.csv` — long / tidy

One row per `(date, outcome, horizon_month)` — a single observation:

> on `date`, the probability of `outcome` at the meeting `horizon_month` months out was `market_probability`.

Only real observations exist as rows. If no market trades for a horizon, **there is simply no row**
(there is no NaN-filled row here). Best for filtering, joining, grouping.

| Column | Type | Description |
|---|---|---|
| `date` | timestamp (UTC) | Observation date, e.g. `2026-06-01 00:00:00+00:00`. |
| `outcome` | string | One of: `25 bps decrease`, `No change`, `25 bps increase`, `25+ bps increase`, `50+ bps decrease`, `50+ bps increase`. |
| `horizon_month` | int | Calendar months from `date` to the meeting: `meeting_month − date`, in months. `0` = same calendar month. |
| `meeting_month` | string `YYYY-MM` | The meeting this row prices, e.g. `2026-06`. |
| `event_id` | int | Meeting/event grouping. Each `market_id` belongs to exactly one `event_id`; every event has 4–5 markets. |
| `market_id` | int | Traded market. `market_probability`, `final_outcome`, `lifetime_volume` are properties of the market. |
| `market_probability` | float `[0,1]` | Implied probability on `date`. |
| `final_outcome` | `0`/`1` | Realized outcome of that market (1 = happened). Constant per `market_id`. |
| `lifetime_volume` | float | Total traded volume of the **market over its lifetime** — constant per `market_id`, not a daily figure. |

Invariants (hold in the shipped file): no duplicate `(date, outcome, horizon_month)`;
`final_outcome` and `lifetime_volume` are constant per `market_id`.

## `forward_probabilities_wide.csv` — wide

One row per `(date, outcome)`. The forward curve as a vector: `prob_m0 … prob_m6` give the
probability of that outcome at the meeting 0, 1, … 6 calendar months ahead, and
`meeting_m0 … meeting_m6` say which meeting month each column maps to. Best when you want the
term structure as a vector — plotting it, or feeding it to a model as features.

Columns: `date`, `outcome`, then, for each horizon `k` in `0 … 6`:

| Column | Description |
|---|---|
| `prob_m{k}` | Probability at horizon `k`; empty (NaN) if no such market. |
| `meeting_m{k}` | Meeting month (`YYYY-MM`) for horizon `k`; empty if absent. |
| `final_outcome_m0` | Realized outcome (`0`/`1`) of the horizon-0 meeting's market; empty when no horizon-0 market exists (892 rows populated). |

Missing meetings/horizons show as **empty fields → `NaN`** when read into a dataframe (a given
`(date, outcome)` has between 1 and 4 populated horizons).

The wide file is an **exact pivot**: for every row, `prob_m{k}` equals the long-file
`market_probability` for the same `(date, outcome, horizon_month=k)`, and vice versa.

---

## Example — `date = 2026-06-01`, `outcome = '25 bps decrease'`

Long file, one row per observation (note the missing horizon 2 — no August meeting exists):

| horizon_month | meeting_month | market_probability |
|---|---|---|
| 0 | 2026-06 | 0.0095 |
| 1 | 2026-07 | 0.0315 |
| 3 | 2026-09 | 0.080 |

Wide file, one row:

| prob_m0 | prob_m1 | prob_m2 | prob_m3 | … | meeting_m0 | meeting_m1 | meeting_m2 | meeting_m3 |
|---|---|---|---|---|---|---|---|---|
| 0.0095 | 0.0315 | NaN | 0.080 | … | 2026-06 | 2026-07 | NaN | 2026-09 |

## Loading

```python
import pandas as pd

long = pd.read_csv("forward_probabilities.csv", parse_dates=["date"])
wide = pd.read_csv("forward_probabilities_wide.csv", parse_dates=["date"])  # empty fields -> NaN

# term structure for one outcome on one date
long.query("date == '2026-06-01' and outcome == '25 bps decrease'").sort_values("horizon_month")

# curve as a vector
wide.query("date == '2026-06-01' and outcome == '25 bps decrease'")
```

## Which file to use

- Filtering, joining, grouping by horizon/meeting/event → **long**.
- Plotting the term structure or using it as a feature vector → **wide**.
