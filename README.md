# uk_inflation_predictors

Research layer for forecasting and nowcasting UK CPI from independently collected predictor data.

**This repository no longer owns source collection.** Each publisher is collected by a standalone repository created from the UK predictor collector template.

## Repository roles

### Official targets (Y)

- `collector_ons_cpi`
- `collector_ons_ex_cpi`

They own official CPI levels, classification, weights and target validation.

### Predictor collectors (X)

| Repository | Data sets | Series |
| --- | --- | --- |
| [`collector_desnz_uk`](https://github.com/lucasweber1202/collector_desnz_uk) | `desnz_road_fuels` (weekly, 2003-06) | 6 |
| [`collector_defra_uk`](https://github.com/lucasweber1202/collector_defra_uk) | `defra_fruit_veg`, `defra_banana_prices`, `defra_milk_prices`, `defra_agricultural_price_index` | 266 |
| [`collector_dft_uk`](https://github.com/lucasweber1202/collector_dft_uk) | `dft_bus_fares` (quarterly, 2005-03) | 16 |
| [`collector_hmrc_uk`](https://github.com/lucasweber1202/collector_hmrc_uk) | `hmrc_tobacco_bulletin`, `hmrc_alcohol_bulletin` (monthly) | 58 |
| [`collector_elexon_uk`](https://github.com/lucasweber1202/collector_elexon_uk) | `elexon_market_index_prices` (half-hourly, 2016-09) | up to 200 |

Blocked or not yet created: `collector_ofgem_uk` (blocked — no machine-readable
artifact), `collector_orr_uk` (planned — fares tables unconfirmed).

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

## Research engine

The repository now contains a deliberately flat Python research engine under
`scripts/`. It reads the collectors' persisted `metadata`, `time_series` and
`availability` contracts; it never imports collector source code.

The supported path is:

```text
persisted raw predictor
→ strict/reconstructed PIT filter
→ as-of panel
→ frequency-aware feature
→ official target release cutoff
→ monthly target alignment
→ historical-mean / last / AR benchmark
→ AR(p) + one predictor
→ expanding pseudo-OOS
→ RMSE / MAE / bias / directional accuracy
→ full ranking table
```

`target_registry.csv` is the versioned ONS target crosswalk. An unresolved
`PENDING_VERIFICATION` target fails closed and cannot enter an experiment.
`predictor_map.csv` is the candidate-feature contract, not a claim of predictive
power.

### Reproduce an experiment

Install the small research dependency set and provide CSV extracts of the
persisted contracts (not raw publisher files):

```bash
python -m pip install -r requirements.txt
python -m scripts.experiments \
  --config configs/first_battery.yml \
  --target-csv target_vintages.csv \
  --predictor-csv predictor_contract.csv \
  --as-of 2026-09-10T23:59:59Z \
  --output results/desnz_fuels.csv
```

The CLI also writes a JSON run manifest beside the ranking CSV. Inputs must
carry their vintages and availability evidence. The checked-in repository does
not contain production databases or large raw snapshots, so empirical rankings
are generated only in an environment with those data contracts available.

Quality gates:

```bash
pytest -q
ruff check .
mypy scripts tests
```

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

A data set inside an otherwise implemented repository can be blocked on its
own: `collector_hmrc_uk` implements both bulletins while both duty-rate data
sets stay blocked, and that repository contains no module for them rather than
a stub.

`source_registry.csv` uses `implemented` / `not_implemented` for
`automation_status`, and `unknown` wherever a fact has not been verified
against the official source. `unknown` is never replaced by a guess.

## Migration state

The original V0.1 collection code is preserved in Git history. Standalone repository trees were prepared before the research-only tree was created, so source ownership moved without losing provenance. The reviewed migration branches are `migration/desnz-standalone-v2` and `migration/defra-standalone-v2` in their owning repositories.
