from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.evaluation import benchmark_forecasts, expanding_forecast, metrics
from scripts.models import design_matrix


def test_lagging_and_expanding_window() -> None:
    index = pd.date_range("2010-01-01", periods=90, freq="MS")
    predictor = pd.Series(np.sin(np.arange(90) / 4), index=index)
    target = 0.4 * predictor.shift(1).fillna(0) + pd.Series(np.arange(90) * 0.001, index=index)
    x, _ = design_matrix(target, 2, predictor, 1)
    assert list(x.columns) == ["ar1", "ar2", "predictor"]
    forecast = expanding_forecast(target, predictor, 2, 1, 36)
    assert len(forecast) > 40


def test_benchmarks_and_metrics() -> None:
    index = pd.date_range("2010-01-01", periods=90, freq="MS")
    target = pd.Series(np.cos(np.arange(90) / 5), index=index)
    forecasts = benchmark_forecasts(target, 36, (1, 2, 3, 6, 12))
    assert {"historical_mean", "last_observation", "AR1", "AR2", "AR3", "AR6", "AR12"} == set(forecasts)
    result = metrics(target, forecasts["AR1"])
    assert result["n_predictions"] > 0 and result["rmse"] >= 0
