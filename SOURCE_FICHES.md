# Verified source fiches for unimplemented predictor sources

Every fiche below was filled from the **live** source on **2026-09-16**, not from
the prior registry and not from memory. A collector must not be coded for a
source until its fiche is complete; where a field is still unknown, that is
recorded as unknown rather than guessed.

Implemented sources are documented in their own repositories
(`METHODOLOGY.md` and `POINT_IN_TIME.md` in `collector_desnz_uk`,
`collector_defra_uk`, `collector_dft_uk`, `collector_hmrc_uk` and
`collector_elexon_uk`). A fiche is removed from this file once its source is
implemented; what remains below is the unimplemented set.

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

## `orr_rail_fares_index` — UNVERIFIED

| Field | Finding |
| --- | --- |
| PUBLISHER | Office of Rail and Road |
| DIRECT_ARTIFACTS | **Not found.** The guessed data-portal URLs for tables 7180 and 7182 both returned **404**, and portal search surfaced no fares table to an automated request (the portal is probably client-rendered). |
| FREQUENCY | unknown |
| SCOPE | fares only — regulated, unregulated, ticket type, overall. Passenger usage is a different series and is out of scope even though it sits in the same portal area. |

The current table identifiers and a machine-readable artifact must be confirmed
manually before any code is written.


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
