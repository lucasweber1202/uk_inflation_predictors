from __future__ import annotations

import pandas as pd

from scripts.cutoffs import forecast_cutoffs


def test_cutoff_uses_first_persisted_release_not_fixed_day() -> None:
    target = pd.DataFrame(
        {
            "reference_date": ["2025-01-01", "2025-01-01", "2025-02-01"],
            "available_at": ["2025-02-19 07:00Z", "2025-03-10 07:00Z", "2025-03-26 07:00Z"],
        }
    )
    cutoffs = forecast_cutoffs(target, "T-5")
    assert cutoffs.iloc[0] == pd.Timestamp("2025-02-14 07:00Z")
    assert cutoffs.iloc[1] == pd.Timestamp("2025-03-21 07:00Z")
