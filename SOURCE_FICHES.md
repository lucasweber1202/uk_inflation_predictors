# Verified source fiches for unimplemented predictor sources

Every fiche below was filled from the **live** source on **2026-09-16**, not from
the prior registry and not from memory. A collector must not be coded for a
source until its fiche is complete; where a field is still unknown, that is
recorded as unknown rather than guessed.

Implemented sources are documented in their own repositories
(`METHODOLOGY.md` and `POINT_IN_TIME.md` in `collector_desnz_uk` and
`collector_defra_uk`).

---

## `ofgem_energy_price_cap` — BLOCKED

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

**Blocker.** The Ofgem data portal and site search return no cap dataset, and the
site is in BETA. Building an HTML scraper is explicitly out of scope, so this
source stays blocked until an official machine-readable artifact or API is
identified manually. This is the reason Phase 4 did not proceed to code.

---

## `elexon_market_index_prices` — VIABLE

| Field | Finding |
| --- | --- |
| PUBLISHER | Elexon (BMRS) |
| DIRECT_ARTIFACTS | `https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index?from=…&to=…&format=json` |
| API | REST, JSON, **no authentication required** (verified) |
| FORMAT | JSON |
| FIELDS | `startTime`, `dataProvider`, `settlementDate`, `settlementPeriod`, `price`, `volume` |
| SERIES | providers observed: `APXMIDP`, `N2EXMIDP`; measures: price, volume |
| FREQUENCY | half-hourly (settlement periods) |
| HISTORY_START | unknown — data returned for 2018-06 and 2021-06, **not** for 2015-01. Bisect before coding. |
| SERIES_ID_RULE | `ELEXON_MID_{PROVIDER}_{PRICE\|VOLUME}_SP{NN}` |
| REFERENCE_DATE_RULE | `reference_date = settlementDate` |
| MISSING_VALUE_RULE | `N2EXMIDP` returned `price = 0.00` across the sampled window — characterise this before treating it as a real level or as missing |
| LICENSE | **unknown — confirm before use** |

`time_series.reference_date` is a `DATE`, so the settlement period is encoded in
`series_id` rather than added as a column, exactly as the brief specifies. This
is coherent with the current contract: the primary key stays
`(series_id, reference_date, vintage_date)` and each settlement period becomes
its own series. Settlement periods run 1–50 on clock-change days, so the
identifier must be zero-padded to two digits and the 49/50 cases tested.
Aggregation to daily, monthly or MTD belongs to `uk_inflation_predictors`.

---

## `dft_bus_fares` (BUS0415) — VIABLE, and the old registry was wrong

| Field | Finding |
| --- | --- |
| PUBLISHER | Department for Transport |
| LANDING_PAGE | `https://www.gov.uk/government/statistical-data-sets/bus-statistics-data-tables` |
| DIRECT_ARTIFACTS | `bus0415.ods` (discovered on the page; the URL carries a content hash) |
| FORMAT | ODS, two sheets: `BUS0415a` (current prices), `BUS0415b` (real terms) |
| **FREQUENCY** | **quarterly** — Year/Month columns take only Mar, Jun, Sep, Dec. The prior registry said *annual*; that was **wrong**. |
| HISTORY_START | 2005-03, base **March 2005 = 100**, 85 observations to 2026-03 |
| SERIES | London, English metropolitan areas, English non-metropolitan areas, England, Scotland, Wales, Great Britain, England outside London |
| SERIES_ID_RULE | encode the base year, as for the DEFRA index, so a rebasing creates new series |
| **SCOPE WARNING** | `BUS0415a` also carries **RPI, CPI and CPIH comparator columns**. Those are ONS *target* data and must **not** be collected in a predictor repository — they belong to `collector_ons_cpi`. |

---

## `hmrc_tobacco_bulletin` / `hmrc_alcohol_bulletin` — VIABLE

| Field | Finding |
| --- | --- |
| PUBLISHER | HM Revenue & Customs |
| DIRECT_ARTIFACTS | `Tobacco_Tab_Jul_26.ods`; `Alcohol_Tables_Jul26.ods` |
| FORMAT | ODS on GOV.UK |
| RELEASE_DATE_RULE | GOV.UK change history: **45** timestamps (tobacco), **48** (alcohol) |
| FREQUENCY | monthly |
| HISTORY_START | unknown — sheet layout and history still to be verified |

Both are ordinary GOV.UK publication pages, so the existing `govuk.py` helper and
the standard release-attribution path apply unchanged. These are **clearances and
receipts**, i.e. activity data.

## `hmrc_tobacco_duty_rates` / `hmrc_alcohol_duty_rates` — PARTIALLY BLOCKED

| Field | Finding |
| --- | --- |
| LANDING_PAGE | `https://www.gov.uk/government/publications/rates-and-allowances-excise-duty-tobacco-duty`; `https://www.gov.uk/guidance/alcohol-duty-rates` (the previously registered alcohol URL 404s) |
| DIRECT_ARTIFACTS | **None.** Rates are published as HTML tables with no CSV/ODS/XLSX attachment. |
| RELEASE_DATE_RULE | 13 change-history timestamps on the tobacco page give announcement dates |

A duty rate is a **tax parameter**, not activity data, and is usually announced
ahead of the date it takes effect. `announcement_date`, `effective_date` and
`reference_date` are three different things, and the rate becomes knowable at the
announcement. Blocked pending either a machine-readable artifact or an explicit
decision to parse the HTML tables.

---

## `orr_rail_fares_index` — UNVERIFIED

| Field | Finding |
| --- | --- |
| PUBLISHER | Office of Rail and Road |
| DIRECT_ARTIFACTS | **Not found.** The guessed data-portal URLs for tables 7180 and 7182 both returned **404**, and portal search surfaced no fares table to an automated request (the portal is probably client-rendered). |
| FREQUENCY | unknown |
| SCOPE | fares only — regulated, unregulated, ticket type, overall. Passenger usage is a different series and is out of scope even though it sits in the same portal area. |

The current table identifiers and a machine-readable artifact must be confirmed
manually before any code is written.
