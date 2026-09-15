# Methodology

## Scope

This repository collects **explanatory variables (X)** for UK CPI forecasting.
The official target variables (Y) are collected by `collector_ons_cpi` and
`collector_ons_ex_cpi` and are never reproduced here. No index construction, no
basket weights, no aggregation hierarchy.

## Architecture

Deliberately boring and flat. One file per source, openable and auditable on its
own:

```
main.py                              CLI and orchestration only
scripts/config.py                    settings from environment and .env
scripts/db.py                        PostgreSQL / Databricks engine
scripts/init_db.py                   all DDL
scripts/govuk.py                     shared GOV.UK access (see below)
scripts/time_series.py               observation persistence and vintages
scripts/availability.py              point-in-time layer and as-of retrieval
scripts/snapshots.py                 raw-file traceability
scripts/metadata.py                  descriptive rows
scripts/run_logs.py                  execution log
scripts/extract_desnz_road_fuels.py  one source
scripts/extract_defra_fruit_veg.py   one source
```

There is no `BaseCollector`, no adapter framework, no plugin system, no ORM, no
migrations, no Docker, no `core/`, `lib/`, `common/` or `framework/`. Adding a
source means adding one `extract_<source>.py` and one line in `main.SOURCES`.

### The one shared module, and why

`scripts/govuk.py` holds the HTTP client, host allowlist, retry budget, download
ceiling, attachment discovery and change-history parsing. Both v0.1 sources are
GOV.UK pages with an identical access contract. Duplicating the network policy
per source file would place the allowlist and redirect rules in two places and
let them drift; the security surface belongs in exactly one place. Source-
specific parsing, validation and identifiers stay entirely in the two
`extract_*.py` files, which is where an auditor looks.

## Identifiers

Structured, uppercase, unique, and round-trippable through the owning module's
`parse_series_id()`. The official product name is never part of the identifier:
a label edit upstream must not fork a stored history.

```
DESNZ_ROADFUEL_{PRODUCT}_{MEASURE}
  DESNZ_ROADFUEL_ULSP_PUMPPRICE     unleaded petrol, pump price
  DESNZ_ROADFUEL_ULSD_PUMPPRICE     diesel, pump price
  DESNZ_ROADFUEL_ULSP_DUTYRATE      unleaded petrol, duty rate
  DESNZ_ROADFUEL_ULSD_VATRATE       diesel, VAT rate

DEFRA_FRUITVEG_{CATEGORY}_{ITEM}_{VARIETY}
  DEFRA_FRUITVEG_FRUIT_APPLES_GALA
  DEFRA_FRUITVEG_VEGETABLE_CABBAGE_SAVOY
```

DEFRA's native labels are normalized by stripping non-alphanumerics. That is
verified collision-free across all 71 published fruit and vegetable series, and
re-checked on every run rather than assumed.

## Storage contract

`metadata`, `time_series` and `logs` follow the fleet contract, with two
additions requested for this repository: `metadata.source_id` (the
`source_registry.csv` key) and the `availability` and `source_snapshots` tables
that make point-in-time reconstruction possible.

`country` is `GBP` for every series, following the fleet convention that the
column named `country` carries an ISO 4217 **currency** code.

### Raw levels only

Only the level the source published is stored. Not stored, by design: MoM, YoY,
monthly average, MTD, last-7-days, last-14-days, diffusion, volatility, or any
aggregate index over products. DESNZ data stays at the weekly frequency the
source publishes and is **not** converted to monthly during collection.

The reason is reversibility: a level can be transformed downstream in any way a
researcher chooses, but a stored transformation cannot be turned back into the
level, and it silently fixes a modelling choice at collection time.

### Vintages

1. First sighting of `(series_id, reference_date)` inserts with
   `vintage_date` = collection day.
2. An identical later value is a no-op; `collected_at` is not touched.
3. A changed value on a later day inserts a new vintage. The old row stays.
4. A changed value on the same day updates only today's row.
5. Values are compared at ten decimal places, so serialization noise is not a
   revision.
6. `None`, NaN and infinite values are dropped before insert.

Historical vintages are never overwritten, and an `availability` row, once
written, is never rewritten: revising it would revise the record of what was
knowable, which is the one thing this repository exists to preserve.

## Validation

Every source runs its structural gates **before anything reaches the database**,
and a critical failure raises rather than warns, so a malformed release cannot
corrupt a good stored history. For each source the pipeline checks:

1. **Source schema** — the published header matches the verified layout exactly;
   a renamed or moved column stops the run.
2. **Missing values** — an empty cell is dropped, never stored as zero.
3. **Duplicates** — one series may publish one value per reference date.
4. **Frequency** — the observed cadence stays within the source's measured gap
   distribution (DESNZ 5-9 days; DEFRA no gap beyond 45 days).
5. **Units** — DEFRA's price unit is checked against the verified vocabulary, and
   a series publishing two different units is refused.
6. **First observation** — must equal the known start of the published history,
   which is how a truncated or substituted historic file is detected.
7. **Last observation** — never in the future.
8. **Value plausibility** — non-positive prices refused; VAT rates must be a
   percentage in `[0, 100]`.
9. **Volume floors** — a series or date count below the measured floor is
   treated as a truncated download.
10. **Identifier injectivity** — normalization must stay collision-free.

Soft failures (one unparseable row, one bad date) are warned and skipped.
Authentication and total network failure after retries propagate.

## Idempotency

A second run against an unchanged source produces zero writes to `time_series`,
`availability`, `source_snapshots` and `metadata`, and one successful `logs`
row. Snapshot identity is the content digest, so re-downloading an unchanged
file records nothing new. Verified end to end against PostgreSQL and covered by
`tests/test_idempotency.py`.

## Security

No credentials in code or logs; `.env` is gitignored and `.env.example` carries
names only. Every HTTP request passes a fixed host allowlist
(`www.gov.uk`, `assets.publishing.service.gov.uk`) — including attachment URLs
read out of a fetched page, which are source-controlled input. Redirects are not
followed, TLS verification stays on, downloads are size-bounded and streamed, and
all SQL uses `sqlalchemy.text` with named parameters against constant
identifiers.
