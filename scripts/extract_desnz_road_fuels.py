"""DESNZ Weekly road fuel prices: UK average pump prices, duty rates and VAT.

Official page:
https://www.gov.uk/government/statistics/weekly-road-fuel-prices

DESNZ publishes this series across two CSV attachments that must be stitched to
obtain the full history: a frozen 2003-2017 file and a current file running from
2018 to the latest week. Both carry the identical seven-column layout. The
attachment URLs embed a content hash that changes on every republication, so
both are discovered from the live page rather than pinned here.

Values are stored exactly as published, at the weekly frequency the source
publishes. No monthly average or any other transformation is derived.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime
from itertools import pairwise
from typing import Any

import httpx

from scripts.config import DOWNLOAD_DELAY
from scripts.govuk import SourceData, download, fetch_page, find_attachment, release_timestamps
from scripts.snapshots import Snapshot, build_snapshot
from scripts.time_series import Observation

logger = logging.getLogger(__name__)

SOURCE_ID = "desnz_road_fuels"
PAGE_URL = "https://www.gov.uk/government/statistics/weekly-road-fuel-prices"

# The two attachments, matched on the stable parts of their published file
# names. Each pattern must select exactly one link or collection fails loudly.
HISTORIC_PATTERN = r"weekly_road_fuel_prices_2003_to_2017[^/]*\.csv"
CURRENT_PATTERN = r"CSV__2018[^/]*\.csv"

DATE_COLUMN = "Date"
# Verified against the live CSV header on 2026-09-15. A column that is renamed
# or dropped upstream fails the schema gate below rather than being skipped.
COLUMN_SERIES = {
    "ULSP (Ultra low sulphur unleaded petrol) Pump price in pence/litre": (
        "ULSP",
        "PUMPPRICE",
    ),
    "ULSD (Ultra low sulphur diesel) Pump price in pence/litre": ("ULSD", "PUMPPRICE"),
    "ULSP (Ultra low sulphur unleaded petrol) Duty rate in pence/litre": ("ULSP", "DUTYRATE"),
    "ULSD (Ultra low sulphur diesel) Duty rate in pence/litre": ("ULSD", "DUTYRATE"),
    "ULSP (Ultra low sulphur unleaded petrol) VAT percentage rate": ("ULSP", "VATRATE"),
    "ULSD (Ultra low sulphur diesel) VAT percentage rate": ("ULSD", "VATRATE"),
}

PRODUCT_NAMES = {
    "ULSP": "ultra low sulphur unleaded petrol",
    "ULSD": "ultra low sulphur diesel",
}
MEASURE_FIELDS = {
    "PUMPPRICE": {
        "label": "pump price",
        "native_unit": "pence per litre",
        "unit": "currency",
        "eco_group": "consumer_prices",
    },
    "DUTYRATE": {
        "label": "duty rate",
        "native_unit": "pence per litre",
        "unit": "currency",
        "eco_group": "public_finance",
    },
    "VATRATE": {
        "label": "VAT rate",
        "native_unit": "percent",
        "unit": "percent",
        "eco_group": "public_finance",
    },
}

# Observed release schedule: DESNZ publishes on the working day after the Monday
# reference date, at 08:30 UTC. The change history reaches back to 2013-09-23
# only, so weeks before it are attributed by this rule and marked `inferred`.
MIN_LAG_DAYS = 1
MAX_LAG_DAYS = 31
INFERRED_LAG_DAYS = 1

# The first reference week DESNZ publishes in the 2003-2017 file. Collecting
# anything later than this from a fresh database means the historic attachment
# was truncated or silently replaced upstream.
EXPECTED_FIRST_OBSERVATION = date(2003, 6, 9)
# Weekly cadence. The source shifts a handful of weeks around bank holidays, so
# the measured gaps over the full 2003-2026 history are 5, 6, 7, 8 and 9 days
# (1202 of 1214 are exactly 7). A gap outside this set means a week was dropped.
ALLOWED_GAP_DAYS = frozenset({5, 6, 7, 8, 9})
MIN_EXPECTED_OBSERVATIONS = 1000


def make_series_id(product: str, measure: str) -> str:
    """Build ``DESNZ_ROADFUEL_{PRODUCT}_{MEASURE}`` from stable identifying fields."""
    product, measure = product.strip().upper(), measure.strip().upper()
    if product not in PRODUCT_NAMES or measure not in MEASURE_FIELDS:
        raise ValueError(f"Unknown DESNZ road fuel series identity: {product} {measure}")
    return f"DESNZ_ROADFUEL_{product}_{measure}"


def parse_series_id(series_id: str) -> tuple[str, str, str, str]:
    """Decode ``DESNZ_ROADFUEL_{PRODUCT}_{MEASURE}`` into its four stable parts."""
    parts = series_id.split("_")
    if len(parts) != 4 or parts[0] != "DESNZ" or parts[1] != "ROADFUEL":
        raise ValueError(f"Invalid DESNZ road fuel series_id: {series_id}")
    source, dataset, product, measure = parts
    if product not in PRODUCT_NAMES or measure not in MEASURE_FIELDS:
        raise ValueError(f"Unknown DESNZ road fuel series_id components: {series_id}")
    return source, dataset, product, measure


def _parse_reference_date(raw: str) -> date:
    """Parse the source's ``dd/mm/yyyy`` reference date.

    The source publishes a calendar date with no time or offset, and a
    reference period is a calendar period, so a naive parse is correct here.
    """
    return datetime.strptime(raw.strip(), "%d/%m/%Y").date()  # noqa: DTZ007


def _cell_float(raw: str) -> float | None:
    """Return a finite float for one cell, or None when it carries no number."""
    value = raw.strip().replace(",", "")
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _assert_schema(fieldnames: Sequence[str] | None, url: str) -> None:
    """Refuse a file whose published layout no longer matches the verified one."""
    if not fieldnames:
        raise ValueError(f"DESNZ file {url} has no header row")
    header = [name.strip() for name in fieldnames]
    if header[0] != DATE_COLUMN:
        raise ValueError(
            f"DESNZ file {url} first column is {header[0]!r}, expected {DATE_COLUMN!r}"
        )
    missing = sorted(set(COLUMN_SERIES) - set(header))
    if missing:
        raise ValueError(
            f"DESNZ file {url} is missing verified columns {missing}; the published layout "
            "changed and must be re-verified against the official source"
        )


def _parse_csv(body: bytes, url: str, snapshot_id: str) -> list[Observation]:
    """Parse one DESNZ CSV attachment into observations."""
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    _assert_schema(reader.fieldnames, url)
    observations: list[Observation] = []
    skipped = 0
    for row in reader:
        raw_date = (row.get(DATE_COLUMN) or "").strip()
        if not raw_date:
            continue
        try:
            reference_date = _parse_reference_date(raw_date)
        except ValueError:
            # A single unreadable date is a soft failure: warn and skip the row.
            logger.warning("DESNZ %s: unreadable date %r; skipping row", url, raw_date)
            skipped += 1
            continue
        for column, (product, measure) in COLUMN_SERIES.items():
            value = _cell_float(row.get(column) or "")
            if value is None:
                continue
            observations.append(
                Observation(
                    series_id=make_series_id(product, measure),
                    reference_date=reference_date,
                    value=value,
                    snapshot_id=snapshot_id,
                )
            )
    if skipped:
        logger.warning("DESNZ %s: skipped %d unreadable rows", url, skipped)
    logger.info("DESNZ %s: parsed %d observations", url, len(observations))
    return observations


def _build_catalog(last_publish_date: date | None) -> dict[str, dict[str, Any]]:
    """Describe every series this source publishes, derived from its identifier."""
    catalog: dict[str, dict[str, Any]] = {}
    for product, product_name in PRODUCT_NAMES.items():
        for measure, fields in MEASURE_FIELDS.items():
            series_id = make_series_id(product, measure)
            catalog[series_id] = {
                "source_id": SOURCE_ID,
                "name": f"UK weekly road fuel {fields['label']}: {product_name}",
                "description": (
                    f"United Kingdom average weekly {fields['label']} for {product_name}, "
                    f"measured in {fields['native_unit']}, as published by the Department for "
                    "Energy Security and Net Zero. Stored at the published weekly frequency "
                    "with no derived transformation."
                ),
                "frequency": "weekly",
                "unit": fields["unit"],
                "eco_group": fields["eco_group"],
                "source_url": PAGE_URL,
                "last_publish_date": last_publish_date,
            }
    return catalog


def validate(observations: list[Observation]) -> None:
    """Gate the parsed panel before anything reaches the database.

    These are structural checks: a failure means the source changed shape or the
    download was partial, and persisting the result would corrupt the stored
    history. Every one of them raises rather than warns.
    """
    if not observations:
        raise ValueError("DESNZ collection produced no observations")
    expected_series = {
        make_series_id(product, measure) for product in PRODUCT_NAMES for measure in MEASURE_FIELDS
    }
    seen_series = {observation.series_id for observation in observations}
    if seen_series != expected_series:
        raise ValueError(
            f"DESNZ series mismatch; missing={sorted(expected_series - seen_series)} "
            f"unexpected={sorted(seen_series - expected_series)}"
        )

    keys = [(observation.series_id, observation.reference_date) for observation in observations]
    if len(keys) != len(set(keys)):
        duplicates = sorted({key for key in keys if keys.count(key) > 1})[:5]
        raise ValueError(f"DESNZ published duplicate observations, for example {duplicates}")

    dates = sorted({observation.reference_date for observation in observations})
    if dates[0] != EXPECTED_FIRST_OBSERVATION:
        raise ValueError(
            f"DESNZ history starts at {dates[0]}, expected {EXPECTED_FIRST_OBSERVATION}; "
            "the historic 2003-2017 attachment changed and must be re-verified"
        )
    if len(dates) < MIN_EXPECTED_OBSERVATIONS:
        raise ValueError(
            f"DESNZ returned only {len(dates)} weeks, below the {MIN_EXPECTED_OBSERVATIONS} "
            "floor; the download was probably truncated"
        )
    if dates[-1] > datetime.now(UTC).date():
        raise ValueError(f"DESNZ published a future reference date {dates[-1]}")

    bad_gaps = [
        (earlier, later)
        for earlier, later in pairwise(dates)
        if (later - earlier).days not in ALLOWED_GAP_DAYS
    ]
    if bad_gaps:
        raise ValueError(
            f"DESNZ weekly cadence broken at {bad_gaps[:5]}; expected gaps of "
            f"{sorted(ALLOWED_GAP_DAYS)} days"
        )

    for observation in observations:
        _, _, _, measure = parse_series_id(observation.series_id)
        if measure == "VATRATE" and not 0.0 <= observation.value <= 100.0:
            raise ValueError(
                f"DESNZ VAT rate {observation.value} for {observation.reference_date} "
                "is not a percentage"
            )
        if measure != "VATRATE" and observation.value <= 0.0:
            raise ValueError(
                f"DESNZ {observation.series_id} has non-positive price "
                f"{observation.value} at {observation.reference_date}"
            )
    logger.info(
        "DESNZ validation passed: %d series, %d weeks, %s to %s",
        len(seen_series),
        len(dates),
        dates[0],
        dates[-1],
    )


def collect(client: httpx.Client) -> SourceData:
    """Download, parse and validate the full DESNZ weekly road fuel history."""
    page = fetch_page(client, PAGE_URL)
    releases = release_timestamps(page)
    if not releases:
        raise ValueError(f"No publication history found on {PAGE_URL}; the page layout changed")
    last_publish_date = releases[-1].astimezone(UTC).date()
    logger.info(
        "DESNZ page carries %d official release timestamps, %s to %s",
        len(releases),
        releases[0].astimezone(UTC).date(),
        last_publish_date,
    )

    observations: list[Observation] = []
    snapshots: list[Snapshot] = []
    for pattern in (HISTORIC_PATTERN, CURRENT_PATTERN):
        url = find_attachment(page, PAGE_URL, pattern)
        body, digest, etag, last_modified = download(client, url)
        snapshots.append(
            build_snapshot(
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
        )
        observations.extend(_parse_csv(body, url, digest))
        time.sleep(DOWNLOAD_DELAY)

    validate(observations)
    return SourceData(
        source_id=SOURCE_ID,
        source_url=PAGE_URL,
        catalog=_build_catalog(last_publish_date),
        observations=observations,
        releases=releases,
        snapshots=snapshots,
        min_lag_days=MIN_LAG_DAYS,
        max_lag_days=MAX_LAG_DAYS,
        inferred_lag_days=INFERRED_LAG_DAYS,
        last_publish_date=last_publish_date,
    )
