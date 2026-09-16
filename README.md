# uk_inflation_predictors

Research layer for forecasting and nowcasting UK CPI from independently collected predictor data.

**This repository no longer owns source collection.** Each publisher is collected by a standalone repository created from the UK predictor collector template.

## Repository roles

### Official targets (Y)

- `collector_ons_cpi`
- `collector_ons_ex_cpi`

They own official CPI levels, classification, weights and target validation.

### Predictor collectors (X)

- [`collector_desnz_uk`](https://github.com/lucasweber1202/collector_desnz_uk) — `desnz_road_fuels` (weekly, from 2003-06-09, 6 series).
- [`collector_defra_uk`](https://github.com/lucasweber1202/collector_defra_uk) — `defra_fruit_veg`, `defra_banana_prices`, `defra_milk_prices`, `defra_agricultural_price_index` (266 series, 55,973 observations).
- planned, repositories not yet created: `collector_ofgem_uk`, `collector_hmrc_uk`, `collector_elexon_uk`, `collector_dft_uk`, `collector_orr_uk`.

One repository per publisher, and the schema name equals the repository name. A
new dataset from a publisher already in the fleet is added to that publisher's
repository, never as a new repository.

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

## Source verification

`SOURCE_FICHES.md` holds the verified fiche for every predictor source that is
not yet implemented: landing page, real artifacts, format, frequency, history,
release rule and blockers, each filled from the live source rather than from a
prior registry entry. A collector is not coded until its fiche is complete.

## Registry status vocabulary

`collector_registry.csv` uses:

| Status | Meaning |
| --- | --- |
| `implemented_verified` | Merged on the collector's `main`, with fresh-build, idempotency, revision and as-of gates passing. |
| `planned` | Approved for implementation; the repository may not exist yet. |
| `candidate` | Not approved. Licence, automatability or a machine-readable artifact is unproven. |
| `blocked` | Attempted and stopped by a source, licence or access blocker. |

`source_registry.csv` uses `implemented` / `not_implemented` for
`automation_status`, and `unknown` wherever a fact has not been verified
against the official source. `unknown` is never replaced by a guess.

## Migration state

The original V0.1 collection code is preserved in Git history. Standalone repository trees were prepared before the research-only tree was created, so source ownership moved without losing provenance. The reviewed migration branches are `migration/desnz-standalone-v2` and `migration/defra-standalone-v2` in their owning repositories.
