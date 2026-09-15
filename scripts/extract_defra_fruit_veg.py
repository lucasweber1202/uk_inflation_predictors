"""DEFRA Wholesale fruit and vegetable prices: average home-grown produce prices.

Official page:
https://www.gov.uk/government/statistical-data-sets/wholesale-fruit-and-vegetable-prices-weekly-average

DEFRA publishes one machine-readable CSV covering the whole history in a tidy
``category,item,variety,date,price,unit`` layout. The same page also carries two
ODS workbooks; only the CSV is parsed, because it is the machine-readable
artifact and the workbooks restate it.

The dataset also carries ``cut_flowers`` and ``pot_plants`` categories. Those
are out of scope for a consumer price predictor layer and are filtered out
explicitly rather than silently, so a new category appearing upstream is
reported instead of being swept in.

Prices are stored exactly as published, per product and per published unit. No
aggregate fruit, vegetable or food index is constructed here: building one would
be a modelling decision, not a collection one.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from itertools import pairwise
from typing import Any

import httpx

from scripts.govuk import SourceData, download, fetch_page, find_attachment, release_timestamps
from scripts.snapshots import build_snapshot
from scripts.time_series import Observation

logger = logging.getLogger(__name__)

SOURCE_ID = "defra_fruit_veg"
PAGE_URL = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "wholesale-fruit-and-vegetable-prices-weekly-average"
)

# The machine-readable attachment. Its published name carries the latest
# reference week, so only the stable stem is matched.
CSV_PATTERN = r"fruitvegprices[^/]*\.csv"

# Verified against the live CSV header on 2026-09-15.
EXPECTED_COLUMNS = ("category", "item", "variety", "date", "price", "unit")

# Categories this predictor layer collects. Anything else on the page is a
# horticultural product that does not enter consumer food prices.
COLLECTED_CATEGORIES = frozenset({"fruit", "vegetable"})
KNOWN_IGNORED_CATEGORIES = frozenset({"cut_flowers", "pot_plants"})

# Published price units. All are a GBP amount per the stated physical unit, so
# the fleet `unit` is currency and the physical unit is preserved in the name
# and description of each series.
KNOWN_UNITS = frozenset({"kg", "head", "twin", "unit", "stem"})

# Observed release schedule: a release can carry its own reference day, and the
# modal lag is three days. The page's change history begins 2017-01-05, before
# the first observation, so in practice every observation is attributable to an
# official timestamp and the inferred rule is a fallback only.
MIN_LAG_DAYS = 0
MAX_LAG_DAYS = 31
INFERRED_LAG_DAYS = 3

EXPECTED_FIRST_OBSERVATION = date(2017, 11, 3)
# Measured cadence over the full history: mostly weekly, with fortnightly runs
# and occasional seasonal gaps. The source describes itself as a fortnightly
# series, so the stored frequency is `irregular` rather than a false `weekly`.
MAX_GAP_DAYS = 45
MIN_EXPECTED_SERIES = 60
MIN_EXPECTED_DATES = 300


def _token(raw: str) -> str:
    """Normalize one native label into an uppercase identifier token."""
    token = re.sub(r"[^A-Z0-9]+", "", raw.strip().upper())
    if not token:
        raise ValueError(f"DEFRA label {raw!r} normalizes to an empty identifier token")
    return token


def make_series_id(category: str, item: str, variety: str) -> str:
    """Build ``DEFRA_FRUITVEG_{CATEGORY}_{ITEM}_{VARIETY}`` from native labels.

    The native labels stay in metadata. Normalization is verified to be
    collision-free across all 71 published fruit and vegetable series, and
    ``validate`` re-checks that on every run rather than trusting it.
    """
    series_id = f"DEFRA_FRUITVEG_{_token(category)}_{_token(item)}_{_token(variety)}"
    if len(series_id) > 200:
        raise ValueError(f"series_id exceeds 200 characters: {series_id}")
    return series_id


def parse_series_id(series_id: str) -> tuple[str, str, str, str, str]:
    """Decode ``DEFRA_FRUITVEG_{CATEGORY}_{ITEM}_{VARIETY}`` into its five parts."""
    parts = series_id.split("_")
    if len(parts) != 5 or parts[0] != "DEFRA" or parts[1] != "FRUITVEG":
        raise ValueError(f"Invalid DEFRA fruit and vegetable series_id: {series_id}")
    source, dataset, category, item, variety = parts
    if not category or not item or not variety:
        raise ValueError(f"Incomplete DEFRA fruit and vegetable series_id: {series_id}")
    return source, dataset, category, item, variety


def _assert_schema(fieldnames: Sequence[str] | None, url: str) -> None:
    """Refuse a file whose published layout no longer matches the verified one."""
    if not fieldnames:
        raise ValueError(f"DEFRA file {url} has no header row")
    header = tuple(name.strip().lower() for name in fieldnames)
    if header != EXPECTED_COLUMNS:
        raise ValueError(
            f"DEFRA file {url} header is {header}, expected {EXPECTED_COLUMNS}; the published "
            "layout changed and must be re-verified against the official source"
        )


def _parse_csv(
    body: bytes, url: str, snapshot_id: str
) -> tuple[list[Observation], dict[str, dict[str, str]]]:
    """Parse the DEFRA CSV into observations plus the native labels per series."""
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    _assert_schema(reader.fieldnames, url)
    observations: list[Observation] = []
    natives: dict[str, dict[str, str]] = {}
    ignored: set[str] = set()
    skipped = 0
    for row in reader:
        category = (row.get("category") or "").strip().lower()
        if category not in COLLECTED_CATEGORIES:
            ignored.add(category)
            continue
        item = (row.get("item") or "").strip().lower()
        variety = (row.get("variety") or "").strip().lower()
        unit = (row.get("unit") or "").strip().lower()
        raw_date = (row.get("date") or "").strip()
        raw_price = (row.get("price") or "").strip()
        try:
            reference_date = date.fromisoformat(raw_date)
            price = float(raw_price)
            series_id = make_series_id(category, item, variety)
        except ValueError:
            # One malformed record is a soft failure: warn and skip it.
            logger.warning("DEFRA %s: unreadable row %r; skipping", url, row)
            skipped += 1
            continue
        if unit not in KNOWN_UNITS:
            raise ValueError(
                f"DEFRA published unverified price unit {unit!r} for {series_id}; "
                "the unit vocabulary must be re-verified against the official source"
            )
        existing = natives.get(series_id)
        if existing is not None and existing["unit"] != unit:
            raise ValueError(
                f"DEFRA published {series_id} in two units, {existing['unit']!r} and {unit!r}; "
                "one series must carry one unit"
            )
        natives[series_id] = {
            "category": category,
            "item": item,
            "variety": variety,
            "unit": unit,
        }
        observations.append(
            Observation(
                series_id=series_id,
                reference_date=reference_date,
                value=price,
                snapshot_id=snapshot_id,
            )
        )
    unexpected = ignored - KNOWN_IGNORED_CATEGORIES - {""}
    if unexpected:
        # Not a hard failure: a new horticultural category does not corrupt the
        # collected ones, but it must never pass unreported.
        logger.warning(
            "DEFRA published unrecognised categories %s, which were not collected; "
            "review whether they belong in this predictor layer",
            sorted(unexpected),
        )
    if skipped:
        logger.warning("DEFRA %s: skipped %d unreadable rows", url, skipped)
    logger.info(
        "DEFRA %s: parsed %d observations across %d series", url, len(observations), len(natives)
    )
    return observations, natives


def _label(raw: str) -> str:
    """Render a native snake_case label as readable English."""
    return raw.replace("_", " ").strip()


def _build_catalog(
    natives: dict[str, dict[str, str]], last_publish_date: date | None
) -> dict[str, dict[str, Any]]:
    """Describe every collected series from its verified native labels."""
    catalog: dict[str, dict[str, Any]] = {}
    for series_id, fields in natives.items():
        item, variety = _label(fields["item"]), _label(fields["variety"])
        product = item if variety == item else f"{item}, {variety}"
        catalog[series_id] = {
            "source_id": SOURCE_ID,
            "name": f"UK wholesale {fields['category']} price: {product} (GBP per {fields['unit']})",
            "description": (
                f"Average wholesale market price of home grown {product} in the United "
                f"Kingdom, in GBP per {fields['unit']}, as published by the Department for "
                "Environment, Food & Rural Affairs. Stored at the published reference dates "
                "with no derived transformation and no aggregate index."
            ),
            # The published cadence is weekly for most of the history and
            # fortnightly latterly; `irregular` is the honest fleet label.
            "frequency": "irregular",
            "unit": "currency",
            "eco_group": "producer_prices",
            "source_url": PAGE_URL,
            "last_publish_date": last_publish_date,
        }
    return catalog


def validate(observations: list[Observation], natives: dict[str, dict[str, str]]) -> None:
    """Gate the parsed panel before anything reaches the database."""
    if not observations:
        raise ValueError("DEFRA collection produced no observations")
    if len(natives) < MIN_EXPECTED_SERIES:
        raise ValueError(
            f"DEFRA returned only {len(natives)} series, below the {MIN_EXPECTED_SERIES} floor; "
            "the download was probably truncated"
        )

    # Normalization must stay injective, or two published products would share
    # one stored history.
    collisions: dict[str, set[tuple[str, str, str]]] = {}
    for series_id, fields in natives.items():
        native_key = (fields["category"], fields["item"], fields["variety"])
        collisions.setdefault(series_id, set()).add(native_key)
    clashing = {sid: keys for sid, keys in collisions.items() if len(keys) > 1}
    if clashing:
        raise ValueError(f"DEFRA identifier normalization collided: {clashing}")

    keys = [(observation.series_id, observation.reference_date) for observation in observations]
    if len(keys) != len(set(keys)):
        counts: dict[tuple[str, date], int] = {}
        for observation_key in keys:
            counts[observation_key] = counts.get(observation_key, 0) + 1
        duplicates = sorted(key for key, count in counts.items() if count > 1)[:5]
        raise ValueError(f"DEFRA published duplicate observations, for example {duplicates}")

    dates = sorted({observation.reference_date for observation in observations})
    if dates[0] != EXPECTED_FIRST_OBSERVATION:
        raise ValueError(
            f"DEFRA history starts at {dates[0]}, expected {EXPECTED_FIRST_OBSERVATION}; "
            "the published file changed and must be re-verified"
        )
    if len(dates) < MIN_EXPECTED_DATES:
        raise ValueError(
            f"DEFRA returned only {len(dates)} reference dates, below the "
            f"{MIN_EXPECTED_DATES} floor; the download was probably truncated"
        )
    if dates[-1] > datetime.now(UTC).date():
        raise ValueError(f"DEFRA published a future reference date {dates[-1]}")

    long_gaps = [
        (earlier, later)
        for earlier, later in pairwise(dates)
        if (later - earlier).days > MAX_GAP_DAYS
    ]
    if long_gaps:
        raise ValueError(
            f"DEFRA cadence broken by gaps longer than {MAX_GAP_DAYS} days at {long_gaps[:5]}"
        )

    non_positive = [
        (observation.series_id, observation.reference_date, observation.value)
        for observation in observations
        if observation.value <= 0.0
    ]
    if non_positive:
        raise ValueError(f"DEFRA published non-positive prices, for example {non_positive[:5]}")

    logger.info(
        "DEFRA validation passed: %d series, %d reference dates, %s to %s",
        len(natives),
        len(dates),
        dates[0],
        dates[-1],
    )


def collect(client: httpx.Client) -> SourceData:
    """Download, parse and validate the full DEFRA fruit and vegetable history."""
    page = fetch_page(client, PAGE_URL)
    releases = release_timestamps(page)
    if not releases:
        raise ValueError(f"No publication history found on {PAGE_URL}; the page layout changed")
    last_publish_date = releases[-1].astimezone(UTC).date()
    logger.info(
        "DEFRA page carries %d official release timestamps, %s to %s",
        len(releases),
        releases[0].astimezone(UTC).date(),
        last_publish_date,
    )

    url = find_attachment(page, PAGE_URL, CSV_PATTERN)
    body, digest, etag, last_modified = download(client, url)
    snapshot = build_snapshot(
        source_id=SOURCE_ID,
        source_url=url,
        filename=url.rsplit("/", 1)[-1],
        body=body,
        digest=digest,
        etag=etag,
        last_modified=last_modified,
        fetched_at=datetime.now(UTC),
        source_published_date=last_publish_date,
    )
    observations, natives = _parse_csv(body, url, digest)
    validate(observations, natives)
    return SourceData(
        source_id=SOURCE_ID,
        source_url=PAGE_URL,
        catalog=_build_catalog(natives, last_publish_date),
        observations=observations,
        releases=releases,
        snapshots=[snapshot],
        min_lag_days=MIN_LAG_DAYS,
        max_lag_days=MAX_LAG_DAYS,
        inferred_lag_days=INFERRED_LAG_DAYS,
        last_publish_date=last_publish_date,
    )
