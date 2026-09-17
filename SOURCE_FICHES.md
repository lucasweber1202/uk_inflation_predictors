# Verified source fiches for unimplemented predictor sources

Every fiche below was filled from the **live** source, most recently on **2026-09-17**, not from
the prior registry and not from memory. A collector must not be coded for a
source until its fiche is complete; where a field is still unknown, that is
recorded as unknown rather than guessed.

Implemented sources are documented in their own repositories
(`METHODOLOGY.md` and `POINT_IN_TIME.md` in `collector_desnz_uk`,
`collector_defra_uk`, `collector_dft_uk`, `collector_hmrc_uk` and
`collector_elexon_uk`). A fiche is removed from this file once its source is
implemented **and certified**; what remains below is the set that is not both.
`brc_shop_price_monitor` and `cbi_economic_surveys` are implemented but not yet
certified against a live vendor session, so their fiches stay here and record
exactly what is still open.

---

## `brc_shop_price_monitor` — RESOLVED (environment-gated)

| Field | Finding |
| --- | --- |
| PUBLISHER | British Retail Consortium (compiled with NIQ) |
| LANDING_PAGE | `https://brc.org.uk/market-intelligence/publications/monitors/shop-price-monitor/` |
| DELIVERY_ROUTE | Bloomberg Terminal / LSEG Workspace, under the desk's own entitlement |
| LICENSED_PRODUCT | BRC's historical datasets and monthly Excel reports remain subscription products. That is unchanged; what changed is that the desk holds a licensed route to the data. |
| FREQUENCY / HISTORY | monthly / stated from 2005; the history a given provider actually carries is unconfirmed |
| RELEASE_RULE | approximately ten days before ONS CPI, at 00:01 Europe/London |
| PIT | A vendor backfill carries no publication timestamp, so history is `first_seen` at the collection instant and is never backdated. The release rule is stored as metadata and is never used as availability evidence. |

**Resolved, with an environment gate.** The earlier blocker asserted that lawful
collection was impossible. That conflated the publisher's licensing with the
desk's access: BRC data is distributed through Bloomberg and LSEG, both of which
the desk is licensed for, so the source is not economically blocked. No news
page is scraped and no series is reconstructed from article text.

`collector_brc_uk` is implemented: five canonical year-on-year series plus six
optional MoM/index series defined, both provider adapters, canonical contract,
point-in-time handling, vintages, idempotency and 79 offline tests that pass
with no vendor library installed.

**What is still open** is environment-bound only: entitlement confirmation, the
vendor identifiers — every one of which ships as `PENDING_VENDOR_DISCOVERY`
rather than a guess — and a live certification run. `LIVE_VENDOR_SMOKE = SKIP`,
reason: no corporate terminal or session available. See
`collector_brc_uk/VENDOR_INTEGRATION.md` for the runbook.

## `cbi_economic_surveys` — RESOLVED (environment-gated)

| Field | Finding |
| --- | --- |
| PUBLISHER | Confederation of British Industry |
| LANDING_PAGE | `https://www.cbi.org.uk/economics/surveys/` |
| DELIVERY_ROUTE | Bloomberg Terminal / LSEG Workspace, under the desk's own entitlement |
| SCOPE | Distributive Trades (monthly), Industrial Trends (monthly), Service Sector (quarterly). 27 canonical series covering the price and cost side plus the demand context needed to read it. |
| LICENSED_PRODUCT | CBI licenses its survey data directly. That is unchanged; what changed is that the desk holds a licensed route to it. |
| FORMAT / API | vendor API (`blpapi` / `lseg.data`); no open historical CSV, XLSX or JSON API |
| PIT | A vendor backfill carries no publication timestamp, so history is `first_seen` at the collection instant and is never backdated. |

**Resolved, with an environment gate**, on the same grounds as `brc`.

`collector_cbi_uk` is implemented. Four dimensions are stored as columns and
never collapsed — `survey`, `sector`, `measure` (current vs expected) and
`stance` — because merging a current and an expected balance would build a
look-ahead into the data model that no downstream point-in-time machinery could
undo, and because "CBI selling prices" is three different series from three
different surveys. Capacity utilisation is excluded as a capacity rather than a
price measure. 89 offline tests pass with no vendor library installed.

**What is still open** is environment-bound only: entitlement, the vendor
identifiers — all 54 cells ship as `PENDING_VENDOR_DISCOVERY` — and a live
certification run. `LIVE_VENDOR_SMOKE = SKIP`, reason: no corporate terminal or
session available. The quarterly Service Sector history is the least certain of
the three and stays pending rather than being stitched if a provider's history
turns out to be discontinuous. See `collector_cbi_uk/VENDOR_INTEGRATION.md`.

## `ofgem_energy_price_cap` — RESOLVED

| Field | Finding |
| --- | --- |
| PUBLISHER | Ofgem |
| LANDING_PAGE | `https://www.ofgem.gov.uk/information-consumers/energy-advice-households/energy-price-cap-unit-rates-and-standing-charges` |
| DIRECT_ARTIFACTS | **None found.** No CSV, XLSX or ODS link in the served HTML. |
| ARTIFACT_DISCOVERY_RULE | Not establishable. Regional tables are rendered client-side (Drupal/JS); the served page carries one summary table covering only the current and next cap period. |
| FORMAT | HTML only |
| FREQUENCY | quarterly cap periods |
| HISTORY_START | unknown — published reporting indicates the full historic series has only been obtained via FOI |
| RELEASE_DATE_RULE | not establishable from the site |
| AVAILABLE_AT_RULE | **must** be the announcement instant, never the effective date |
| EFFECTIVE_DATE_RULE | `reference_date` = first day of the cap period; the cap is knowable well before it |

The earlier blocker was resolved by locating the official Annex 9 final
levelised cap-rates XLSX. It is implemented on `collector_ofgem_uk` main. The
collector preserves announcement availability separately from effective cap
periods and marks unproven historical publication times `first_seen`.

---

## `hmrc_tobacco_duty_rates` / `hmrc_alcohol_duty_rates` — BLOCKED

Re-investigated 2026-09-16. The live rate histories are published at:

- `https://www.gov.uk/government/statistics/tobacco-bulletin/historical-tobacco-duty-rates`
  — rates back to 1978, **2 HTML tables, no attachment**
- `https://www.gov.uk/government/statistics/alcohol-bulletin/alcohol-bulletin-historic-duty-rates`
  — **18 HTML tables, no attachment**

| Field | Finding |
| --- | --- |
| DIRECT_ARTIFACTS | **None.** Neither page carries a CSV, ODS or XLSX. |
| RELEASE_DATE_RULE | GOV.UK change-history timestamps give announcement dates |

A duty rate is a **tax parameter**, not activity data, and is usually announced
ahead of the date it takes effect. `announcement_date`, `effective_date` and
`reference_date` are three different things, and the rate becomes knowable at the
announcement. Blocked pending either a machine-readable artifact or an explicit
decision to parse the HTML tables.

---

## `orr_rail_fares_index` — RESOLVED

| Field | Finding |
| --- | --- |
| PUBLISHER | Office of Rail and Road |
| DIRECT_ARTIFACTS | **Not found.** The guessed data-portal URLs for tables 7180 and 7182 both returned **404**, and portal search surfaced no fares table to an automated request (the portal is probably client-rendered). |
| FREQUENCY | unknown |
| SCOPE | fares only — regulated, unregulated, ticket type, overall. Passenger usage is a different series and is out of scope even though it sits in the same portal area. |

Official ODS tables 7180 and 7182 were found and are implemented on
`collector_orr_uk` main. They supply 54 annual series and 1,348 observations
from 1995 through 2026 without HTML scraping.


---

## Resolved this round

These fiches were completed and their sources implemented, so they no longer
appear above:

| Source | Outcome |
| --- | --- |
| `dft_bus_fares` | implemented in `collector_dft_uk` — quarterly, 2005-03, 16 series |
| `hmrc_tobacco_bulletin` | implemented in `collector_hmrc_uk` — monthly, 1991-01, 10 series |
| `hmrc_alcohol_bulletin` | implemented in `collector_hmrc_uk` — monthly, 2023-08, 48 series |
| `elexon_market_index_prices` | implemented in `collector_elexon_uk` — half-hourly, 2016-09-12 |

The three Elexon blockers recorded in the previous round were all resolved
before any parser was written:

- **Licence** — Elexon grants a worldwide, royalty-free, perpetual,
  non-exclusive licence to copy, adapt and exploit BMRS data commercially,
  subject to the attribution "Contains BMRS data © Elexon Limited copyright and
  database right". Automation and historical storage are permitted.
- **History start** — bisected to **2016-09-12** (partial day); the first full
  day is 2016-09-13.
- **The N2EXMIDP zeros** — the first hypothesis, that the provider is entirely
  silent, was **wrong**. Sampling eleven days suggested it; the full history
  disproved it. `N2EXMIDP` reports in 501 of 172,666 periods across 168
  distinct dates, with real values from -65.8 to 450.23 GBP/MWh. The correct
  rule is not provider exclusion but a placeholder rule: a row whose price
  **and** volume are both exactly zero is a non-reporting placeholder and is
  skipped, for either provider. Six rows in the full history carry a zero price
  with a real volume and are genuine trades, so the conjunction matters.
