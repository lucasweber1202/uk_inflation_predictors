# collector_defra_uk

Standalone predictor collector for UK data published by the Department for Environment, Food & Rural Affairs (DEFRA).

This repository owns DEFRA predictor data only. Official CPI targets remain in `collector_ons_cpi` / `collector_ons_ex_cpi`; modelling and predictor evaluation remain in `uk_inflation_predictors`.

## Implemented dataset

`Wholesale fruit and vegetable prices`:

- all machine-readable fruit series;
- all machine-readable vegetable series;
- raw published price and unit;
- no synthetic food, fruit or vegetable index.

The current machine-readable CSV begins 2017-11-03. The official historical ODS reaches further back (2015) and is an explicit next collector gate: it should be stitched ahead of the CSV with overlap checks rather than discarded.

Future DEFRA datasets such as bananas, farm-gate milk and Agricultural Price Indices belong in this repository as flat source-specific modules because the publisher is the same; they must not become separate repositories unless governance later changes to dataset-per-repo.

## Output

Schema: `collector_defra_uk`.

Tables: `metadata`, `time_series`, `availability`, `source_snapshots`, `logs`.

## Point-in-time

The current fruit/vegetable history is attributable to GOV.UK change-history timestamps. Later historical revisions are stamped `first_seen` unless explicit revision-release evidence exists.

## Run

```bash
python -m scripts.init_db
python main.py
```

An unchanged second run is a data no-op except for the execution log.

See `METHODOLOGY.md` and `POINT_IN_TIME.md`.
