"""DESNZ parsing, identifier round-trip, and the structural validation gates."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.extract_desnz_road_fuels import (
    COLUMN_SERIES,
    EXPECTED_FIRST_OBSERVATION,
    _build_catalog,
    _parse_csv,
    make_series_id,
    parse_series_id,
    validate,
)
from scripts.metadata import validate_catalog
from scripts.time_series import Observation

HEADER = ",".join(["Date", *COLUMN_SERIES])
ROW = "09/06/2003,74.59,76.77,45.82,45.82,17.5,17.5"


def _csv(*rows: str, header: str = HEADER) -> bytes:
    return ("﻿" + "\n".join([header, *rows]) + "\n").encode("utf-8")


def test_parses_the_published_row_into_six_series() -> None:
    """One published week yields one observation per verified column."""
    observations = _parse_csv(_csv(ROW), "test.csv", "snap")
    assert len(observations) == 6
    by_series = {row.series_id: row.value for row in observations}
    assert by_series["DESNZ_ROADFUEL_ULSP_PUMPPRICE"] == 74.59
    assert by_series["DESNZ_ROADFUEL_ULSD_PUMPPRICE"] == 76.77
    assert by_series["DESNZ_ROADFUEL_ULSP_DUTYRATE"] == 45.82
    assert by_series["DESNZ_ROADFUEL_ULSD_VATRATE"] == 17.5
    assert all(row.reference_date == date(2003, 6, 9) for row in observations)
    assert all(row.snapshot_id == "snap" for row in observations)


def test_day_first_dates_are_not_read_as_month_first() -> None:
    """The source publishes dd/mm/yyyy; reading it as mm/dd would silently shift."""
    observations = _parse_csv(_csv("06/11/2017,119.91,123.69,57.95,57.95,20,20"), "t.csv", "s")
    assert observations[0].reference_date == date(2017, 11, 6)


def test_a_renamed_column_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A moved or renamed column must stop the run, not be skipped."""
    header = HEADER.replace("Pump price in pence/litre", "Pump price", 1)
    with pytest.raises(ValueError, match="missing verified columns"):
        _parse_csv(_csv(ROW, header=header), "test.csv", "snap")


def test_a_missing_date_column_fails_loudly() -> None:
    """The reference-date column is the one column that cannot be inferred."""
    header = HEADER.replace("Date", "Week", 1)
    with pytest.raises(ValueError, match="first column"):
        _parse_csv(_csv(ROW, header=header), "test.csv", "snap")


def test_an_unreadable_date_is_a_soft_failure() -> None:
    """One bad row is warned and skipped; the rest of the file still loads."""
    observations = _parse_csv(_csv("not-a-date,1,2,3,4,5,6", ROW), "test.csv", "snap")
    assert len(observations) == 6


def test_a_blank_cell_is_dropped_rather_than_stored_as_zero() -> None:
    """An empty cell is missing data, never a zero price."""
    observations = _parse_csv(_csv("09/06/2003,74.59,,45.82,45.82,17.5,17.5"), "t.csv", "s")
    assert "DESNZ_ROADFUEL_ULSD_PUMPPRICE" not in {row.series_id for row in observations}
    assert len(observations) == 5


@pytest.mark.parametrize(
    ("product", "measure"),
    [("ULSP", "PUMPPRICE"), ("ULSD", "DUTYRATE"), ("ULSP", "VATRATE")],
)
def test_series_ids_round_trip(product: str, measure: str) -> None:
    """Identifiers must decode back to the fields that built them."""
    series_id = make_series_id(product, measure)
    assert series_id.isupper()
    assert parse_series_id(series_id) == ("DESNZ", "ROADFUEL", product, measure)


def test_an_unknown_identifier_is_rejected() -> None:
    """An identifier this collector does not publish must not parse."""
    with pytest.raises(ValueError):
        parse_series_id("DESNZ_ROADFUEL_LPG_PUMPPRICE")
    with pytest.raises(ValueError):
        parse_series_id("CPI_COICOP_ALL_D7BT")


def _panel(dates: list[date]) -> list[Observation]:
    return [
        Observation(
            make_series_id(product, measure), day, 100.0 if measure != "VATRATE" else 20.0, "snap"
        )
        for day in dates
        for product in ("ULSP", "ULSD")
        for measure in ("PUMPPRICE", "DUTYRATE", "VATRATE")
    ]


def _weekly(count: int) -> list[date]:
    from datetime import timedelta

    return [EXPECTED_FIRST_OBSERVATION + timedelta(days=7 * index) for index in range(count)]


def test_validation_accepts_the_shape_the_source_actually_publishes() -> None:
    """The gate must pass a well-formed panel, or it gates nothing useful."""
    validate(_panel(_weekly(1100)))


def test_a_truncated_history_is_refused() -> None:
    """A short download must not silently replace a full history."""
    with pytest.raises(ValueError, match="below the"):
        validate(_panel(_weekly(50)))


def test_a_shifted_first_observation_is_refused() -> None:
    """The 2003 start is the signature of the historic attachment being present."""
    from datetime import timedelta

    shifted = [day + timedelta(days=7) for day in _weekly(1100)]
    with pytest.raises(ValueError, match="history starts at"):
        validate(_panel(shifted))


def test_a_dropped_week_is_refused() -> None:
    """A hole in the weekly cadence means a week went missing upstream."""
    dates = _weekly(1100)
    del dates[500]
    with pytest.raises(ValueError, match="cadence broken"):
        validate(_panel(dates))


def test_a_duplicate_observation_is_refused() -> None:
    """One series may publish one value per reference week."""
    panel = _panel(_weekly(1100))
    with pytest.raises(ValueError, match="duplicate observations"):
        validate([*panel, panel[0]])


def test_an_impossible_vat_rate_is_refused() -> None:
    """A percentage outside 0-100 means the column meaning changed."""
    panel = _panel(_weekly(1100))
    broken = [
        Observation(row.series_id, row.reference_date, 2000.0, row.snapshot_id)
        if row.series_id.endswith("VATRATE")
        else row
        for row in panel
    ]
    with pytest.raises(ValueError, match="not a percentage"):
        validate(broken)


def test_the_catalog_satisfies_the_metadata_vocabularies() -> None:
    """Descriptors must pass the same gate the pipeline applies before writing."""
    catalog = _build_catalog(date(2026, 9, 15))
    assert len(catalog) == 6
    validate_catalog(catalog)
    assert all(fields["source_id"] == "desnz_road_fuels" for fields in catalog.values())
