# uk_inflation_predictors

Research layer for forecasting and nowcasting UK CPI from independently collected predictor data.

**This repository no longer owns source collection.** Each publisher is collected by a standalone repository created from the UK predictor collector template.

## Repository roles

### Official targets (Y)

- `collector_ons_cpi`
- `collector_ons_ex_cpi`

They own official CPI levels, classification, weights and target validation.

### Predictor collectors (X)

- [`collector_desnz_uk`](https://github.com/lucasweber1202/collector_desnz_uk) — DESNZ predictor feeds, beginning with weekly road fuels.
- [`collector_defra_uk`](https://github.com/lucasweber1202/collector_defra_uk) — DEFRA predictor feeds, beginning with fruit/vegetable wholesale prices.
- future: `collector_ofgem_uk`, `collector_hmrc_uk`, `collector_elexon_uk`, `collector_dft_uk`, `collector_orr_uk`.

Predictor collectors own extraction, raw values, vintages, source snapshots and point-in-time availability. They do not import this repository or each other.

### Research layer (this repository)

This repository owns:

- `source_registry.csv`: source/publisher research inventory;
- `collector_registry.csv`: which repository owns each implemented/planned source family;
- `predictor_map.csv`: predictor → ONS target crosswalk;
- future feature definitions and transformations;
- correlation and cross-correlation studies;
- lead/lag selection;
- AR(p) benchmark models;
- AR(p)+predictor models;
- rolling/expanding pseudo-out-of-sample evaluation;
- RMSE, MAE, bias, directional/turning-point metrics;
- predictor ranking by incremental OOS value.

## Non-negotiable research rule

Every historical experiment must query predictor collectors point-in-time. A feature for forecast instant `t` may use only vintages with `available_at <= t`. `inferred`/`unknown` availability is excluded unless an experiment explicitly opts into reconstructed history and labels the result accordingly.

## What does not belong here

No HTTP source collector, Databricks ingestion pipeline, raw source snapshot storage, publisher-specific parser or source credential belongs in this repository after the split.

## Migration state

The original V0.1 collection code is preserved in Git history. Standalone repository trees were prepared before the research-only tree was created, so source ownership moved without losing provenance. The reviewed migration branches are `migration/desnz-standalone-v2` and `migration/defra-standalone-v2` in their owning repositories.
