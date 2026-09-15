"""Rerun behaviour: unchanged sources write nothing; revisions add vintages."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from scripts.config import METADATA_TABLE, SCHEMA_NAME, TIME_SERIES_TABLE
from scripts.metadata import upsert_metadata
from scripts.snapshots import Snapshot, upsert_snapshots
from scripts.time_series import Observation, upsert_time_series

SERIES = "DESNZ_ROADFUEL_ULSD_PUMPPRICE"
DAY_ONE = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
DAY_TWO = datetime(2026, 3, 3, 9, 0, tzinfo=UTC)

CATALOG = {
    SERIES: {
        "source_id": "desnz_road_fuels",
        "name": "UK weekly road fuel pump price: ultra low sulphur diesel",
        "description": "Test descriptor.",
        "frequency": "weekly",
        "unit": "currency",
        "eco_group": "consumer_prices",
        "source_url": "https://www.gov.uk/government/statistics/weekly-road-fuel-prices",
        "last_publish_date": date(2026, 3, 2),
    }
}


def _observations(value: float) -> list[Observation]:
    return [Observation(SERIES, date(2026, 2, 23), value, "snap")]


def test_second_identical_run_writes_no_observation(engine: Engine) -> None:
    """The release criterion: an unchanged source is a data no-op."""
    with engine.begin() as conn:
        first = upsert_time_series(conn, _observations(150.0), DAY_ONE)
    assert (first.new_observations, first.new_vintages) == (1, 0)

    with engine.begin() as conn:
        second = upsert_time_series(conn, _observations(150.0), DAY_TWO)
    assert (second.new_observations, second.new_vintages, second.same_day_updates) == (0, 0, 0)
    assert second.written_keys == []

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT collected_at FROM {SCHEMA_NAME}.{TIME_SERIES_TABLE}")
        ).all()
    assert len(rows) == 1, "an unchanged rerun must not add a row"


def test_second_identical_run_writes_no_metadata(engine: Engine) -> None:
    """Identical metadata is a no-op, including `collected_at`."""
    with engine.begin() as conn:
        upsert_time_series(conn, _observations(150.0), DAY_ONE)
        assert upsert_metadata(conn, CATALOG, DAY_ONE) == (1, 0)
    with engine.begin() as conn:
        assert upsert_metadata(conn, CATALOG, DAY_TWO) == (0, 0)
    with engine.connect() as conn:
        collected = conn.execute(
            text(f"SELECT collected_at FROM {SCHEMA_NAME}.{METADATA_TABLE}")
        ).scalar_one()
    assert collected == DAY_ONE


def test_a_revision_on_a_later_day_adds_a_vintage_and_keeps_the_old_one(
    engine: Engine,
) -> None:
    """Historical vintages are never overwritten."""
    with engine.begin() as conn:
        upsert_time_series(conn, _observations(150.0), DAY_ONE)
    with engine.begin() as conn:
        revision = upsert_time_series(conn, _observations(151.5), DAY_TWO)
    assert (revision.new_observations, revision.new_vintages) == (0, 1)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT vintage_date, value FROM {SCHEMA_NAME}.{TIME_SERIES_TABLE} "
                "ORDER BY vintage_date"
            )
        ).all()
    assert [(row[0], row[1]) for row in rows] == [
        (date(2026, 3, 2), 150.0),
        (date(2026, 3, 3), 151.5),
    ]


def test_a_revision_on_the_same_day_updates_todays_row_only(engine: Engine) -> None:
    """A same-day correction must not create a second vintage for that day."""
    with engine.begin() as conn:
        upsert_time_series(conn, _observations(150.0), DAY_ONE)
    with engine.begin() as conn:
        same_day = upsert_time_series(conn, _observations(150.4), DAY_ONE.replace(hour=17))
    assert (same_day.new_observations, same_day.new_vintages, same_day.same_day_updates) == (
        0,
        0,
        1,
    )
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT vintage_date, value FROM {SCHEMA_NAME}.{TIME_SERIES_TABLE}")
        ).all()
    assert rows == [(date(2026, 3, 2), 150.4)]


def test_preexisting_series_are_reported_so_first_seen_can_be_justified(
    engine: Engine,
) -> None:
    """`first_seen` is only defensible for a series the collector already held."""
    with engine.begin() as conn:
        fresh = upsert_time_series(conn, _observations(150.0), DAY_ONE)
    assert fresh.preexisting_series == frozenset()

    with engine.begin() as conn:
        later = upsert_time_series(
            conn,
            [*_observations(150.0), Observation(SERIES, date(2026, 3, 2), 152.0, "snap")],
            DAY_TWO,
        )
    assert later.preexisting_series == frozenset({SERIES})
    assert later.new_observations == 1


def _snapshot(digest: str) -> Snapshot:
    return Snapshot(
        snapshot_id=digest,
        source_id="desnz_road_fuels",
        source_url="https://assets.publishing.service.gov.uk/media/x/y.csv",
        fetched_at=DAY_ONE,
        source_published_date=date(2026, 3, 2),
        http_etag='"abc"',
        http_last_modified="Mon, 02 Mar 2026 08:30:00 GMT",
        sha256=digest,
        byte_size=10,
        raw_path="_raw/desnz_road_fuels/abc-y.csv",
    )


def test_an_unchanged_file_records_no_second_snapshot(engine: Engine) -> None:
    """Snapshot identity is the content digest, so re-downloading is a no-op."""
    with engine.begin() as conn:
        assert upsert_snapshots(conn, [_snapshot("a" * 64)]) == 1
    with engine.begin() as conn:
        assert upsert_snapshots(conn, [_snapshot("a" * 64)]) == 0


def test_a_replaced_file_is_recorded_alongside_the_old_one(engine: Engine) -> None:
    """A source that rewrites history must leave both snapshots visible."""
    with engine.begin() as conn:
        upsert_snapshots(conn, [_snapshot("a" * 64)])
    with engine.begin() as conn:
        assert upsert_snapshots(conn, [_snapshot("b" * 64)]) == 1
    with engine.connect() as conn:
        count = conn.execute(
            text(f"SELECT COUNT(*) FROM {SCHEMA_NAME}.source_snapshots")
        ).scalar_one()
    assert count == 2
