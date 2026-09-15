# UK Predictor Collector Template

Use this repository as the canonical skeleton for one UK inflation predictor source/publisher.

## Non-negotiable rules

- Repository name: `collector_<source>_uk`.
- Database schema name must equal repository name.
- One publisher/source family per repository.
- Official CPI targets do not live here.
- Store raw published levels only.
- Preserve vintages and point-in-time availability.
- Second unchanged run is a data no-op.
- No cross-repository imports, shared core package, `BaseCollector`, ORM, migrations, Docker or plugin framework unless explicitly approved.
- Source-specific logic belongs in `scripts/extract.py` and only the helper modules forced by that source.

## Tables

Every predictor collector writes `metadata`, `time_series`, `availability`, `source_snapshots`, and `logs`.

## Creating a collector

1. Copy this skeleton into a new `collector_<source>_uk` repository.
2. Change `SCHEMA_NAME` and `COLLECTOR_USER_AGENT` in `scripts/config.py`.
3. Implement `scripts/extract.py` for the source.
4. Narrow metadata vocabularies to values actually emitted when useful.
5. Add source validation and source-specific tests.
6. Document historical coverage and point-in-time limitations.
7. Verify fresh DB, unchanged rerun, later-day revision, snapshot replacement and `get_series_as_of()`.

See `PREDICTOR_COLLECTOR_GUIDELINES.md`, `METHODOLOGY.md`, and `POINT_IN_TIME.md`.
