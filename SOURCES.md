# Sources

`source_registry.csv` is the machine-readable register. This document records
what was verified against each official source, and what was not.

Every field that could not be confirmed on the official source is recorded as
`unknown` in the registry. No API, licence, history start or revision policy is
asserted from assumption.

---

## Implemented

### `desnz_road_fuels` — Weekly road fuel prices

- **Publisher:** Department for Energy Security and Net Zero
- **Page:** https://www.gov.uk/government/statistics/weekly-road-fuel-prices
- **Licence:** Open Government Licence v3.0 (stated on the page)
- **Frequency:** weekly · **History:** 2003-06-09 → present
- **Format:** two CSV attachments, both needed for the full history:
  - `weekly_road_fuel_prices_2003_to_2017.csv` — frozen historic file
  - `CSV__2018_-__.csv` — current file, 2018 to the latest week

Attachment URLs embed a content hash that changes on every republication, so
both are discovered from the live page each run rather than pinned in code. An
ambiguous or missing match fails the run.

**Verified layout** (identical in both files):

```
Date,
ULSP (Ultra low sulphur unleaded petrol) Pump price in pence/litre,
ULSD (Ultra low sulphur diesel) Pump price in pence/litre,
ULSP (Ultra low sulphur unleaded petrol) Duty rate in pence/litre,
ULSD (Ultra low sulphur diesel) Duty rate in pence/litre,
ULSP (Ultra low sulphur unleaded petrol) VAT percentage rate,
ULSD (Ultra low sulphur diesel) VAT percentage rate
```

Dates are `dd/mm/yyyy`. Reference dates are Mondays, with a handful of
bank-holiday shifts: measured gaps over the full history are 5, 6, 7, 8 and 9
days, 1,202 of 1,214 being exactly 7.

**Six series collected** — pump price, duty rate and VAT rate for each of
unleaded petrol (ULSP) and diesel (ULSD). The user's minimum was petrol and
diesel pump prices; duty and VAT rates are collected alongside because they are
published in the same file and are direct, pre-announced CPI drivers.

Data is kept at the published **weekly** frequency and is not converted to
monthly.

**Not verified:** DESNZ publishes no revision policy on this page, so
`revision_policy` is `unknown`. The weekly release rule (next working day,
08:30 UTC) is *observed* from the page's change history, not documented by the
source, which is why it only ever produces `inferred` availability.

### `defra_fruit_veg` — Wholesale fruit and vegetable prices

- **Publisher:** Department for Environment, Food & Rural Affairs
- **Page:** https://www.gov.uk/government/statistical-data-sets/wholesale-fruit-and-vegetable-prices-weekly-average
- **Licence:** Open Government Licence v3.0 (stated on the page)
- **Frequency:** irregular · **History:** 2015-01-09 → present
- **Format:** official historical ODS plus tidy machine-readable CSV:
  - `fruitveg-weeklyhort-YYMMDD.ods` — maximum official history, from 2015
  - `fruitvegprices-YYMMDD.csv` — modern machine-readable observations, from 2017

The CSV layout is `category,item,variety,date,price,unit`; dates are ISO
`YYYY-MM-DD`. The ODS contains year and legacy combined worksheets. Both
artifacts preserve GBP prices and the published physical unit.

**127 series collected** in the source artifact verified on 2026-09-15.
Product, price, unit and reference date are all preserved: the physical unit
(`kg`, `head`, `twin`, `unit`) carries into the series name and description,
because the fleet `unit` column can only say `currency`. A series that ever
appeared in two different units would fail the run.

**Overlap rule.** The ODS and CSV must overlap. Identifiers, dates and units are
normalized consistently; the CSV wins deterministically in the overlapping
period. Differences up to £0.01 are accepted because the workbook displays
some values at lower precision. Any larger unexplained difference fails the
run. No value is invented to fill a gap.

**Scope filter.** The same file also publishes `cut_flowers` and `pot_plants`.
These are horticultural products that do not enter consumer food prices and are
excluded explicitly. A category that is neither collected nor in the known
ignore-list is reported as a warning, so a new upstream category cannot pass
unnoticed.

**No aggregate index is built.** No food, fruit or vegetable composite is
constructed, as that would be a modelling decision.

**Frequency is `irregular`, deliberately.** The page title says "weekly
average" and the dataset description says "fortnightly". Neither matches the
data: measured gaps are 7 days (348), 14 days (42), 21 days (6), 28 days (2) and
31 days (1), and the recent regime is fortnightly while the bulk of the history
is weekly. The reference weekday also switched from Friday to Monday. `weekly`
and `biweekly` would both be false for part of the history, so the honest fleet
label is `irregular`, with the true cadence recoverable from the reference dates
themselves.

**Point in time:** GOV.UK change history proves timestamps for the modern
period. Earlier ODS history is retained as `availability_basis=inferred`, so it
is excluded from evidence-backed as-of queries by default. DEFRA publishes no
revision policy on this page.

---

## Current implementation state

The machine-readable registry is authoritative for the complete list. As of
2026-09-17, the following source families are implemented on their standalone
collector `main` branches: DESNZ road fuels; four DEFRA datasets; DfT bus
fares; HMRC tobacco and alcohol bulletins; Elexon market-index prices; Ofgem
price-cap rates; ORR rail fares; ONS PPI/SPPI, AWE, BICS and private rents; BoE
FX and DMP. Their detailed source semantics live in each collector's
`METHODOLOGY.md` and `POINT_IN_TIME.md`.

`implemented_verified` is reserved for a collector already merged to `main`
whose source smoke, fresh-build, idempotency, revision, snapshot and as-of
tests have passed. A PR or branch alone is not enough.

## Licensed sources reached through a delivery provider

Both sources below are licensed by their publisher and have no open
machine-readable archive. Neither is economically blocked, because the desk
holds a licensed route to them: Bloomberg Terminal and/or LSEG Workspace. The
publisher remains the publisher — `metadata.original_publisher` names BRC or
CBI, and the delivery provider is recorded per observation. Nothing is scraped
from a news page and no series is reconstructed from article text.

| source_id | What is collected | Remaining gate |
|---|---|---|
| `brc_shop_price_monitor` | Overall, food, fresh-food, ambient-food and non-food shop-price rates, obtained through a licensed delivery provider (Bloomberg/LSEG) rather than a public release. | Implemented in `collector_brc_uk`; the remaining gate is entitlement, vendor identifier discovery and live certification. Redistribution remains out of scope. |
| `cbi_economic_surveys` | Distributive Trades, Industrial Trends and Service Sector balances, obtained through a licensed delivery provider (Bloomberg/LSEG) rather than a public release. | Implemented in `collector_cbi_uk`; the remaining gate is entitlement, vendor identifier discovery and live certification. Redistribution remains out of scope. |

Both now have a collector repository and `predictor_map.csv` entries. Those
entries are hypotheses about the economic channel: every one carries
`research_status=not_started` and `point_in_time_quality=first_seen` until a
live vendor query has actually run. No vendor identifier is recorded until it
has been confirmed inside an entitled session; unconfirmed cells hold the
literal sentinel `PENDING_VENDOR_DISCOVERY`. `SOURCE_FICHES.md` records what is
still open for each, and each repository's `VENDOR_INTEGRATION.md` is the
corporate-machine runbook.

## Other unimplemented or dataset-level blockers

- HMRC tobacco and alcohol duty-rate histories remain HTML-only; the two
  implemented bulletins are unaffected.
- Ofcom, Auto Trader and commercial rental feeds remain candidates pending an
  automatable licensed artifact.
- Scraping rental portals, retailers or commercial survey pages is out of
  scope. Obtaining a licensed publisher's data through a delivery provider the
  desk is entitled to is not scraping and is the route used for BRC and CBI.
