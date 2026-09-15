# collector_desnz_uk

Standalone predictor collector for UK data published by the Department for Energy Security and Net Zero (DESNZ).

This repository is an **X-variable collector** for UK inflation research. Official CPI targets remain in `collector_ons_cpi` / `collector_ons_ex_cpi`; forecasting and predictor evaluation remain in `uk_inflation_predictors`.

## Implemented dataset

`Weekly road fuel prices`:

- ultra-low-sulphur unleaded petrol pump price;
- ultra-low-sulphur diesel pump price;
- petrol and diesel duty rates;
- petrol and diesel VAT rates.

History starts 2003-06-09 and is stitched from the official 2003-2017 and 2018-present CSVs. Values remain weekly and untransformed.

## Output

Schema: `collector_desnz_uk`.

Tables: `metadata`, `time_series`, `availability`, `source_snapshots`, `logs`.

## Point-in-time

Historical GOV.UK change-history coverage is incomplete for road fuels. Evidence-backed release timestamps are used where available; uncovered history is marked `inferred` and excluded from `get_series_as_of()` by default. Later historical revisions are always stamped `first_seen` unless explicit revision-release evidence exists.

## Run

```bash
python -m scripts.init_db
python main.py
```

An unchanged second run is a data no-op except for the execution log.

See `METHODOLOGY.md` and `POINT_IN_TIME.md`.
