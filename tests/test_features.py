from __future__ import annotations

import pandas as pd

from scripts.features import aggregate_monthly, mtd_feature, trailing_feature, transformations


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"series_id": ["X"] * 4, "reference_date": ["2025-04-01", "2025-04-08", "2025-04-14", "2025-05-01"], "value": [1.0, 3.0, 100.0, 5.0]}
    )


def test_mtd_does_not_use_observation_after_cutoff() -> None:
    assert mtd_feature(frame(), "2025-04-10") == 2.0


def test_weekly_trailing_window() -> None:
    assert trailing_feature(frame(), "2025-04-10", 7) == 3.0


def test_monthly_aggregation_and_transforms() -> None:
    level = aggregate_monthly(frame(), "monthly_last")
    assert level.loc[pd.Timestamp("2025-04-01")] == 100.0
    assert transformations(level).loc[pd.Timestamp("2025-05-01"), "mom"] == -0.95
