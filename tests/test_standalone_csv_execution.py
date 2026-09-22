"""End-to-end research smoke using only explicit contract-shaped inputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.experiments import run_from_frames


def test_experiment_runs_from_explicit_frames_without_collector_code(tmp_path: Path) -> None:
    months = pd.date_range("2015-01-01", periods=90, freq="MS")
    target_id = "CPI_TEST_VERIFIED"
    predictor_id = "PREDICTOR_TEST"
    target = pd.DataFrame(
        {
            "series_id": target_id,
            "reference_date": months,
            "vintage_date": months + pd.offsets.MonthEnd(1),
            "value": 100 + np.cumsum(0.2 + 0.05 * np.sin(np.arange(90) / 3)),
        }
    )
    predictor = pd.DataFrame(
        {
            "series_id": predictor_id,
            "reference_date": months,
            "vintage_date": months + pd.Timedelta(days=5),
            "value": 50 + np.sin(np.arange(90) / 3),
            "available_at": months + pd.Timedelta(days=5),
            "availability_basis": "official_timestamp",
        }
    )
    config = tmp_path / "experiment.yml"
    config.write_text(
        "\n".join(
            [
                f"target: {target_id}",
                f"predictors: [{predictor_id}]",
                "features: [monthly_mean]",
                "cutoffs: [T-5]",
                "pit_modes: [strict]",
                "ar_orders: [1]",
                "predictor_lags: [0]",
                "minimum_train_months: 24",
                "minimum_oos_predictions: 12",
            ]
        ),
        encoding="utf-8",
    )

    result = run_from_frames(config, target, predictor, "2023-01-01T00:00:00Z")

    assert not result.empty
    assert set(result["pit_mode"]) == {"strict"}
    assert set(result["predictor"]) == {predictor_id}
    assert result["n_predictions"].min() >= 12
