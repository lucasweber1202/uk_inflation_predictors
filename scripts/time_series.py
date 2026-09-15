"""Idempotent, vintage-preserving persistence of raw published observation levels.

Only the level published by the source is stored. No month-on-month, year-on-
year, monthly average, month-to-date, rolling-window, diffusion or volatility
transformation is derived here or anywhere else in this repository; those belong
to the research layer that reads this table.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.engine import Connection, Engine

from scripts.config import SCHEMA_NAME, TIME_SERIES_TABLE

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{TIME_SERIES_TABLE}"
BATCH_SIZE = 500
SERIES_BATCH_SIZE = 50
ROUND_DECIMALS = 10

_COLUMNS = ("series_id", "reference_date", "vintage_date", "value", "collected_at")
_KEY_COLUMNS = ("series_id", "reference_date", "vintage_date")
_UPDATE_COLUMNS = ("value", "collected_at")
# Dialects whose MERGE lets a whole batch of same-day revisions travel in one
# statement. Everything else falls back to a parameter-sequence UPDATE, which is
# only reached by the in-process SQLite engine used in tests.
_MERGE_DIALECTS = frozenset({"databricks", "postgresql"})


@dataclass(frozen=True)
class Observation:
    """One published value, carrying the raw file it was parsed from."""

    series_id: str
    reference_date: date
    value: float
    snapshot_id: str


@dataclass(frozen=True)
class WriteResult:
    """What one upsert changed, and what the database already held beforehand."""

    new_observations: int
    new_vintages: int
    same_day_updates: int
    # Keys actually written by this run; availability is recorded for exactly
    # these, since an existing vintage already has an immutable availability row.
    written_keys: list[tuple[str, date, date]]
    # Series that held at least one observation before this run. A new period
    # arriving for one of these was witnessed by the collector, which is what
    # makes `first_seen` a defensible availability basis rather than a guess.
    preexisting_series: frozenset[str]


def _batch_parameters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten a batch into named parameters suffixed by row position."""
    return {
        f"{column}_{index}": row[column] for index, row in enumerate(rows) for column in _COLUMNS
    }


def _insert_statement(count: int) -> TextClause:
    """Build one multi-row INSERT covering ``count`` rows."""
    values = ", ".join(
        "(" + ", ".join(f":{column}_{index}" for column in _COLUMNS) + ")" for index in range(count)
    )
    return text(f"INSERT INTO {_TABLE} ({', '.join(_COLUMNS)}) VALUES {values}")


def _merge_statement(count: int) -> TextClause:
    """Build one Databricks-compatible MERGE covering ``count`` rows."""
    source = " UNION ALL ".join(
        "SELECT " + ", ".join(f":{column}_{index} AS {column}" for column in _COLUMNS)
        for index in range(count)
    )
    condition = " AND ".join(f"target.{column} = source.{column}" for column in _KEY_COLUMNS)
    assignments = ", ".join(f"{column} = source.{column}" for column in _UPDATE_COLUMNS)
    return text(
        f"MERGE INTO {_TABLE} AS target USING ({source}) AS source ON {condition} "
        f"WHEN MATCHED THEN UPDATE SET {assignments}"
    )


_UPDATE_SQL = text(
    f"UPDATE {_TABLE} SET {', '.join(f'{column}=:{column}' for column in _UPDATE_COLUMNS)} "
    f"WHERE {' AND '.join(f'{column}=:{column}' for column in _KEY_COLUMNS)}"
)

_AGGREGATES_SQL = text(
    f"""SELECT series_id, MIN(reference_date) AS first_observation,
    MAX(reference_date) AS last_observation,
    COUNT(DISTINCT reference_date) AS observation_count,
    MAX(collected_at) AS last_collected_at
    FROM {_TABLE} GROUP BY series_id"""
)
_LATEST_SQL = text(
    f"""SELECT series_id, reference_date, vintage_date, value, collected_at
    FROM (SELECT series_id, reference_date, vintage_date, value, collected_at,
    ROW_NUMBER() OVER (PARTITION BY series_id, reference_date
    ORDER BY vintage_date DESC, collected_at DESC) AS rn
    FROM {_TABLE} WHERE series_id IN :series_ids) ranked
    WHERE rn = 1"""
).bindparams(bindparam("series_ids", expanding=True))
_MAX_REFERENCE_SQL = text(
    f"SELECT series_id, MAX(reference_date) AS last_observation FROM {_TABLE} GROUP BY series_id"
)


def _as_date(value: object) -> date:
    """Coerce a driver-returned date/datetime/string to a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    assert isinstance(value, date)
    return value


def get_last_observations(engine: Engine) -> dict[str, date]:
    """Return the latest stored reference date per series."""
    with engine.connect() as conn:
        rows = conn.execute(_MAX_REFERENCE_SQL).mappings().all()
    return {str(row["series_id"]): _as_date(row["last_observation"]) for row in rows}


def get_series_aggregates(conn: Connection) -> dict[str, dict[str, Any]]:
    """Return per-series first, last, distinct count, and latest collection."""
    rows = conn.execute(_AGGREGATES_SQL).mappings().all()
    return {str(row["series_id"]): dict(row) for row in rows}


def _latest(conn: Connection, series_ids: list[str]) -> dict[tuple[str, date], dict[str, Any]]:
    """Fetch the latest stored vintage for a bounded batch of series."""
    rows = conn.execute(_LATEST_SQL, {"series_ids": series_ids}).mappings().all()
    return {(str(row["series_id"]), _as_date(row["reference_date"])): dict(row) for row in rows}


def _write_batches(
    conn: Connection, rows: list[dict[str, Any]], operation: str, merge: bool
) -> None:
    """Apply rows in bounded statements, logging INFO progress per batch."""
    if not rows:
        return
    logger.info(
        "Time-series %s: writing %d rows in batches of %d", operation, len(rows), BATCH_SIZE
    )
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        if merge:
            conn.execute(_merge_statement(len(batch)), _batch_parameters(batch))
        elif operation == "insert":
            conn.execute(_insert_statement(len(batch)), _batch_parameters(batch))
        else:
            conn.execute(_UPDATE_SQL, batch)
        logger.info(
            "Time-series %s progress: %d/%d rows",
            operation,
            min(start + BATCH_SIZE, len(rows)),
            len(rows),
        )


def upsert_time_series(
    conn: Connection, observations: list[Observation], collected_at: datetime
) -> WriteResult:
    """Write new observations and revisions, preserving every earlier vintage.

    Vintage rules, matching the fleet contract for realized data:

    1. First sighting of a key inserts with ``vintage_date`` = collection day.
    2. An identical later value is a no-op and does not touch ``collected_at``.
    3. A changed value on a later day inserts a new vintage; the old row stays.
    4. A changed value on the same day updates only today's row.
    """
    today = collected_at.date()
    incoming = [
        observation
        for observation in observations
        if observation.value is not None and math.isfinite(observation.value)
    ]
    dropped = len(observations) - len(incoming)
    if dropped:
        logger.info("Dropped %d non-finite observations before persistence", dropped)
    logger.info("Time-series upsert: evaluating %d incoming observations", len(incoming))
    if not incoming:
        return WriteResult(0, 0, 0, [], frozenset())

    by_series: dict[str, list[Observation]] = {}
    for observation in incoming:
        by_series.setdefault(observation.series_id, []).append(observation)

    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    written_keys: list[tuple[str, date, date]] = []
    preexisting: set[str] = set()
    new_observations = 0
    new_vintages = 0
    series_ids = sorted(by_series)

    for start in range(0, len(series_ids), SERIES_BATCH_SIZE):
        batch_ids = series_ids[start : start + SERIES_BATCH_SIZE]
        existing = _latest(conn, batch_ids)
        preexisting.update(series_id for series_id, _ in existing)
        for series_id in batch_ids:
            for observation in by_series[series_id]:
                key = (series_id, observation.reference_date)
                current = existing.get(key)
                row: dict[str, Any] = {
                    "series_id": series_id,
                    "reference_date": observation.reference_date,
                    "value": float(observation.value),
                    "collected_at": collected_at,
                }
                if current is None:
                    inserts.append({**row, "vintage_date": today})
                    written_keys.append((series_id, observation.reference_date, today))
                    new_observations += 1
                    continue
                if round(float(current["value"]), ROUND_DECIMALS) == round(
                    float(row["value"]), ROUND_DECIMALS
                ):
                    continue
                vintage = _as_date(current["vintage_date"])
                if vintage == today:
                    updates.append({**row, "vintage_date": today})
                else:
                    inserts.append({**row, "vintage_date": today})
                    written_keys.append((series_id, observation.reference_date, today))
                    new_vintages += 1

    merge = conn.dialect.name in _MERGE_DIALECTS
    _write_batches(conn, inserts, "insert", merge=False)
    _write_batches(conn, updates, "same-day update", merge=merge)
    logger.info(
        "Time-series upsert: new=%d new_vintages=%d same_day_updates=%d",
        new_observations,
        new_vintages,
        len(updates),
    )
    return WriteResult(
        new_observations, new_vintages, len(updates), written_keys, frozenset(preexisting)
    )
