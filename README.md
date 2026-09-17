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
| [`collector_ofgem_uk`](https://github.com/lucasweber1202/collector_ofgem_uk) | Ofgem final levelised price-cap rates | 352 |
| [`collector_orr_uk`](https://github.com/lucasweber1202/collector_orr_uk) | ORR rail-fare tables 7180/7182 | 54 |
| [`collector_ons_business_prices_uk`](https://github.com/lucasweber1202/collector_ons_business_prices_uk) | ONS PPI and SPPI | 27 |
| [`collector_boe_fx_uk`](https://github.com/lucasweber1202/collector_boe_fx_uk) | Sterling ERI, GBP/USD and GBP/EUR | 3 |
| [`collector_ons_awe_uk`](https://github.com/lucasweber1202/collector_ons_awe_uk) | ONS Average Weekly Earnings | 16 |
| [`collector_boe_dmp_uk`](https://github.com/lucasweber1202/collector_boe_dmp_uk) | BoE Decision Maker Panel aggregates | 11 |
| [`collector_ons_bics_uk`](https://github.com/lucasweber1202/collector_ons_bics_uk) | ONS BICS selected wave-aware series | 140 |
| [`collector_ons_housing_uk`](https://github.com/lucasweber1202/collector_ons_housing_uk) | ONS private-rent successor data | 45 |

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
→ per-forecast-origin target and predictor reconstruction
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
  --output results/desnz_fuels.csv
```

The optional `--as-of` argument is only a ceiling for reproducibility; it is
never used as a single global historical information set. The CLI writes
per-origin forecast rows, a `*_summary.csv` grouped without mixing PIT modes,
and a JSON run manifest. Inputs must
carry their vintages and availability evidence. The checked-in repository does
not contain production databases or large raw snapshots, so empirical rankings
are generated only in an environment with those data contracts available.

Quality gates:

```bash
pytest -q
ruff check .
ruff format --check .
mypy scripts tests
python -m compileall -q .
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
| `blocked_license` | A technically relevant source exists, but lawful historical collection/storage requires a commercial licence or explicit permission, and no licensed route to it is available. No collector repository is created. |
| `ready_with_environment_gate` | The collector repository exists and is architecturally complete, standalone, offline-tested, point-in-time safe and idempotent. The only remaining blocker is environment-bound: a corporate entitlement, the vendor identifiers that can only be confirmed inside it, and a live certification run. |

A data set inside an otherwise implemented repository can be blocked on its
own: `collector_hmrc_uk` implements both bulletins while both duty-rate data
sets stay blocked, and that repository contains no module for them rather than
a stub.

`ready_with_environment_gate` exists because `blocked_license` turned out to be
too coarse. It bundled six separable facts, and `collector_brc_uk` and
`collector_cbi_uk` sit differently on each:

| Term | brc / cbi |
| --- | --- |
| `SOURCE_EXISTS` — the publisher publishes the statistic | yes |
| `VENDOR_AVAILABLE` — a licensed delivery provider is available to the desk | yes, Bloomberg and/or LSEG |
| `ENTITLEMENT_UNKNOWN` — whether the account may read it is unverified | **open** |
| `VENDOR_SERIES_ID_UNKNOWN` — vendor identifiers are unconfirmed | **open** |
| `IMPLEMENTATION_READY` — code, schema, tests and PIT handling complete | yes |
| `LIVE_CERTIFICATION_PENDING` — no live vendor query has run | **open** |

The earlier status asserted that lawful collection was impossible, which
conflated the *publisher's* licensing with the *desk's* access. BRC and CBI data
are licensed, and the desk holds licensed routes to them, so the source is not
economically blocked. What is genuinely unresolved is environmental. Neither
repository may move to `implemented_verified` until a real query has run against
a real provider; `pending_vendor_entitlement` is the status to use instead if
entitlement is ever established to be absent.

Data reaching the fleet through a delivery provider does not change who the
publisher is. `metadata.original_publisher` names BRC or CBI, and the provider
is recorded per observation in `delivery_provider` / `vendor_series_id`. There
is no `collector_bloomberg_uk` and no `collector_reuters_uk`: a collector is
named for a publisher, and a vendor is a route.

`source_registry.csv` uses `implemented`, `not_implemented`, `blocked`,
`blocked_license` and `ready_with_environment_gate` for `automation_status`, and
`unknown` wherever a fact has not been verified against the official source.
`unknown` is never replaced by a guess. A source blocked by licence has no
`predictor_map.csv` row because no persisted data contract exists yet; a source
that is `ready_with_environment_gate` does have rows, because the contract
exists, but every one of them carries `research_status=not_started` and
`point_in_time_quality=first_seen` until the collector has actually run.

The same rule applies to vendor identifiers. A Bloomberg ticker, a field
mnemonic or an LSEG RIC that has not been confirmed inside an entitled session
is recorded as the literal sentinel `PENDING_VENDOR_DISCOVERY`, never as a
plausible guess: a wrong identifier either fails loudly or resolves to a
different statistic and silently poisons the stored history.

## Migration state

The original V0.1 collection code is preserved in Git history. Standalone repository trees were prepared before the research-only tree was created, so source ownership moved without losing provenance. The reviewed migration branches are `migration/desnz-standalone-v2` and `migration/defra-standalone-v2` in their owning repositories.
