from __future__ import annotations

import pandas as pd

from scripts.point_in_time import build_as_of_panel, get_predictor_as_of


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
