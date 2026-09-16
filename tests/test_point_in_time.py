from __future__ import annotations

import pandas as pd

from scripts.features import mtd_feature
from scripts.point_in_time import build_as_of_panel, get_predictor_as_of, get_target_as_of


def sample() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["X", "2025-01-01", "2025-01-10", 1.0, "2025-01-10", "official_timestamp"],
            ["X", "2025-01-01", "2025-02-10", 9.0, "2025-02-10", "first_seen"],
            ["X", "2025-02-01", "2025-02-03", 2.0, "2025-02-03", "inferred"],
            ["X", "2025-03-01", "2025-04-01", 3.0, "2025-04-01", "official_timestamp"],
        ],
        columns=["series_id", "reference_date", "vintage_date", "value", "available_at", "availability_basis"],
    )


def test_future_observation_and_revision_do_not_leak() -> None:
    result = get_predictor_as_of(sample(), "X", "2025-01-31", "strict")
    assert result["value"].tolist() == [1.0]


def test_strict_and_reconstructed_are_separate() -> None:
    strict = get_predictor_as_of(sample(), "X", "2025-03-01", "strict")
    reconstructed = get_predictor_as_of(sample(), "X", "2025-03-01", "reconstructed")
    assert strict["value"].tolist() == [9.0]
    assert reconstructed["value"].tolist() == [9.0, 2.0]
    assert reconstructed["is_reconstructed"].tolist() == [False, True]


def test_as_of_panel_never_exceeds_cutoff() -> None:
    panel = build_as_of_panel(sample(), "2025-03-15", "reconstructed")
    assert (panel["available_at"] <= pd.Timestamp("2025-03-15", tz="UTC")).all()


def test_target_and_predictor_revisions_change_only_after_publication() -> None:
    rows = pd.DataFrame(
        [
            ["X", "2020-01-01", "2020-02-01", 1.0, "2020-02-01", "official_timestamp"],
            ["X", "2020-01-01", "2020-06-15", 9.0, "2020-06-15", "official_timestamp"],
        ],
        columns=["series_id", "reference_date", "vintage_date", "value", "available_at", "availability_basis"],
    )
    assert get_target_as_of(rows, "X", "2020-06-01")["value"].tolist() == [1.0]
    assert get_target_as_of(rows, "X", "2020-07-01")["value"].tolist() == [9.0]
    assert get_predictor_as_of(rows, "X", "2020-06-01")["value"].tolist() == [1.0]


def test_mtd_filters_on_available_at_not_only_reference_date() -> None:
    rows = pd.DataFrame(
        [
            ["X", "2025-04-08", "2025-04-09", 2.0, "2025-04-09", "official_timestamp"],
            ["X", "2025-04-09", "2025-04-14", 100.0, "2025-04-14", "official_timestamp"],
        ],
        columns=["series_id", "reference_date", "vintage_date", "value", "available_at", "availability_basis"],
    )
    pit = get_predictor_as_of(rows, "X", "2025-04-10")
    assert mtd_feature(pit, "2025-04-10") == 2.0
