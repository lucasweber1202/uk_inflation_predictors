"""DEFRA parsing, scope filtering, identifier round-trip, and validation gates."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts.extract_defra_fruit_veg import (
    EXPECTED_COLUMNS,
    EXPECTED_FIRST_OBSERVATION,
    _build_catalog,
    _parse_csv,
    make_series_id,
    parse_series_id,
    validate,
)
from scripts.metadata import validate_catalog
from scripts.time_series import Observation

HEADER = ",".join(EXPECTED_COLUMNS)
FRUIT = "fruit,apples,gala,2026-09-14,1.43,kg"
VEG = "vegetable,cabbage,savoy,2026-09-14,0.85,head"
FLOWERS = "cut_flowers,lillies,oriental,2026-09-14,0.7,stem"


def _csv(*rows: str, header: str = HEADER) -> bytes:
    return ("﻿" + "\n".join([header, *rows]) + "\n").encode("utf-8")


def test_parses_product_price_unit_and_reference_date() -> None:
    """All four fields the source publishes per record are preserved."""
    observations, natives = _parse_csv(_csv(FRUIT, VEG), "t.csv", "snap")
    assert len(observations) == 2
    by_series = {row.series_id: row for row in observations}
    apples = by_series["DEFRA_FRUITVEG_FRUIT_APPLES_GALA"]
    assert apples.value == 1.43
    assert apples.reference_date == date(2026, 9, 14)
    assert natives["DEFRA_FRUITVEG_FRUIT_APPLES_GALA"]["unit"] == "kg"
    assert natives["DEFRA_FRUITVEG_VEGETABLE_CABBAGE_SAVOY"]["unit"] == "head"


def test_non_food_categories_are_excluded() -> None:
    """Cut flowers and pot plants are not consumer food prices."""
    observations, natives = _parse_csv(_csv(FRUIT, FLOWERS), "t.csv", "snap")
    assert [row.series_id for row in observations] == ["DEFRA_FRUITVEG_FRUIT_APPLES_GALA"]
    assert "CUTFLOWERS" not in " ".join(natives)


def test_an_unrecognised_category_is_reported_not_silently_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A new upstream category must surface in the run log."""
    with caplog.at_level("WARNING"):
        _parse_csv(_csv(FRUIT, "nuts,walnuts,shelled,2026-09-14,4.2,kg"), "t.csv", "snap")
    assert "unrecognised categories" in caplog.text
    assert "nuts" in caplog.text


def test_a_changed_header_fails_loudly() -> None:
    """The tidy layout is the contract; a change must stop the run."""
    with pytest.raises(ValueError, match="header is"):
        _parse_csv(_csv(FRUIT, header="category,item,variety,week,price,unit"), "t.csv", "s")


def test_an_unverified_price_unit_fails_loudly() -> None:
    """An unknown unit means the price means something this layer has not verified."""
    with pytest.raises(ValueError, match="unverified price unit"):
        _parse_csv(_csv("fruit,apples,gala,2026-09-14,1.43,punnet"), "t.csv", "snap")


def test_one_series_published_in_two_units_fails_loudly() -> None:
    """A unit switch inside one series would make its history incomparable."""
    rows = ("fruit,apples,gala,2026-09-07,1.40,kg", "fruit,apples,gala,2026-09-14,1.43,head")
    with pytest.raises(ValueError, match="two units"):
        _parse_csv(_csv(*rows), "t.csv", "snap")


def test_an_unreadable_row_is_a_soft_failure() -> None:
    """One malformed record is skipped; the rest of the file still loads."""
    observations, _ = _parse_csv(_csv("fruit,apples,gala,not-a-date,1.43,kg", VEG), "t.csv", "s")
    assert len(observations) == 1


def test_series_ids_round_trip() -> None:
    """Identifiers must decode back to the parts that built them."""
    series_id = make_series_id("vegetable", "brussels_sprouts", "brussels_sprouts")
    assert series_id == "DEFRA_FRUITVEG_VEGETABLE_BRUSSELSSPROUTS_BRUSSELSSPROUTS"
    assert parse_series_id(series_id) == (
        "DEFRA",
        "FRUITVEG",
        "VEGETABLE",
        "BRUSSELSSPROUTS",
        "BRUSSELSSPROUTS",
    )


def test_an_empty_label_cannot_produce_an_identifier() -> None:
    """A blank native label must not collapse into a shared identifier."""
    with pytest.raises(ValueError, match="empty identifier token"):
        make_series_id("fruit", "", "gala")


def _panel(count: int, series: int = 65) -> list[Observation]:
    dates = [EXPECTED_FIRST_OBSERVATION + timedelta(days=7 * index) for index in range(count)]
    return [
        Observation(f"DEFRA_FRUITVEG_FRUIT_ITEM{index}_ALL", day, 1.5, "snap")
        for day in dates
        for index in range(series)
    ]


def _natives(series: int = 65) -> dict[str, dict[str, str]]:
    return {
        f"DEFRA_FRUITVEG_FRUIT_ITEM{index}_ALL": {
            "category": "fruit",
            "item": f"item{index}",
            "variety": "all",
            "unit": "kg",
        }
        for index in range(series)
    }


def test_validation_accepts_a_well_formed_panel() -> None:
    """The gate must pass the shape the source actually publishes."""
    validate(_panel(320), _natives())


def test_too_few_series_is_refused() -> None:
    """A partial download must not replace the full product list."""
    with pytest.raises(ValueError, match="below the 60"):
        validate(_panel(320, series=10), _natives(10))


def test_too_few_reference_dates_is_refused() -> None:
    """A truncated history must not overwrite a complete one."""
    with pytest.raises(ValueError, match="reference dates, below"):
        validate(_panel(100), _natives())


def test_a_shifted_first_observation_is_refused() -> None:
    """The 2017-11-03 start is the signature of the full published file."""
    panel = [
        Observation(row.series_id, row.reference_date + timedelta(days=7), row.value, "snap")
        for row in _panel(320)
    ]
    with pytest.raises(ValueError, match="history starts at"):
        validate(panel, _natives())


def test_a_non_positive_price_is_refused() -> None:
    """A zero or negative wholesale price is not a price."""
    panel = _panel(320)
    panel[5] = Observation(panel[5].series_id, panel[5].reference_date, 0.0, "snap")
    with pytest.raises(ValueError, match="non-positive prices"):
        validate(panel, _natives())


def test_a_duplicate_observation_is_refused() -> None:
    """One product may publish one price per reference date."""
    panel = _panel(320)
    with pytest.raises(ValueError, match="duplicate observations"):
        validate([*panel, panel[0]], _natives())


def test_the_catalog_satisfies_the_metadata_vocabularies() -> None:
    """Descriptors must pass the same gate the pipeline applies before writing."""
    _, natives = _parse_csv(_csv(FRUIT, VEG), "t.csv", "snap")
    catalog = _build_catalog(natives, date(2026, 9, 14))
    validate_catalog(catalog)
    name = catalog["DEFRA_FRUITVEG_VEGETABLE_CABBAGE_SAVOY"]["name"]
    # The published physical unit must survive into the descriptive fields,
    # because the fleet `unit` column can only say "currency".
    assert "GBP per head" in name
