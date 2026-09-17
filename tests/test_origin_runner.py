from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.config import load_config
from scripts.experiments import run_from_frames
from scripts.features import feature_series_as_of
from scripts.point_in_time import get_predictor_as_of


def _config(path: Path) -> Path:
    path.write_text(
        """
target: TARGET
predictors: [PREDICTOR]
features: [monthly_mean]
cutoffs: [T-5]
pit_modes: [strict]
ar_orders: [1]
predictor_lags: [0]
minimum_train_months: 12
minimum_oos_predictions: 1
max_nan_fraction: 0.35
""".strip(),
        encoding="utf-8",
    )
    return path


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.date_range("2022-01-01", periods=24, freq="MS")
    target_rows = []
    predictor_rows = []
    for position, month in enumerate(months):
        target_rows.append(
            [
                "TARGET",
                month,
                month + pd.DateOffset(months=1, days=19),
                100.0 + position,
                month + pd.DateOffset(months=1, days=19),
                "official_timestamp",
            ]
        )
        predictor_rows.append(
            [
                "PREDICTOR",
                month,
                month + pd.DateOffset(days=4),
                50.0 + position,
                month + pd.DateOffset(days=4),
                "official_date",
            ]
        )
    # Revisions become visible between the cutoffs for November and December 2023.
    target_rows.append(["TARGET", months[5], "2023-12-01", 999.0, "2023-12-01", "first_seen"])
    predictor_rows.append(["PREDICTOR", months[5], "2023-12-01", 777.0, "2023-12-01", "first_seen"])
    columns = [
        "series_id",
        "reference_date",
        "vintage_date",
        "value",
        "available_at",
        "availability_basis",
    ]
    return pd.DataFrame(target_rows, columns=columns), pd.DataFrame(predictor_rows, columns=columns)


def test_origin_runner_does_not_rewrite_prior_forecast(tmp_path: Path) -> None:
    target, predictor = _frames()
    config = _config(tmp_path / "config.yml")
    early = run_from_frames(config, target, predictor, "2023-11-30")
    full = run_from_frames(config, target, predictor)
    key = ["forecast_month", "cutoff", "pit_mode", "feature", "benchmark"]
    overlap = early.merge(full, on=key, suffixes=("_early", "_full"), validate="one_to_one")
    assert not overlap.empty
    assert overlap["forecast_early"].equals(overlap["forecast_full"])


def test_cutoff_feature_uses_available_at_not_only_reference_date() -> None:
    frame = pd.DataFrame(
        [
            ["X", "2025-04-08", "2025-04-09", 2.0, "2025-04-09", "official_date"],
            ["X", "2025-04-09", "2025-04-14", 100.0, "2025-04-14", "official_date"],
        ],
        columns=[
            "series_id",
            "reference_date",
            "vintage_date",
            "value",
            "available_at",
            "availability_basis",
        ],
    )
    pit = get_predictor_as_of(frame, "X", "2025-04-10", "strict")
    feature = feature_series_as_of(pit, "2025-04-10", "mtd_mean", "2025-04-01")
    assert feature.loc[pd.Timestamp("2025-04-01")] == 2.0


def test_unsupported_feature_fails_before_experiment(tmp_path: Path) -> None:
    config = _config(tmp_path / "config.yml")
    config.write_text(config.read_text().replace("monthly_mean", "17d_average"))
    with pytest.raises(ValueError, match="Unsupported feature"):
        load_config(config)
