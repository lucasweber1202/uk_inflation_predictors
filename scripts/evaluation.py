"""Expanding-window pseudo-out-of-sample evaluation and metrics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from scripts.models import design_matrix, fit_ols, predict_ols


def metrics(actual: pd.Series, forecast: pd.Series) -> dict[str, float]:
    joined = pd.concat([actual.rename("actual"), forecast.rename("forecast")], axis=1).dropna()
    if joined.empty:
        raise ValueError("No aligned forecasts")
    error = joined["forecast"] - joined["actual"]
    direction_actual = np.sign(joined["actual"])
    direction_forecast = np.sign(joined["forecast"])
    return {
        "rmse": float(math.sqrt(np.mean(np.square(error)))),
        "mae": float(np.mean(np.abs(error))),
        "bias": float(np.mean(error)),
        "directional_accuracy": float(np.mean(direction_actual == direction_forecast)),
        "n_predictions": float(len(joined)),
    }


def expanding_forecast(
    target: pd.Series,
    predictor: pd.Series | None,
    ar_order: int,
    predictor_lag: int,
    minimum_train_months: int,
) -> pd.Series:
    x, y = design_matrix(target, ar_order, predictor, predictor_lag)
    forecasts: dict[pd.Timestamp, float] = {}
    for position in range(minimum_train_months, len(y)):
        train_x, train_y = x.iloc[:position], y.iloc[:position]
        coefficients = fit_ols(train_x, train_y)
        forecasts[pd.Timestamp(y.index[position])] = predict_ols(coefficients, x.iloc[position])
    return pd.Series(forecasts, name="forecast", dtype=float)


def benchmark_forecasts(target: pd.Series, minimum_train_months: int, ar_orders: tuple[int, ...] = (1, 2, 3, 6, 12)) -> dict[str, pd.Series]:
    ordered = target.dropna().sort_index()
    forecasts: dict[str, pd.Series] = {}
    index = ordered.index[minimum_train_months:]
    forecasts["historical_mean"] = pd.Series(
        [ordered.iloc[:i].mean() for i in range(minimum_train_months, len(ordered))], index=index
    )
    forecasts["last_observation"] = ordered.shift(1).reindex(index)
    for order in ar_orders:
        forecasts[f"AR{order}"] = expanding_forecast(ordered, None, order, 0, minimum_train_months)
    return forecasts


def compare_to_benchmark(model: dict[str, float], benchmark: dict[str, float]) -> dict[str, float]:
    return {
        "relative_rmse": model["rmse"] / benchmark["rmse"],
        "rmse_improvement": 1.0 - model["rmse"] / benchmark["rmse"],
        "relative_mae": model["mae"] / benchmark["mae"],
        "mae_improvement": 1.0 - model["mae"] / benchmark["mae"],
    }
