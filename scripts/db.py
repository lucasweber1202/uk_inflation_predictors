"""Read persisted collector contracts without importing collector code."""

from __future__ import annotations

import re

import pandas as pd
from sqlalchemy import Engine, text

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def _safe_identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def load_predictor_contract(
    engine: Engine, schema: str, series_ids: tuple[str, ...] = ()
) -> pd.DataFrame:
    """Join time_series to availability using the fleet's persisted data contract."""
    schema = _safe_identifier(schema)
    where = ""
    parameters: dict[str, object] = {}
    if series_ids:
        placeholders = ", ".join(f":sid{i}" for i in range(len(series_ids)))
        where = f"WHERE t.series_id IN ({placeholders})"
        parameters = {f"sid{i}": sid for i, sid in enumerate(series_ids)}
    statement = text(
        f"""SELECT t.series_id, t.reference_date, t.vintage_date, t.value,
                   a.release_date, a.available_at, a.availability_basis,
                   a.source_snapshot_id
            FROM {schema}.time_series t
            JOIN {schema}.availability a
              ON a.series_id=t.series_id
             AND a.reference_date=t.reference_date
             AND a.vintage_date=t.vintage_date
            {where}"""
    )
    with engine.connect() as connection:
        return pd.read_sql(statement, connection, params=parameters)


def load_target_contract(engine: Engine, schema: str, series_id: str) -> pd.DataFrame:
    """Read target vintages; CPI collectors expose vintage_date/collected_at."""
    schema = _safe_identifier(schema)
    statement = text(
        f"""SELECT series_id, reference_date, vintage_date, value, collected_at
            FROM {schema}.time_series WHERE series_id=:series_id"""
    )
    with engine.connect() as connection:
        return pd.read_sql(statement, connection, params={"series_id": series_id})
