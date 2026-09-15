# Predictor-layer instructions

This is a **predictor (X) data layer**, not a collector of official targets. It
follows the fleet contract in
`lucasweber1202/Coletores/MASTER_MACRO_COLLECTOR_GUIDELINES.md`, with the
deviations recorded below. Read that document and `METHODOLOGY.md` before
changing anything here.

## The separation that defines this repository

- Official UK CPI targets (Y) belong to `collector_ons_cpi` and
  `collector_ons_ex_cpi`. Never reproduce, re-weight or re-aggregate a CPI here.
- Never port the forecast-target weights logic into this repository. There is no
  basket, no hierarchy, no `weights` table, no index construction.
- Never build an aggregate predictor index (food, fruit, energy). Store the
  published product-level levels; composing them is the research layer's job.

## Architecture

- Keep the repository flat and source-specific. One `extract_<source>.py` per
  source, openable and auditable on its own. Do not merge them into one
  `extract.py`, and do not add `core/`, `lib/`, `common/`, `framework/`, a
  `BaseCollector`, an adapter framework, a plugin system, an ORM, migrations or
  Docker.
- `scripts/govuk.py` is the one justified shared module: the HTTP allowlist,
  retry budget, download ceiling and GOV.UK change-history parsing belong in
  exactly one place. Source-specific parsing, validation and identifiers stay in
  the `extract_*.py` files. Do not add further shared modules without the same
  kind of justification.
- Adding a source means adding one `extract_<source>.py`, one entry in
  `main.SOURCES`, and one row in `source_registry.csv`. Nothing else changes.

## Approved deviations from the base fleet contract

These were requested explicitly for this repository and are not licence for
further schema drift:

- `metadata.source_id` carries the `source_registry.csv` key.
- `availability` and `source_snapshots` are extra tables, required because
  point-in-time reconstruction and raw-file traceability are the point of this
  layer.

## Storage

- Store the **raw published level only**. Never write MoM, YoY, monthly average,
  MTD, rolling windows, diffusion or volatility to the database. Never resample
  a weekly source to monthly during collection.
- Preserve vintages. Never overwrite a historical vintage.
- An `availability` row is immutable once written. Rewriting it would revise the
  record of what was knowable.

## Point-in-time

- Never invent a historical availability date. If the source does not establish
  it, the basis is `inferred` or `unknown`, and both are excluded from
  `get_series_as_of` by default.
- `get_series_as_of` must never return a row with `available_at > as_of`. That
  invariant has explicit tests in `tests/test_as_of.py`; do not weaken them.
- When attribution is uncertain, prefer a **later** availability instant. Late
  understates the information set; early is a look-ahead.

## Behaviour

- Preserve idempotency: an unchanged second run writes no metadata, observation,
  availability or snapshot row, but does write one successful log row.
- Validation runs before persistence, and a structural failure stops the run
  rather than warning. A renamed column, a shifted first observation or a broken
  cadence is a hard failure.
- Verify endpoints and file layouts against the current official source. Never
  pin an attachment URL whose path carries a content hash; discover it from the
  live page.
- Never assert a licence, API, history start or revision policy that is not
  stated by the official source. Mark it `unknown` and document why.

## Verification before a PR

`python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`,
and `python -m mypy`, plus a fresh-database run and an immediate rerun to
confirm the rerun is a data no-op.
