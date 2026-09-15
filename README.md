# uk_inflation_predictors

Open, historically reproducible **predictor (X) data** for forecasting and
nowcasting the UK Consumer Prices Index.

## What this repository is, and what it is not

This repository is **separate from the ONS collectors** and has a different job.

| | Repository | Role |
|---|---|---|
| **Official targets (Y)** | [`collector_ons_cpi`](https://github.com/lucasweber1202/collector_ons_cpi), `collector_ons_ex_cpi` | The authoritative UK CPI series, its official basket weights, and the bottom-up reconciliation of the published index. These remain the **only** source of truth for the variables a model is evaluated against. |
| **Alternative predictors (X)** | **`uk_inflation_predictors`** (this repository) | Open, non-ONS explanatory variables that may help predict those targets, plus everything needed to reconstruct what was knowable at a past instant. |

Consequences of that split, which this repository holds to strictly:

- **No CPI is rebuilt here.** No forecast-target weights, no basket, no
  aggregation hierarchy, no index construction. `collector_ons_cpi` owns that
  and its logic is deliberately not copied.
- **No aggregate predictor index is invented.** Individual published levels are
  stored as published. Combining them into a "food index" or "energy index" is
  a modelling decision for the research layer, not a collection decision.
- **No transformations are stored.** No month-on-month, year-on-year, monthly
  average, month-to-date, rolling window, diffusion or volatility measure is
  written to the database. Only the raw published level. Transformations are
  derived downstream, where the choice of transformation is part of the
  research, not baked irreversibly into storage.
- **No modelling.** No regressions, AR models, forecasting, machine learning,
  feature selection or dashboards live here. This is a data foundation.

## Implemented sources (v0.1)

| source_id | Source | Publisher | Frequency | History | Series |
|---|---|---|---|---|---|
| `desnz_road_fuels` | [Weekly road fuel prices](https://www.gov.uk/government/statistics/weekly-road-fuel-prices) | DESNZ | Weekly | 2003-06-09 → present | 6 |
| `defra_fruit_veg` | [Wholesale fruit and vegetable prices](https://www.gov.uk/government/statistical-data-sets/wholesale-fruit-and-vegetable-prices-weekly-average) | DEFRA | Irregular (weekly/fortnightly) | 2017-11-03 → present | 71 |

`source_registry.csv` additionally registers twelve further candidate sources
that are catalogued but **not implemented**, with every unverifiable field
explicitly marked `unknown`. See [SOURCES.md](SOURCES.md).

## Usage

```bash
python -m scripts.init_db                      # create schema and tables
python main.py --source desnz_road_fuels       # one source
python main.py --source defra_fruit_veg
python main.py --all                           # every implemented source
```

A fresh database performs the full historical backfill. A second run against an
unchanged source writes **nothing** to `time_series`, `availability`,
`source_snapshots` or `metadata`, and one successful row to `logs`.

## Configuration

Copy `.env.example` to `.env`. `PROD=false` uses the local PostgreSQL database in
`PREDICTORS_DB_URL`; `PROD=true` uses Databricks (`macrobond_inhouse` catalog).
Raw downloaded files go to a gitignored directory and are **never committed**;
`source_snapshots` is the traceability record.

## Database

Schema `uk_inflation_predictors`, five tables:

- **`metadata`** — one row per predictor: identifier, `source_id`, name,
  description, `country` (`GBP`, the fleet currency vocabulary), frequency,
  unit, first/last observation, observation count, source URL, last publish
  date.
- **`time_series`** — append-only `(series_id, reference_date, vintage_date)`
  observations of raw published levels. Revisions add vintages; historical
  vintages are never overwritten.
- **`availability`** — the point-in-time companion: when each stored vintage
  actually became knowable, and **how strong the evidence for that is**.
- **`source_snapshots`** — one row per distinct raw file parsed, keyed by the
  SHA256 of its bytes, with ETag, Last-Modified and local path.
- **`logs`** — one row per execution, success or failure.

## Point-in-time retrieval

```python
from datetime import UTC, datetime
from scripts.availability import get_series_as_of
from scripts.db import build_engine

rows = get_series_as_of(
    build_engine(),
    "DEFRA_FRUITVEG_FRUIT_APPLES_GALA",
    datetime(2026, 9, 1, tzinfo=UTC),
)
```

No returned row can have `available_at > as_of`. By default only
evidence-backed availability answers the query; reconstructed availability
(`inferred`, `unknown`) must be opted into explicitly. This is the central
guarantee of the repository — read [POINT_IN_TIME.md](POINT_IN_TIME.md) before
using the data for any backtest.

## Predictor-to-target mapping

`predictor_map.csv` links every predictor to the CPI series it is meant to help
predict, in `collector_ons_cpi`. Where the ONS native identifier could not be
confirmed by reading that repository, the target is written as
`PENDING_VERIFICATION` rather than guessed.

## Documents

- [METHODOLOGY.md](METHODOLOGY.md) — identifiers, storage contract, validation.
- [SOURCES.md](SOURCES.md) — what each source publishes and what is not yet verified.
- [POINT_IN_TIME.md](POINT_IN_TIME.md) — availability semantics and their limits.
