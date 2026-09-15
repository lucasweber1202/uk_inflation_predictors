"""Collect open UK predictor sources into the point-in-time predictor layer.

This repository stores explanatory variables (X) only. The official UK CPI
target variables (Y) are collected by `collector_ons_cpi` and are never
reproduced, re-weighted or re-aggregated here.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine

from scripts.availability import attribute_release, upsert_availability
from scripts.config import LOG_LEVEL, missing_environment, unresolved_credentials
from scripts.db import build_engine
from scripts.extract_defra_fruit_veg import collect as collect_defra
from scripts.extract_desnz_road_fuels import collect as collect_desnz
from scripts.govuk import SourceData, build_client
from scripts.init_db import init_db
from scripts.metadata import upsert_metadata
from scripts.run_logs import insert_run_log
from scripts.snapshots import upsert_snapshots
from scripts.time_series import WriteResult, upsert_time_series

logger = logging.getLogger("main")

# The registry of implemented sources. Adding a source means adding one
# `extract_<source>.py` and one entry here; nothing else in this file changes.
SOURCES = {
    "desnz_road_fuels": collect_desnz,
    "defra_fruit_veg": collect_defra,
}

# Dialects whose multi-statement transaction covers every table one source
# touches. Databricks SQL commits each statement on its own, so there an
# interrupted run is repaired by the next run rather than rolled back.
TRANSACTIONAL_DIALECTS = frozenset({"postgresql", "sqlite"})


def _setup_logging(level: str) -> io.StringIO:
    """Capture collector logs while suppressing noisy third-party INFO output."""
    buffer = io.StringIO()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    buffer_handler = logging.StreamHandler(stream=buffer)
    buffer_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.ERROR)
    root.addHandler(stream_handler)
    root.addHandler(buffer_handler)
    app_level = level.upper()
    logging.getLogger("main").setLevel(app_level)
    logging.getLogger("scripts").setLevel(app_level)
    return buffer


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect open UK inflation predictor sources (X variables)."
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=sorted(SOURCES),
        help="Collect one source; repeatable.",
    )
    parser.add_argument("--all", action="store_true", help="Collect every implemented source.")
    parser.add_argument("--log-level", default=LOG_LEVEL)
    return parser.parse_args(argv)


def _selected_sources(args: argparse.Namespace) -> list[str]:
    """Resolve the CLI selection into an ordered, deduplicated source list."""
    if args.all:
        if args.source:
            raise SystemExit("--all and --source are mutually exclusive")
        return sorted(SOURCES)
    if not args.source:
        raise SystemExit("Choose --source <name> or --all")
    return sorted(dict.fromkeys(args.source))


def _availability_rows(
    data: SourceData, result: WriteResult, collected_at: datetime
) -> list[dict[str, Any]]:
    """Decide, per newly written vintage, when it became available and on what basis.

    Precedence, strongest evidence first:

    1. An official publication timestamp the reference period can be attributed
       to, which is evidence from the source itself.
    2. ``first_seen``: no official timestamp reaches this period, but the series
       already held history before this run, so the collector genuinely watched
       this observation arrive and the collection instant is a true upper bound.
    3. Whatever ``attribute_release`` fell back to — ``inferred`` from the
       source's observed release rule, or ``unknown``. On a fresh backfill there
       is nothing to have witnessed, so this is where uncovered history lands.
    """
    snapshot_by_key = {
        (observation.series_id, observation.reference_date): observation.snapshot_id
        for observation in data.observations
    }
    rows: list[dict[str, Any]] = []
    for series_id, reference_date, vintage_date in result.written_keys:
        available_at, basis, release_date = attribute_release(
            reference_date,
            data.releases,
            data.min_lag_days,
            data.max_lag_days,
            data.inferred_lag_days,
        )
        if basis != "official_timestamp" and series_id in result.preexisting_series:
            available_at, basis, release_date = collected_at, "first_seen", None
        rows.append(
            {
                "series_id": series_id,
                "reference_date": reference_date,
                "vintage_date": vintage_date,
                "release_date": release_date,
                "available_at": available_at,
                "availability_basis": basis,
                "source_snapshot_id": snapshot_by_key[(series_id, reference_date)],
            }
        )
    return rows


def _log_availability_quality(rows: list[dict[str, Any]], source_id: str) -> None:
    """Report how much of what was just written is genuinely point-in-time."""
    if not rows:
        return
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["availability_basis"]] = counts.get(row["availability_basis"], 0) + 1
    logger.info(
        "%s availability bases: %s",
        source_id,
        ", ".join(f"{basis}={count}" for basis, count in sorted(counts.items())),
    )
    reconstructed = counts.get("inferred", 0) + counts.get("unknown", 0)
    if reconstructed:
        logger.warning(
            "%s: %d of %d written vintages have reconstructed availability "
            "(inferred/unknown) and are excluded from get_series_as_of by default",
            source_id,
            reconstructed,
            len(rows),
        )


def collect_source(engine: Engine, name: str) -> None:
    """Run one source end to end: extract, validate, then persist in one transaction."""
    logger.info("Collecting source %s", name)
    with build_client() as client:
        data = SOURCES[name](client)

    collected_at = datetime.now(UTC)
    if engine.dialect.name not in TRANSACTIONAL_DIALECTS:
        logger.warning(
            "%s commits each statement separately; an interrupted run is repaired by the "
            "next run rather than rolled back",
            engine.dialect.name,
        )
    with engine.begin() as conn:
        snapshots_written = upsert_snapshots(conn, data.snapshots)
        result = upsert_time_series(conn, data.observations, collected_at)
        rows = _availability_rows(data, result, collected_at)
        _log_availability_quality(rows, name)
        availability_written = upsert_availability(conn, rows, collected_at)
        metadata_inserted, metadata_updated = upsert_metadata(conn, data.catalog, collected_at)
    logger.info(
        "%s result: observations=%d vintages=%d same_day_updates=%d availability=%d "
        "snapshots=%d metadata_inserted=%d metadata_updated=%d",
        name,
        result.new_observations,
        result.new_vintages,
        result.same_day_updates,
        availability_written,
        snapshots_written,
        metadata_inserted,
        metadata_updated,
    )


def main(args: argparse.Namespace) -> int:
    """Run the selected sources against one caller-owned engine."""
    missing = missing_environment()
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    for name in unresolved_credentials():
        logger.warning("%s is unset; it must resolve from the runtime context", name)

    sources = _selected_sources(args)
    engine = build_engine()
    try:
        init_db(engine)
        for name in sources:
            collect_source(engine, name)
    finally:
        engine.dispose()
    return 0


def run(argv: list[str] | None = None) -> int:
    """Run the pipeline and always attempt a separate durable execution log."""
    arguments = _parse_args(argv)
    log_buffer = _setup_logging(arguments.log_level)
    started_at = datetime.now(UTC)
    status = "success"
    traceback_text: str | None = None
    return_code = 0
    try:
        return_code = main(arguments)
    except Exception:
        status = "error"
        traceback_text = traceback.format_exc()
        logger.exception("Pipeline failed")
        return_code = 1
    finally:
        finished_at = datetime.now(UTC)
        log_engine = None
        try:
            log_engine = build_engine()
            init_db(log_engine)
            insert_run_log(
                log_engine,
                started_at,
                finished_at,
                status,
                log_buffer.getvalue(),
                traceback_text,
            )
        except Exception:
            logger.exception("Could not persist run log")
            return_code = 1
        finally:
            if log_engine is not None:
                log_engine.dispose()
    return return_code


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
